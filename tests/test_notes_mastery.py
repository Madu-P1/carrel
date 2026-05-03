from __future__ import annotations

import sqlite3
import unittest
from unittest import mock

from services.notes.mastery import maybe_update_note_mastery


class NotesMasteryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self) -> None:
        self.conn.close()

    def test_short_note_does_not_update_mastery(self) -> None:
        with mock.patch("services.notes.mastery.mastery_engine.update_mastery_state") as update:
            result = maybe_update_note_mastery(
                self.conn,
                concept_id="concept-1",
                content="Too short.",
                evidence_reference_ids=[],
                goal_id=None,
                session_id=None,
            )

        self.assertIsNone(result)
        update.assert_not_called()

    def test_note_with_evidence_updates_mastery_with_higher_quality(self) -> None:
        with mock.patch(
            "services.notes.mastery.mastery_engine.update_mastery_state",
            return_value={"concept_id": "concept-1"},
        ) as update:
            result = maybe_update_note_mastery(
                self.conn,
                concept_id="concept-1",
                content="This note explains the mechanism and cites evidence from the source.",
                evidence_reference_ids=["ev-1", "ev-2"],
                goal_id="goal-1",
                session_id="session-1",
            )

        self.assertEqual({"concept_id": "concept-1"}, result)
        update.assert_called_once_with(
            self.conn,
            "concept-1",
            goal_id="goal-1",
            session_id="session-1",
            classification="shallow_but_correct",
            learner_confidence=45,
            evidence_quality=0.85,
        )


if __name__ == "__main__":
    unittest.main()
