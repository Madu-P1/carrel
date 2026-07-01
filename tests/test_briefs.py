"""Tests for services/briefs.py — Shelf persistence round-trips.

Bootstraps a real SQLite database against a temporary directory the way
test_db_migrations.py does, so migration 0024_briefs.sql runs end to end
and the service functions hit actual rows. Each test opens its own
connection; the schema persists in the temp file across connections.
"""

from __future__ import annotations

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
        with db.get_db() as conn:
            briefs.save_brief(
                conn,
                draft="Same draft",
                fingerprint=HEX64_A,
                response=first_response,
                seal_state="unsealed",
            )
            second = briefs.save_brief(
                conn,
                draft="Same draft",
                fingerprint=HEX64_A,
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

    def test_sealed_brief_returns_original_fingerprint_on_reread(self) -> None:
        # Locks the seal-immutability invariant from the persistence side:
        # once a brief is sealed, get_brief must return the exact
        # fingerprint, certification, and seal_state captured at seal time
        # on every later read — never a freshly recomputed value. Mirrors
        # the guarantee useVerify.ts's markSealed already enforces
        # client-side.
        with db.get_db() as conn:
            briefs.save_brief(
                conn,
                draft="Brief to be sealed",
                fingerprint=HEX64_A,
                response=SAMPLE_RESPONSE,
                seal_state="unsealed",
            )
            sealed = briefs.save_brief(
                conn,
                draft="Brief to be sealed",
                fingerprint=HEX64_A,
                response=SAMPLE_RESPONSE,
                cert=SAMPLE_CERT,
                seal_state="sealed",
            )
            sealed_detail = briefs.get_brief(conn, sealed["id"])

        assert sealed_detail is not None
        original_fingerprint = sealed_detail["fingerprint"]
        original_cert = sealed_detail["cert"]
        original_seal_state = sealed_detail["seal_state"]
        self.assertEqual(original_seal_state, "sealed")

        # Fresh read on a fresh connection must reproduce the sealed values
        # byte-for-byte — never a freshly-minted fingerprint or a new
        # certification.
        with db.get_db() as conn:
            reread = briefs.get_brief(conn, sealed["id"])

        assert reread is not None
        self.assertEqual(reread["fingerprint"], original_fingerprint)
        self.assertEqual(reread["cert"], original_cert)
        self.assertEqual(reread["seal_state"], original_seal_state)
        self.assertEqual(reread["seal_state"], "sealed")

    def test_get_brief_on_sealed_row_returns_original_fingerprint_cert_and_seal_state_unchanged_across_reread(
        self,
    ) -> None:
        # Seal-immutability: once a brief is sealed, every later get_brief
        # read must return the EXACT fingerprint, certification, and
        # seal_state captured at seal time — never a freshly re-minted
        # value. This is the server-side half of the guarantee
        # useVerify.ts's markSealed already enforces on the client; a
        # lawyer relies on the persisted certification fingerprint/timestamp
        # staying byte-for-byte stable as evidence.
        with db.get_db() as conn:
            briefs.save_brief(
                conn,
                draft="Brief to be sealed",
                fingerprint=HEX64_A,
                response=SAMPLE_RESPONSE,
                seal_state="unsealed",
            )
            sealed = briefs.save_brief(
                conn,
                draft="Brief to be sealed",
                fingerprint=HEX64_A,
                response=SAMPLE_RESPONSE,
                cert=SAMPLE_CERT,
                seal_state="sealed",
            )
            sealed_detail = briefs.get_brief(conn, sealed["id"])

        assert sealed_detail is not None
        original_fingerprint = sealed_detail["fingerprint"]
        original_cert = sealed_detail["cert"]
        original_seal_state = sealed_detail["seal_state"]
        self.assertEqual(original_seal_state, "sealed")
        self.assertEqual(original_cert, SAMPLE_CERT)

        # Idempotent read: re-reading the same sealed row twice in a row, on
        # the same connection, must not perturb it — each read reproduces
        # the captured values exactly.
        with db.get_db() as conn:
            reread_first = briefs.get_brief(conn, sealed["id"])
            reread_second = briefs.get_brief(conn, sealed["id"])

        assert reread_first is not None
        assert reread_second is not None
        for reread in (reread_first, reread_second):
            self.assertEqual(reread["fingerprint"], original_fingerprint)
            self.assertEqual(reread["cert"], original_cert)
            self.assertEqual(reread["seal_state"], original_seal_state)

        # No cross-contamination: saving an unrelated, different brief in
        # between must not touch the sealed row's persisted values when it
        # is re-fetched afterward.
        with db.get_db() as conn:
            briefs.save_brief(
                conn,
                draft="A completely different brief",
                fingerprint=HEX64_B,
                response=SAMPLE_RESPONSE,
                seal_state="unsealed",
            )
            reread_after_unrelated_save = briefs.get_brief(conn, sealed["id"])

        assert reread_after_unrelated_save is not None
        self.assertEqual(reread_after_unrelated_save["fingerprint"], original_fingerprint)
        self.assertEqual(reread_after_unrelated_save["cert"], original_cert)
        self.assertEqual(reread_after_unrelated_save["seal_state"], original_seal_state)

    def _seal_a_brief(self, conn):
        briefs.save_brief(
            conn,
            draft="Sealed brief body",
            fingerprint=HEX64_A,
            response=SAMPLE_RESPONSE,
            seal_state="unsealed",
        )
        return briefs.save_brief(
            conn,
            draft="Sealed brief body",
            fingerprint=HEX64_A,
            response=SAMPLE_RESPONSE,
            cert=SAMPLE_CERT,
            seal_state="sealed",
        )

    def test_unsealing_a_sealed_brief_is_refused_with_409_and_leaves_it_unchanged(self) -> None:
        # THE seal-immutability invariant (not merely read-stability, which the
        # get_brief re-read tests already cover): once a brief is sealed, a
        # later save_brief on the SAME fingerprint must not un-seal it or
        # overwrite its draft / cert / response. It is refused LOUDLY (409), not
        # silently dropped, so a caller can never believe it modified a sealed,
        # certified brief.
        with db.get_db() as conn:
            sealed = self._seal_a_brief(conn)
            with self.assertRaises(HTTPException) as ctx:
                briefs.save_brief(
                    conn,
                    draft="TAMPERED body",
                    fingerprint=HEX64_A,
                    response={"tampered": True},
                    cert=None,
                    seal_state="unsealed",
                    title="tampered title",
                )
            self.assertEqual(ctx.exception.status_code, 409)
            detail = briefs.get_brief(conn, sealed["id"])

        # The row is untouched: still sealed, original draft + cert + response.
        assert detail is not None
        self.assertEqual(detail["seal_state"], "sealed")
        self.assertEqual(detail["draft"], "Sealed brief body")
        self.assertEqual(detail["cert"], SAMPLE_CERT)
        self.assertEqual(detail["response"], SAMPLE_RESPONSE)

    def test_reseal_is_idempotent_no_op_and_never_overwrites_the_sealed_content(self) -> None:
        # A same-state re-seal (e.g. a network retry of the original seal POST)
        # must NOT 409 and must NOT overwrite the sealed content — even if the
        # retry carries a different (forged) cert. It returns the unchanged
        # sealed summary.
        with db.get_db() as conn:
            sealed = self._seal_a_brief(conn)
            resave = briefs.save_brief(
                conn,
                draft="Sealed brief body",
                fingerprint=HEX64_A,
                response={"forged": True},
                cert={"fingerprint": "b" * 64, "sealed_count": 99},
                seal_state="sealed",
                title="renamed",
            )
            detail = briefs.get_brief(conn, sealed["id"])

        self.assertEqual(resave["id"], sealed["id"])
        self.assertEqual(resave["seal_state"], "sealed")
        assert detail is not None
        # The original sealed cert/response survive the re-seal; the forged
        # cert and renamed title did not take.
        self.assertEqual(detail["cert"], SAMPLE_CERT)
        self.assertEqual(detail["response"], SAMPLE_RESPONSE)

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
