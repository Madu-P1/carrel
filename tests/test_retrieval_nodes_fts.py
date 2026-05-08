"""Integration tests for BM25 search against `node_fts`.

Seeds a tiny document tree of typed nodes, then runs `search_node_fts`
through every option (default, doc_id filter, subject filter,
node_type allowlist) to confirm the SQL composes correctly. No vec0
or fastembed dependencies — pure FTS5.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services.ingestion.persistence import insert_typed_nodes
from services.ingestion.typed_walker import TypedNode
from services.retrieval.nodes_fts import search_node_fts

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _node(
    order: int,
    *,
    node_type: str = "body",
    text: str = "",
    heading_path: str = "",
    page: int | None = 1,
) -> TypedNode:
    return TypedNode(
        node_type=node_type,
        heading_path=heading_path,
        page=page,
        char_start=order * 200,
        char_end=order * 200 + len(text),
        verbatim_text=text,
        parent_block_id=None,
        reading_order=order,
    )


class NodesFtsSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original = (
            db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH,
        )
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root, data_dir=data_dir, upload_dir=upload_dir,
            db_path=data_dir / "test.db", schema_path=root / "schema.sql",
        )
        self._conn = db.get_db()
        db.apply_migrations(self._conn)
        self._seed_corpus()

    def tearDown(self) -> None:
        self._conn.close()
        self._tmp.cleanup()
        db.configure_paths(
            base_dir=self._original[0], data_dir=self._original[1],
            upload_dir=self._original[2], db_path=self._original[3],
            schema_path=self._original[4],
        )

    def _seed_corpus(self) -> None:
        # Two documents in two subjects so we can exercise every filter.
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('doc-bio', 'bio.md', 'md', 'ready', 'manual_text', 'Biology')"
        )
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('doc-chem', 'chem.md', 'md', 'ready', 'manual_text', 'Chemistry')"
        )
        insert_typed_nodes(self._conn, "doc-bio", [
            _node(0, node_type="heading", text="Photosynthesis",
                  heading_path="Photosynthesis"),
            _node(1, node_type="body",
                  text="Plants use chlorophyll to capture light energy from the sun.",
                  heading_path="Photosynthesis"),
            _node(2, node_type="list_item",
                  text="Step one: water is split in the thylakoid membrane",
                  heading_path="Photosynthesis"),
            _node(3, node_type="caption",
                  text="Figure 1: The Calvin cycle and ATP regeneration",
                  heading_path="Photosynthesis"),
            _node(4, node_type="footer",
                  text="Page 12 of biology textbook",  # must NOT match a 'thylakoid' query
                  heading_path=""),
        ])
        insert_typed_nodes(self._conn, "doc-chem", [
            _node(0, node_type="heading", text="Combustion",
                  heading_path="Combustion"),
            _node(1, node_type="body",
                  text="Methane reacts with oxygen to form carbon dioxide and water.",
                  heading_path="Combustion"),
            _node(2, node_type="equation",
                  text="CH4 plus 2O2 yields CO2 plus 2H2O",
                  heading_path="Combustion"),
        ])
        self._conn.commit()

    def test_returns_empty_for_blank_query(self) -> None:
        self.assertEqual(search_node_fts(self._conn, "   "), [])

    def test_basic_match_returns_node_metadata(self) -> None:
        hits = search_node_fts(self._conn, "chlorophyll")
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit.doc_id, "doc-bio")
        self.assertEqual(hit.node_type, "body")
        self.assertEqual(hit.heading_path, "Photosynthesis")
        self.assertEqual(hit.page, 1)
        self.assertIn("chlorophyll", hit.verbatim_text)
        self.assertGreater(hit.score, 0.0)
        # snippet wraps the matched term in << >> via FTS5's snippet().
        self.assertIn("<<", hit.snippet)

    def test_doc_id_filter_scopes_to_one_document(self) -> None:
        # "water" appears in both documents — filter should narrow to one.
        all_hits = search_node_fts(self._conn, "water")
        self.assertGreater(len(all_hits), 1)
        bio_only = search_node_fts(self._conn, "water", doc_ids=["doc-bio"])
        self.assertTrue(bio_only)
        for hit in bio_only:
            self.assertEqual(hit.doc_id, "doc-bio")

    def test_subject_filter_scopes_to_one_subject(self) -> None:
        chem_only = search_node_fts(self._conn, "water", subject_name="Chemistry")
        self.assertTrue(chem_only)
        for hit in chem_only:
            self.assertEqual(hit.doc_id, "doc-chem")

    def test_node_type_filter_excludes_others(self) -> None:
        # Default search would surface the body line. Restrict to caption.
        caption_only = search_node_fts(self._conn, "Calvin", node_types=["caption"])
        self.assertTrue(caption_only)
        for hit in caption_only:
            self.assertEqual(hit.node_type, "caption")

    def test_empty_node_type_allowlist_returns_no_hits(self) -> None:
        # Empty set means "match nothing" — caller mistake, not a footgun.
        self.assertEqual(search_node_fts(self._conn, "chlorophyll", node_types=[]), [])

    def test_heading_path_is_indexed(self) -> None:
        # Querying by the heading path should still find body nodes
        # under that heading. The FTS5 schema indexes both columns.
        hits = search_node_fts(self._conn, "Photosynthesis")
        # At least the heading row hits; body row may match too.
        node_types = {hit.node_type for hit in hits}
        self.assertIn("heading", node_types)

    def test_footer_is_addressable_when_explicitly_allowed(self) -> None:
        # The router strips header/footer by default, but `search_node_fts`
        # itself respects whatever node_types you pass. This pins the
        # contract: filtering is the router's job, not the search's.
        hits = search_node_fts(
            self._conn, "biology", node_types=["footer"],
        )
        self.assertTrue(hits)
        for hit in hits:
            self.assertEqual(hit.node_type, "footer")


if __name__ == "__main__":
    unittest.main()
