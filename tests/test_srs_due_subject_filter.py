"""Subject + doc_id filters on fetch_due_cards (S-1).

Verifies the WHERE clause threading: a subject filter only returns
cards joined to a document whose `subject_name` matches; doc_id
filters on `concepts.doc_id`. Both AND together.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path

import db
from services.study import fetch_due_cards

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class SrsDueSubjectFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base_dir = Path(self._tmp.name)
        data_dir = base_dir / "data"
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(MIGRATIONS_SOURCE, base_dir / "migrations", dirs_exist_ok=True)
        (base_dir / "schema.sql").write_text("-- test\n", encoding="utf-8")
        self._original = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        db.configure_paths(
            base_dir=base_dir,
            data_dir=data_dir,
            upload_dir=upload_dir,
            db_path=data_dir / "test.db",
            schema_path=base_dir / "schema.sql",
        )
        self._conn = db.get_db()
        db.apply_migrations(self._conn)
        self._seed_corpus()

    def tearDown(self) -> None:
        self._conn.close()
        self._tmp.cleanup()
        db.configure_paths(
            base_dir=self._original[0],
            data_dir=self._original[1],
            upload_dir=self._original[2],
            db_path=self._original[3],
            schema_path=self._original[4],
        )

    def _seed_corpus(self) -> None:
        # Two docs across two subjects, each with a concept and one
        # SRS card. Cards are due today (NULL due_date).
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('doc-bio', 'photosynthesis.md', 'md', 'ready', 'manual_text', 'Biology')"
        )
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('doc-chem', 'combustion.md', 'md', 'ready', 'manual_text', 'Chemistry')"
        )
        bio_concept = str(uuid.uuid4())
        chem_concept = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO concepts (id, doc_id, name, mastery) VALUES (?, ?, ?, ?)",
            (bio_concept, "doc-bio", "Photosystem II", 0.0),
        )
        self._conn.execute(
            "INSERT INTO concepts (id, doc_id, name, mastery) VALUES (?, ?, ?, ?)",
            (chem_concept, "doc-chem", "Combustion", 0.0),
        )
        bio_card_id = str(uuid.uuid4())
        chem_card_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO srs_cards (id, concept_id, card_type, front, back, state, "
            "stability, difficulty, due_date) "
            "VALUES (?, ?, 'mcq', 'What is photosystem II?', 'splits water', 'new', "
            "1.0, 0.5, ?)",
            (bio_card_id, bio_concept, date.today().isoformat()),
        )
        self._conn.execute(
            "INSERT INTO srs_cards (id, concept_id, card_type, front, back, state, "
            "stability, difficulty, due_date) "
            "VALUES (?, ?, 'mcq', 'What is combustion?', 'methane plus oxygen', 'new', "
            "1.0, 0.5, ?)",
            (chem_card_id, chem_concept, date.today().isoformat()),
        )
        self._conn.commit()

    def test_no_filter_returns_both_cards(self) -> None:
        cards = fetch_due_cards(self._conn)
        self.assertEqual(len(cards), 2)
        subjects = {card["subject_name"] for card in cards}
        self.assertEqual(subjects, {"Biology", "Chemistry"})

    def test_subject_filter_narrows_to_one_subject(self) -> None:
        cards = fetch_due_cards(self._conn, subject="Biology")
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["subject_name"], "Biology")
        self.assertIn("photosystem", cards[0]["front"].lower())

    def test_doc_id_filter_narrows_to_one_doc(self) -> None:
        cards = fetch_due_cards(self._conn, doc_id="doc-chem")
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["document_name"], "combustion.md")

    def test_subject_and_doc_id_filters_and_together(self) -> None:
        # Mismatched filters → empty (Biology + doc-chem cannot AND).
        cards = fetch_due_cards(self._conn, subject="Biology", doc_id="doc-chem")
        self.assertEqual(cards, [])
        # Matching filters → exactly the one row.
        cards = fetch_due_cards(self._conn, subject="Biology", doc_id="doc-bio")
        self.assertEqual(len(cards), 1)

    def test_unknown_subject_returns_empty(self) -> None:
        cards = fetch_due_cards(self._conn, subject="Astronomy")
        self.assertEqual(cards, [])


if __name__ == "__main__":
    unittest.main()
