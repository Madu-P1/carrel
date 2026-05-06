"""Direct tests for `services.document_duplicates`.

Covers the source-hash derivation + duplicate-cluster detection + the
cleanup-with-deleter contract. Uses a real sqlite3 connection over an
in-memory DB so we exercise the actual SQL.
"""

from __future__ import annotations

import sqlite3
import unittest

from services.document_duplicates import (
    cleanup_duplicate_documents,
    compute_document_source_hash,
    find_canonical_duplicate,
    find_duplicate_groups,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Minimal schema — just the columns the module reads/writes. Real
    # migrations add more, but this slice is enough for behavior tests.
    conn.executescript(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            filename TEXT,
            subject_name TEXT,
            file_type TEXT,
            upload_date TEXT,
            page_count INTEGER,
            status TEXT,
            duplicate_of TEXT,
            source_hash TEXT
        );
        CREATE TABLE concepts (
            id TEXT PRIMARY KEY,
            doc_id TEXT
        );
        CREATE TABLE srs_cards (
            id TEXT PRIMARY KEY,
            concept_id TEXT
        );
        """
    )
    return conn


def _insert_doc(
    conn: sqlite3.Connection,
    *,
    id: str,
    source_hash: str | None,
    upload_date: str | None = "2026-01-01",
    duplicate_of: str | None = None,
    status: str | None = None,
    filename: str = "x.pdf",
) -> None:
    conn.execute(
        """INSERT INTO documents (id, filename, source_hash, upload_date,
                                  duplicate_of, status, file_type)
           VALUES (?, ?, ?, ?, ?, ?, 'pdf')""",
        (id, filename, source_hash, upload_date, duplicate_of, status),
    )


class ComputeSourceHashTests(unittest.TestCase):
    def test_asset_path_uses_content_hash_truncated_to_32(self) -> None:
        class FakeAsset:
            content_hash = "a" * 64  # SHA-256 hex length

        result = compute_document_source_hash(asset=FakeAsset())
        self.assertEqual(32, len(result))
        self.assertEqual("a" * 32, result)

    def test_text_path_normalises_whitespace(self) -> None:
        # Two pastes that differ only in trailing whitespace must hash
        # to the same value — the contract for de-dupe of manual text.
        a = compute_document_source_hash(raw_text="hello world")
        b = compute_document_source_hash(raw_text="hello world   ")
        self.assertEqual(a, b)

    def test_empty_inputs_still_return_a_hash(self) -> None:
        # Empty text shouldn't crash; it returns a stable empty-text hash.
        result = compute_document_source_hash(raw_text="")
        self.assertEqual(32, len(result))


class FindDuplicateGroupsTests(unittest.TestCase):
    def test_empty_db_returns_empty_list(self) -> None:
        conn = _connect()
        self.assertEqual([], find_duplicate_groups(conn))

    def test_no_duplicates_returns_empty_list(self) -> None:
        conn = _connect()
        _insert_doc(conn, id="a", source_hash="h1")
        _insert_doc(conn, id="b", source_hash="h2")
        self.assertEqual([], find_duplicate_groups(conn))

    def test_null_source_hash_is_ignored(self) -> None:
        # Pre-hashing legacy rows have NULL source_hash. They must NOT
        # cluster together, even though SQL GROUP BY would otherwise
        # treat them as one group.
        conn = _connect()
        _insert_doc(conn, id="a", source_hash=None)
        _insert_doc(conn, id="b", source_hash=None)
        self.assertEqual([], find_duplicate_groups(conn))

    def test_oldest_upload_wins_canonical_choice(self) -> None:
        conn = _connect()
        _insert_doc(conn, id="newer", source_hash="h", upload_date="2026-03-01")
        _insert_doc(conn, id="older", source_hash="h", upload_date="2026-01-01")
        groups = find_duplicate_groups(conn)
        self.assertEqual(1, len(groups))
        self.assertEqual("older", groups[0]["canonical"]["id"])
        self.assertEqual(["newer"], [d["id"] for d in groups[0]["duplicates"]])

    def test_total_cards_counts_only_duplicates(self) -> None:
        # Cards bound to the canonical doc must NOT be counted in the
        # cleanup preview — only the cards that would actually be
        # deleted (i.e., bound to non-canonical docs).
        conn = _connect()
        _insert_doc(conn, id="canon", source_hash="h", upload_date="2026-01-01")
        _insert_doc(conn, id="dup", source_hash="h", upload_date="2026-02-01")
        conn.execute("INSERT INTO concepts (id, doc_id) VALUES (?, ?)", ("c1", "canon"))
        conn.execute("INSERT INTO concepts (id, doc_id) VALUES (?, ?)", ("c2", "dup"))
        conn.execute("INSERT INTO srs_cards (id, concept_id) VALUES (?, ?)", ("s1", "c1"))
        conn.execute("INSERT INTO srs_cards (id, concept_id) VALUES (?, ?)", ("s2", "c2"))
        conn.execute("INSERT INTO srs_cards (id, concept_id) VALUES (?, ?)", ("s3", "c2"))
        groups = find_duplicate_groups(conn)
        # Two cards on the duplicate, one on the canonical → expect 2.
        self.assertEqual(2, groups[0]["total_cards"])


class CleanupDuplicateDocumentsTests(unittest.TestCase):
    def test_dry_run_does_not_mutate(self) -> None:
        conn = _connect()
        _insert_doc(conn, id="a", source_hash="h", upload_date="2026-01-01")
        _insert_doc(conn, id="b", source_hash="h", upload_date="2026-02-01")
        before = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        result = cleanup_duplicate_documents(conn, dry_run=True, deleter=lambda c, i: True)
        after = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        self.assertTrue(result["dry_run"])
        self.assertEqual(1, result["would_delete"])
        self.assertEqual(before, after, "dry_run must not mutate the documents table")

    def test_deleter_is_invoked_per_duplicate(self) -> None:
        conn = _connect()
        _insert_doc(conn, id="canon", source_hash="h", upload_date="2026-01-01")
        _insert_doc(conn, id="dup1", source_hash="h", upload_date="2026-02-01")
        _insert_doc(conn, id="dup2", source_hash="h", upload_date="2026-03-01")
        called_with: list[str] = []

        def fake_deleter(c: sqlite3.Connection, doc_id: str) -> bool:
            called_with.append(doc_id)
            return True

        result = cleanup_duplicate_documents(conn, deleter=fake_deleter)
        # The canonical (oldest upload) survives; the two newer dupes go.
        self.assertEqual(["dup1", "dup2"], called_with)
        self.assertEqual(2, result["deleted"])
        self.assertFalse(result["dry_run"])


class FindCanonicalDuplicateTests(unittest.TestCase):
    def test_returns_none_for_empty_hash(self) -> None:
        conn = _connect()
        self.assertIsNone(find_canonical_duplicate(conn, ""))

    def test_skips_status_deleted(self) -> None:
        # A previously-aborted ingest with status='deleted' must not
        # block a legitimate re-upload of the same content.
        conn = _connect()
        _insert_doc(conn, id="dead", source_hash="h", status="deleted")
        self.assertIsNone(find_canonical_duplicate(conn, "h"))

    def test_skips_rows_with_duplicate_of_set(self) -> None:
        # A row whose duplicate_of points elsewhere is itself a dupe;
        # only true canonicals (duplicate_of IS NULL) count.
        conn = _connect()
        _insert_doc(conn, id="dup", source_hash="h", duplicate_of="someone")
        self.assertIsNone(find_canonical_duplicate(conn, "h"))

    def test_returns_canonical_row_dict(self) -> None:
        conn = _connect()
        _insert_doc(conn, id="canon", source_hash="h", filename="paper.pdf")
        result = find_canonical_duplicate(conn, "h")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("canon", result["id"])
        self.assertEqual("paper.pdf", result["filename"])


if __name__ == "__main__":
    unittest.main()
