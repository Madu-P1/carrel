"""Tests for services/briefs.py — Shelf persistence round-trips.

Bootstraps a real SQLite database against a temporary directory the way
test_db_migrations.py does, so migration 0024_briefs.sql runs end to end
and the service functions hit actual rows. Each test opens its own
connection; the schema persists in the temp file across connections.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

import db
from services import briefs

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"

# A realistic-shaped verify response: nested claims + a top-level unplaced
# list, to prove JSON fidelity through the TEXT blob round-trip.
SAMPLE_RESPONSE = {
    "draft_text": "The court held that the statute applies.",
    "claims": [
        {"id": 1, "disposition": "supported", "placement": {"placed": True}},
        {"id": 2, "disposition": "claim_unsupported", "placement": {"placed": False}},
    ],
    "unplaced": [2],
    "provider": "claude",
}
SAMPLE_CERT = {"fingerprint": "a" * 64, "sealed_count": 1, "flagged": ["claim 2"]}
HEX64 = "a" * 64
# Distinct valid 64-char lowercase-hex fingerprints. save_brief upserts on
# fingerprint, so any test that needs N distinct rows must use N distinct
# fingerprints; reusing one would collapse the rows to a single upserted row.
HEX64_A = "a" * 64
HEX64_B = "b" * 64
HEX64_C = "c" * 64


class BriefsServiceTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self._original_paths[0],
            data_dir=self._original_paths[1],
            upload_dir=self._original_paths[2],
            db_path=self._original_paths[3],
            schema_path=self._original_paths[4],
        )
        self._temp.cleanup()

    def test_save_then_get_round_trips_full_record(self) -> None:
        with db.get_db() as conn:
            summary = briefs.save_brief(
                conn,
                draft="Motion to Dismiss\n\nThe statute applies.",
                fingerprint=HEX64,
                response=SAMPLE_RESPONSE,
                cert=SAMPLE_CERT,
                seal_state="sealed",
                title="My Motion",
            )
            detail = briefs.get_brief(conn, summary["id"])

        self.assertIsNotNone(detail)
        assert detail is not None  # narrow for the type checker
        self.assertEqual(detail["title"], "My Motion")
        self.assertEqual(detail["fingerprint"], HEX64)
        self.assertEqual(detail["seal_state"], "sealed")
        self.assertEqual(detail["draft"], "Motion to Dismiss\n\nThe statute applies.")
        # JSON blobs deserialize to the exact structures that went in.
        self.assertEqual(detail["response"], SAMPLE_RESPONSE)
        self.assertEqual(detail["cert"], SAMPLE_CERT)

    def test_list_returns_summaries_without_blobs(self) -> None:
        with db.get_db() as conn:
            briefs.save_brief(conn, draft="A", fingerprint=HEX64_A, response=SAMPLE_RESPONSE)
            briefs.save_brief(conn, draft="B", fingerprint=HEX64_B, response=SAMPLE_RESPONSE)
            listed = briefs.list_briefs(conn)

        self.assertEqual(len(listed), 2)
        for summary in listed:
            self.assertEqual(
                set(summary.keys()),
                {"id", "title", "fingerprint", "seal_state", "created_at", "updated_at"},
            )
            # The heavy fields never appear in the list path.
            self.assertNotIn("draft", summary)
            self.assertNotIn("response", summary)
            self.assertNotIn("cert", summary)

    def test_list_surfaces_cracked_seal_when_draft_drifts(self) -> None:
        # SM-V8 the live ledger: a sealed brief is re-verified per read. One whose
        # stored draft still hashes to its sealed fingerprint stays "sealed"; one
        # whose draft drifted from the fingerprint (tampering, corruption,
        # migration) surfaces as "cracked". The integrity state is derived per
        # read and never persisted, and only a sealed brief can crack.
        intact_draft = "The statute applies as written."
        intact_fp = hashlib.sha256(intact_draft.encode("utf-8")).hexdigest()
        with db.get_db() as conn:
            intact = briefs.save_brief(
                conn,
                draft=intact_draft,
                fingerprint=intact_fp,
                response=SAMPLE_RESPONSE,
                seal_state="sealed",
            )
            drifted = briefs.save_brief(
                conn,
                draft="A different draft than the one that was sealed.",
                fingerprint=HEX64_B,  # does not hash the draft -> drift
                response=SAMPLE_RESPONSE,
                seal_state="sealed",
            )
            unsealed = briefs.save_brief(
                conn,
                draft="An unsealed working draft.",
                fingerprint=HEX64_C,  # mismatched, but unsealed never cracks
                response=SAMPLE_RESPONSE,
            )
            listed = {row["id"]: row["seal_state"] for row in briefs.list_briefs(conn)}
            # The stored state is untouched; "cracked" is render-derived only.
            stored = briefs.get_brief(conn, drifted["id"])
            assert stored is not None
            self.assertEqual(stored["seal_state"], "sealed")

        self.assertEqual(listed[intact["id"]], "sealed")
        self.assertEqual(listed[drifted["id"]], "cracked")
        self.assertEqual(listed[unsealed["id"]], "unsealed")

    def test_list_orders_most_recent_first(self) -> None:
        with db.get_db() as conn:
            a = briefs.save_brief(conn, draft="A", fingerprint=HEX64_A, response={})
            b = briefs.save_brief(conn, draft="B", fingerprint=HEX64_B, response={})
            c = briefs.save_brief(conn, draft="C", fingerprint=HEX64_C, response={})
            # Pin created_at to known, distinct values so the ORDER BY is
            # tested deterministically instead of depending on wall-clock
            # microsecond resolution between sub-millisecond saves.
            conn.execute(
                "UPDATE briefs SET created_at = ? WHERE id = ?",
                ("2026-01-01T00:00:00+00:00", a["id"]),
            )
            conn.execute(
                "UPDATE briefs SET created_at = ? WHERE id = ?",
                ("2026-01-02T00:00:00+00:00", b["id"]),
            )
            conn.execute(
                "UPDATE briefs SET created_at = ? WHERE id = ?",
                ("2026-01-03T00:00:00+00:00", c["id"]),
            )
            conn.commit()
            listed = briefs.list_briefs(conn)

        self.assertEqual([row["id"] for row in listed], [c["id"], b["id"], a["id"]])

    def test_list_tiebreak_uses_insertion_order_on_equal_created_at(self) -> None:
        # When two briefs share an identical created_at, the list must still be
        # deterministically most-recent-first. The tiebreak is rowid DESC
        # (insertion order), not the random uuid id, so the later-saved brief
        # always sorts first.
        with db.get_db() as conn:
            a = briefs.save_brief(conn, draft="A", fingerprint=HEX64_A, response={})
            b = briefs.save_brief(conn, draft="B", fingerprint=HEX64_B, response={})
            c = briefs.save_brief(conn, draft="C", fingerprint=HEX64_C, response={})
            conn.execute("UPDATE briefs SET created_at = ?", ("2026-01-01T00:00:00+00:00",))
            conn.commit()
            listed = briefs.list_briefs(conn)

        # Insertion order a, b, c -> most-recent-first is c, b, a.
        self.assertEqual([row["id"] for row in listed], [c["id"], b["id"], a["id"]])

    def test_delete_removes_then_is_idempotent(self) -> None:
        with db.get_db() as conn:
            summary = briefs.save_brief(
                conn, draft="To be deleted", fingerprint=HEX64, response=SAMPLE_RESPONSE
            )
            brief_id = summary["id"]

            self.assertTrue(briefs.delete_brief(conn, brief_id))
            self.assertIsNone(briefs.get_brief(conn, brief_id))
            # Deleting again is a clean False, not an error.
            self.assertFalse(briefs.delete_brief(conn, brief_id))

    def test_get_unknown_id_returns_none(self) -> None:
        with db.get_db() as conn:
            self.assertIsNone(briefs.get_brief(conn, "does-not-exist"))

    def test_empty_draft_is_rejected(self) -> None:
        with db.get_db() as conn:
            with self.assertRaises(HTTPException) as ctx:
                briefs.save_brief(
                    conn, draft="   \n  ", fingerprint=HEX64, response=SAMPLE_RESPONSE
                )
            self.assertEqual(ctx.exception.status_code, 400)

    def test_title_derived_from_first_nonempty_line(self) -> None:
        with db.get_db() as conn:
            summary = briefs.save_brief(
                conn,
                draft="\n\n   Motion to Compel Discovery\nThe body follows here.",
                fingerprint=HEX64,
                response=SAMPLE_RESPONSE,
            )
        self.assertEqual(summary["title"], "Motion to Compel Discovery")

    def test_explicit_title_wins_over_derivation(self) -> None:
        with db.get_db() as conn:
            summary = briefs.save_brief(
                conn,
                draft="First line would be the title",
                fingerprint=HEX64,
                response=SAMPLE_RESPONSE,
                title="  Operator Title  ",
            )
        self.assertEqual(summary["title"], "Operator Title")

    def test_cracked_and_unknown_seal_states_coerce_to_unsealed(self) -> None:
        with db.get_db() as conn:
            cracked = briefs.save_brief(
                conn,
                draft="A",
                fingerprint=HEX64_A,
                response=SAMPLE_RESPONSE,
                seal_state="cracked",
            )
            garbage = briefs.save_brief(
                conn,
                draft="B",
                fingerprint=HEX64_B,
                response=SAMPLE_RESPONSE,
                seal_state="banana",
            )
            sealed = briefs.save_brief(
                conn,
                draft="C",
                fingerprint=HEX64_C,
                response=SAMPLE_RESPONSE,
                seal_state="sealed",
            )
        # "cracked" is render-derived and must never be persisted.
        self.assertEqual(cracked["seal_state"], "unsealed")
        self.assertEqual(garbage["seal_state"], "unsealed")
        self.assertEqual(sealed["seal_state"], "sealed")

    def test_cert_none_round_trips_as_none(self) -> None:
        with db.get_db() as conn:
            summary = briefs.save_brief(
                conn, draft="No cert yet", fingerprint=HEX64, response=SAMPLE_RESPONSE, cert=None
            )
            detail = briefs.get_brief(conn, summary["id"])
        assert detail is not None
        self.assertIsNone(detail["cert"])

    def test_saving_same_fingerprint_twice_upserts_one_row_last_write_wins(self) -> None:
        # Saving the same draft fingerprint again updates the existing row
        # rather than adding a card. The second save's seal_state + response
        # win (last write wins), and the Shelf still shows exactly one brief.
        first_response = {"draft_text": "first", "claims": []}
        second_response = {"draft_text": "second", "claims": [{"id": 9}]}
        # A real content fingerprint (sha256 of the draft), so the sealed row
        # passes the SM-V8 integrity re-check and lists as "sealed", not cracked.
        same_fp = hashlib.sha256(b"Same draft").hexdigest()
        with db.get_db() as conn:
            briefs.save_brief(
                conn,
                draft="Same draft",
                fingerprint=same_fp,
                response=first_response,
                seal_state="unsealed",
            )
            second = briefs.save_brief(
                conn,
                draft="Same draft",
                fingerprint=same_fp,
                response=second_response,
                seal_state="sealed",
            )
            listed = briefs.list_briefs(conn)
            detail = briefs.get_brief(conn, second["id"])

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["seal_state"], "sealed")
        assert detail is not None
        self.assertEqual(detail["response"], second_response)

    def test_save_then_seal_keeps_id_and_created_at_bumps_updated_at(self) -> None:
        # The save-then-seal path the UI uses: save unsealed, then re-save the
        # same fingerprint sealed. One row, seal_state flips to "sealed", id and
        # created_at are preserved from the first save, updated_at advances.
        with db.get_db() as conn:
            first = briefs.save_brief(
                conn,
                draft="Brief to be sealed",
                fingerprint=HEX64_A,
                response=SAMPLE_RESPONSE,
                seal_state="unsealed",
            )
            # Pin created_at + updated_at to a known past instant so the bump is
            # observable without depending on sub-millisecond wall-clock deltas.
            past = "2026-01-01T00:00:00+00:00"
            conn.execute(
                "UPDATE briefs SET created_at = ?, updated_at = ? WHERE id = ?",
                (past, past, first["id"]),
            )
            conn.commit()

            second = briefs.save_brief(
                conn,
                draft="Brief to be sealed",
                fingerprint=HEX64_A,
                response=SAMPLE_RESPONSE,
                seal_state="sealed",
            )
            listed = briefs.list_briefs(conn)

        self.assertEqual(len(listed), 1)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["seal_state"], "sealed")
        # created_at preserved from the first save, updated_at bumped past it.
        self.assertEqual(second["created_at"], past)
        self.assertNotEqual(second["updated_at"], past)

    def test_different_fingerprints_stay_two_rows(self) -> None:
        # The no-collapse guard: distinct fingerprints are distinct briefs even
        # when every other field matches.
        with db.get_db() as conn:
            briefs.save_brief(
                conn, draft="Same text", fingerprint=HEX64_A, response=SAMPLE_RESPONSE
            )
            briefs.save_brief(
                conn, draft="Same text", fingerprint=HEX64_B, response=SAMPLE_RESPONSE
            )
            listed = briefs.list_briefs(conn)

        self.assertEqual(len(listed), 2)
        self.assertEqual({row["fingerprint"] for row in listed}, {HEX64_A, HEX64_B})


if __name__ == "__main__":
    unittest.main()
