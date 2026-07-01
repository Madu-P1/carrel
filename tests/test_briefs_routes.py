"""HTTP-level tests for the Shelf routes (routes/briefs.py).

The service layer (services/briefs.py) is unit-tested in test_briefs.py;
these tests cover what only the HTTP layer adds: the response envelopes,
404 mapping, Pydantic 422 on a malformed fingerprint, and that the new
routes sit behind the local-API-token gate like every other /api/* path.

A real temp-migrated DB is configured on `db`, and routes/briefs.py
calls `db.get_db()`, so TestClient requests hit actual rows — no mocking.
TestClient is used without a `with` block so app startup events (which
would otherwise reconfigure paths) do not fire.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import db
import main
from services.local_api_security import HEADER_NAME, get_local_api_token

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"

HEX64 = "0" * 64
SAMPLE_RESPONSE = {"draft_text": "x", "claim_verdicts": [], "unplaced": []}
SAMPLE_CERT = {"fingerprint": HEX64, "sealed_count": 0}


class BriefsRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        data_dir.mkdir(parents=True, exist_ok=True)
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=upload_dir,
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        with db.get_db() as conn:
            db.apply_migrations(conn)

        from fastapi.testclient import TestClient

        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self._original_paths[0],
            data_dir=self._original_paths[1],
            upload_dir=self._original_paths[2],
            db_path=self._original_paths[3],
            schema_path=self._original_paths[4],
        )
        self._temp.cleanup()

    def _save(self, **overrides):
        body = {
            "draft": "Motion to Dismiss\n\nBody.",
            "fingerprint": HEX64,
            "response": SAMPLE_RESPONSE,
            "cert": SAMPLE_CERT,
            "seal_state": "sealed",
        }
        body.update(overrides)
        return self.client.post("/api/briefs", json=body)

    def test_save_list_get_delete_round_trip(self) -> None:
        # save
        saved = self._save()
        self.assertEqual(saved.status_code, 200, saved.text)
        brief = saved.json()["brief"]
        brief_id = brief["id"]
        self.assertEqual(brief["seal_state"], "sealed")
        self.assertEqual(brief["fingerprint"], HEX64)
        # the save envelope is the lean summary — no heavy blobs
        self.assertNotIn("response", brief)
        self.assertNotIn("draft", brief)

        # list
        listed = self.client.get("/api/briefs")
        self.assertEqual(listed.status_code, 200)
        ids = [b["id"] for b in listed.json()["briefs"]]
        self.assertIn(brief_id, ids)

        # get (full re-hydration payload)
        got = self.client.get(f"/api/briefs/{brief_id}")
        self.assertEqual(got.status_code, 200)
        detail = got.json()
        self.assertEqual(detail["draft"], "Motion to Dismiss\n\nBody.")
        self.assertEqual(detail["response"], SAMPLE_RESPONSE)
        self.assertEqual(detail["cert"], SAMPLE_CERT)

        # delete
        deleted = self.client.delete(f"/api/briefs/{brief_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"deleted": True, "brief_id": brief_id})

        # gone
        self.assertEqual(self.client.get(f"/api/briefs/{brief_id}").status_code, 404)

    def test_get_unknown_returns_404(self) -> None:
        self.assertEqual(self.client.get("/api/briefs/nope").status_code, 404)

    def test_delete_unknown_returns_404(self) -> None:
        self.assertEqual(self.client.delete("/api/briefs/nope").status_code, 404)

    def test_malformed_fingerprint_is_rejected_422(self) -> None:
        resp = self._save(fingerprint="not-a-hash")
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_empty_draft_is_rejected_422(self) -> None:
        # min_length=1 on draft is a Pydantic-layer rejection (422), distinct
        # from the service's whitespace-only 400.
        resp = self._save(draft="")
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_unsealing_a_sealed_brief_is_refused_409(self) -> None:
        # Seal-immutability at the HTTP boundary: once sealed, a POST to the
        # same fingerprint that would un-seal it is refused with 409, and the
        # brief stays sealed and unchanged.
        sealed = self._save()  # seal_state defaults to "sealed"
        self.assertEqual(sealed.status_code, 200, sealed.text)
        brief_id = sealed.json()["brief"]["id"]

        resp = self._save(seal_state="unsealed", draft="TAMPERED body", response={"x": 1})
        self.assertEqual(resp.status_code, 409, resp.text)

        detail = self.client.get(f"/api/briefs/{brief_id}").json()
        self.assertEqual(detail["seal_state"], "sealed")
        self.assertEqual(detail["draft"], "Motion to Dismiss\n\nBody.")
        self.assertEqual(detail["response"], SAMPLE_RESPONSE)

    def test_reseal_same_state_is_idempotent_200(self) -> None:
        # A same-state re-seal (retry) is not a modification: 200, no 409.
        sealed = self._save()
        self.assertEqual(sealed.status_code, 200, sealed.text)
        again = self._save()  # identical, still seal_state="sealed"
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["brief"]["seal_state"], "sealed")

    def test_routes_sit_behind_the_local_api_token_gate(self) -> None:
        from fastapi.testclient import TestClient

        ungated = TestClient(main.app)  # no token header
        self.assertEqual(ungated.get("/api/briefs").status_code, 403)


if __name__ == "__main__":
    unittest.main()
