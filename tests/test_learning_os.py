import json
import tempfile
import unittest
from pathlib import Path

import main
from api_models import (
    NoteUpsertRequest,
    ReviewEventRequestV2,
    SessionStartRequest,
    TutorExchangeCreateRequest,
    TutorExchangeEvaluateRequest,
)
from routes.study import review_event
from routes.tutor import evaluate_tutor_exchange, save_note, tutor_exchange
from routes.workspace import complete_session, create_session, workspace_state_v2
from services import documents as document_service
from services.ingestion import ingest_document_record


class LearningOSBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.original_base_dir = main.BASE_DIR
        self.original_data_dir = main.DATA_DIR
        self.original_upload_dir = main.UPLOAD_DIR
        self.original_db_path = main.DB_PATH
        self.original_schema_path = main.SCHEMA_PATH

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        self.clear_seed_data()

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def clear_seed_data(self) -> None:
        with main.get_db() as conn:
            for table in [
                "stale_dependencies",
                "note_evidence",
                "quiz_evidence",
                "flashcard_evidence",
                "artifact_exports",
                "artifact_evidence",
                "artifacts",
                "review_events",
                "mastery_states",
                "session_artifacts",
                "sessions",
                "tutor_exchange_evidence",
                "tutor_exchanges",
                "evidence_references",
                "misconceptions",
                "concept_examples",
                "claims",
                "goals",
                "concept_edges",
                "questions",
                "srs_cards",
                "dialogue_sessions",
                "notes",
                "study_events",
                "concepts",
                "chunks",
                "documents",
                "app_settings",
            ]:
                conn.execute(f"DELETE FROM {table}")
            if conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'chunks_vec'"
            ).fetchone():
                conn.execute("DELETE FROM chunks_vec")
            conn.commit()

    def ingest(self, filename: str, text: str, subject_name: str) -> str:
        with main.get_db() as conn:
            result = ingest_document_record(
                conn=conn,
                filename=filename,
                file_type=Path(filename).suffix.replace(".", "") or "txt",
                extracted_text=text,
                page_count=None,
                subject_name=subject_name,
            )
        return result["doc_id"]

    def first_concept_id(self, doc_id: str) -> str:
        with main.get_db() as conn:
            row = conn.execute(
                "SELECT id FROM concepts WHERE doc_id = ? ORDER BY rowid ASC LIMIT 1",
                (doc_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        return row["id"]

    def first_card_id(self) -> str:
        with main.get_db() as conn:
            row = conn.execute("SELECT id FROM srs_cards ORDER BY rowid ASC LIMIT 1").fetchone()
        self.assertIsNotNone(row)
        return row["id"]

    def test_initialize_database_applies_learning_os_migration(self) -> None:
        with main.get_db() as conn:
            migration = conn.execute(
                "SELECT name FROM schema_migrations WHERE name = '0001_initial.sql'"
            ).fetchone()
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

        self.assertIsNotNone(migration)
        self.assertIn("evidence_references", tables)
        self.assertIn("tutor_exchanges", tables)
        self.assertIn("sessions", tables)
        self.assertIn("mastery_states", tables)

    def test_tutor_exchange_persists_evidence_and_workspace_v2_surfaces_it(self) -> None:
        doc_id = self.ingest(
            "osmosis.txt",
            "Osmosis moves water across a semipermeable membrane. Water moves toward the higher solute concentration.",
            "Biology",
        )
        concept_id = self.first_concept_id(doc_id)

        response = tutor_exchange(
            TutorExchangeCreateRequest(
                question="Explain osmosis with evidence",
                source_scope=[doc_id],
                concept_scope=[concept_id],
                learner_confidence=41,
            )
        )

        self.assertTrue(response["exchange_id"])
        self.assertTrue(response["evidence"])

        workspace = workspace_state_v2(
            source_ids=[doc_id],
            concept_ids=[concept_id],
            surface="tutor",
        )

        self.assertEqual("tutor", workspace["center_canvas"]["surface"])
        self.assertTrue(workspace["right_rail"]["evidence"])
        self.assertTrue(workspace["left_rail"]["sources"])

    def test_session_and_review_flow_generate_mastery_and_summary(self) -> None:
        doc_id = self.ingest(
            "enzymes.txt",
            "Enzymes lower activation energy. Active sites bind substrates and shape the reaction pathway.",
            "Biology",
        )
        concept_id = self.first_concept_id(doc_id)
        card_id = self.first_card_id()

        session = create_session(
            SessionStartRequest(
                objective="Lock in the enzyme mechanism",
                source_scope=[doc_id],
                concept_scope=[concept_id],
            )
        )
        review_result = review_event(
            ReviewEventRequestV2(
                item_id=card_id,
                item_kind="flashcard",
                outcome="missed",
                classification="misconception",
                confidence=30,
                session_id=session["id"],
            )
        )
        summary = complete_session(session["id"])

        self.assertIn("next_due_at", review_result)
        self.assertIn("mastery_state", review_result)
        self.assertIn("mastery_delta", summary)
        self.assertIn("suggested_next_session", summary)
        self.assertTrue(summary["revision_recommendation"])

    def test_document_detail_builds_and_caches_deterministic_concept_options(self) -> None:
        doc_id = self.ingest(
            "transport.txt",
            (
                "Membrane transport moves substances across a membrane. "
                "Diffusion follows concentration gradients. "
                "Osmosis moves water across a semipermeable membrane. "
                "Active transport uses energy to move against a gradient."
            ),
            "Biology",
        )
        with main.get_db() as conn:
            detail = document_service.fetch_document_detail(conn, doc_id, include_chunks=False)
            cache_key = f"{document_service.SELECTOR_CACHE_PREFIX}{doc_id}"
            cached = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (cache_key,),
            ).fetchone()

        self.assertTrue(detail["concept_options"])
        self.assertIsNotNone(cached)
        cached_payload = json.loads(cached["value"])
        self.assertEqual(
            [item["name"] for item in detail["concept_options"]],
            [item["display_name"] for item in cached_payload["options"]],
        )

        with main.get_db() as conn:
            cached_detail = document_service.fetch_document_detail(
                conn, doc_id, include_chunks=False
            )

        self.assertEqual(
            [item["name"] for item in detail["concept_options"]],
            [item["name"] for item in cached_detail["concept_options"]],
        )

    def test_tutor_exchange_evaluation_updates_mastery_and_logs_signal(self) -> None:
        doc_id = self.ingest(
            "osmosis.txt",
            "Osmosis moves water across a semipermeable membrane. Water moves toward higher solute concentration.",
            "Biology",
        )
        concept_id = self.first_concept_id(doc_id)

        exchange = tutor_exchange(
            TutorExchangeCreateRequest(
                question="Explain osmosis",
                source_scope=[doc_id],
                concept_scope=[concept_id],
                learner_confidence=24,
            )
        )
        evaluation = evaluate_tutor_exchange(
            exchange["exchange_id"],
            TutorExchangeEvaluateRequest(
                learner_response="Water moves.",
                mode="examiner",
            ),
        )

        self.assertEqual("omission", evaluation["classification"])
        self.assertIsNotNone(evaluation["mastery_state"])

        with main.get_db() as conn:
            concept_row = conn.execute(
                "SELECT mastery FROM concepts WHERE id = ?",
                (concept_id,),
            ).fetchone()
            study_event = conn.execute(
                """
                SELECT event_type, concept_id, payload
                FROM study_events
                WHERE concept_id = ? AND event_type = 'tutor_exchange_evaluated'
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (concept_id,),
            ).fetchone()

        self.assertIsNotNone(concept_row)
        self.assertLess(float(concept_row["mastery"]), 0.35)
        self.assertIsNotNone(study_event)
        self.assertEqual("tutor_exchange_evaluated", study_event["event_type"])
        self.assertEqual(concept_id, study_event["concept_id"])
        self.assertEqual("omission", json.loads(study_event["payload"])["classification"])

    def test_save_note_updates_mastery_for_the_concept(self) -> None:
        doc_id = self.ingest(
            "osmosis-notes.txt",
            "Osmosis moves water across a semipermeable membrane toward higher solute concentration.",
            "Biology",
        )
        concept_id = self.first_concept_id(doc_id)

        response = save_note(
            NoteUpsertRequest(
                doc_id=doc_id,
                concept_id=concept_id,
                title="Osmosis note",
                content="Osmosis moves water across the membrane toward the side with higher solute concentration.",
                note_type="saved_insight",
            )
        )

        self.assertIsNotNone(response["mastery_state"])
        with main.get_db() as conn:
            concept_row = conn.execute(
                "SELECT mastery FROM concepts WHERE id = ?",
                (concept_id,),
            ).fetchone()

        self.assertIsNotNone(concept_row)
        self.assertGreater(float(concept_row["mastery"]), 0.0)

    def test_delete_document_clears_concept_selector_cache(self) -> None:
        doc_id = self.ingest(
            "cache-cleanup.txt",
            "Catalysts lower activation energy. Enzymes are catalysts used in biological systems.",
            "Chemistry",
        )
        with main.get_db() as conn:
            detail = document_service.fetch_document_detail(conn, doc_id, include_chunks=False)
            self.assertTrue(detail["concept_options"])
            cache_key = f"{document_service.SELECTOR_CACHE_PREFIX}{doc_id}"
            cached = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (cache_key,),
            ).fetchone()
            self.assertIsNotNone(cached)
            deleted = document_service.delete_document_record(conn, doc_id)
            remaining = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (cache_key,),
            ).fetchone()

        self.assertTrue(deleted)
        self.assertIsNone(remaining)


if __name__ == "__main__":
    unittest.main()
