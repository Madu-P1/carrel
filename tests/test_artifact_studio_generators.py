"""Tests for `services.artifact_studio.generators`.

The 9 markdown generators + 3 item builders + the dispatch table +
the shadow JSON-payload generator. Each generator is template-heavy;
we pin the *contracts* (output shape, item count caps, kind dispatch)
not the exact wording of the templates.
"""

from __future__ import annotations

import unittest

from services.artifact_studio.generators import (
    _KIND_TO_GENERATOR,
    _flashcard_items,
    _hidden_artifact_payload,
    _mock_exam_items,
    _quiz_items,
)


def _concept(id: str, name: str, **extra) -> dict:
    return {
        "id": id,
        "name": name,
        "description": extra.get("description", f"Description of {name}."),
        "study_description": extra.get("study_description"),
        "mastery": extra.get("mastery", 0.5),
        "source_chunk_ids": extra.get("source_chunk_ids", []),
        **{k: v for k, v in extra.items() if k not in {"description", "study_description", "mastery", "source_chunk_ids"}},
    }


class KindToGeneratorTests(unittest.TestCase):
    def test_all_known_kinds_present(self) -> None:
        # A typo'd kind in the orchestrator's fallback path means the
        # request silently degrades. Pin the supported set so a future
        # refactor can't remove a kind without updating callers.
        expected = {
            "study_guide", "briefing", "faq", "flashcards", "quiz",
            "mock_exam", "outline", "summary", "report", "concept_map",
        }
        self.assertEqual(expected, set(_KIND_TO_GENERATOR.keys()))

    def test_concept_map_aliases_outline(self) -> None:
        # concept_map and outline use the same generator function — if
        # someone splits them, they should remember to update tests.
        # We don't assert function identity (it's wrapped in a lambda),
        # but we DO assert both produce non-empty output for the same
        # input.
        c = [_concept("a", "Mitosis")]
        outline = _KIND_TO_GENERATOR["outline"](c, [])
        concept_map = _KIND_TO_GENERATOR["concept_map"](c, [])
        self.assertEqual(outline, concept_map)


class FlashcardItemsTests(unittest.TestCase):
    def test_empty_concepts_produces_empty(self) -> None:
        self.assertEqual([], _flashcard_items([]))

    def test_each_concept_yields_at_least_one_card(self) -> None:
        concepts = [_concept(f"c{i}", f"Concept {i}") for i in range(3)]
        items = _flashcard_items(concepts)
        self.assertGreaterEqual(len(items), 3)

    def test_card_has_question_and_answer_fields(self) -> None:
        concepts = [_concept("c1", "Mitosis")]
        items = _flashcard_items(concepts)
        # Item builders use either `q`/`a` or `front`/`back` shape;
        # `_hidden_artifact_payload` normalises across them.
        first = items[0]
        has_qa = "q" in first and "a" in first
        has_frontback = "front" in first and "back" in first
        self.assertTrue(has_qa or has_frontback)


class QuizItemsTests(unittest.TestCase):
    def test_each_item_has_options(self) -> None:
        concepts = [_concept(f"c{i}", f"Concept {i}") for i in range(4)]
        items = _quiz_items(concepts)
        self.assertGreater(len(items), 0)
        for item in items:
            # The autoplan review noted MCQ should have multiple options.
            options = item.get("options") or item.get("choices") or []
            self.assertGreaterEqual(len(options), 2,
                                     f"quiz item for {item.get('topic')} has too few options")


class MockExamItemsTests(unittest.TestCase):
    def test_pulls_from_topic_map(self) -> None:
        # `_mock_exam_items` consumes the topic-map shape
        # (`title` + `concept_names`) — NOT raw concept lists. This
        # contract drift was the original reason the autoplan eng
        # review demanded orchestrator/generator tests.
        topic_map = [
            {"title": "Cell Division", "concept_names": ["Mitosis", "Meiosis"]},
            {"title": "Energy", "concept_names": ["Photosynthesis"]},
        ]
        items = _mock_exam_items(topic_map)
        self.assertEqual(2, len(items))
        self.assertEqual("essay", items[0]["kind"])
        self.assertIn("Mitosis", items[0]["prompt"])

    def test_skips_topics_with_no_concept_names(self) -> None:
        topic_map = [
            {"title": "Empty"},
            {"title": "Has", "concept_names": ["A"]},
        ]
        items = _mock_exam_items(topic_map)
        self.assertEqual(1, len(items))
        self.assertEqual("Has", items[0]["topic"])


class HiddenArtifactPayloadTests(unittest.TestCase):
    def test_flashcards_uses_deck_items_when_provided(self) -> None:
        # The orchestrator passes a pre-built deck for flashcards;
        # when it does, we MUST honor it and not regenerate.
        concepts = [_concept("c1", "Mitosis")]
        deck_items = [
            {"q": "Q1", "a": "A1", "topic": "Cells", "type": "definition"},
            {"q": "Q2", "a": "A2", "topic": "Cells", "type": "definition"},
        ]
        payload = _hidden_artifact_payload(
            "flashcards", concepts, [], [], custom_prompt=None, deck_items=deck_items,
        )
        self.assertEqual(2, len(payload["items"]))
        self.assertEqual("Q1", payload["items"][0]["front"])

    def test_unknown_kind_falls_through_to_concept_items(self) -> None:
        # The orchestrator already rewrote the kind to study_guide by
        # the time _hidden_artifact_payload is called; this is the
        # default path for non-flashcard / non-quiz / non-mock_exam kinds.
        concepts = [_concept("c1", "Mitosis"), _concept("c2", "Meiosis")]
        payload = _hidden_artifact_payload(
            "study_guide", concepts, [], [], custom_prompt=None,
        )
        self.assertEqual(2, len(payload["items"]))
        kinds = {item["kind"] for item in payload["items"]}
        self.assertEqual({"concept"}, kinds)

    def test_supporting_chunks_capped_at_12(self) -> None:
        # The supporting_chunks slice protects the persisted JSON from
        # blowing up on a 100-chunk grounding bundle.
        chunks = [{"id": f"c{i}", "doc_id": "d", "page_num": i} for i in range(20)]
        payload = _hidden_artifact_payload(
            "study_guide", [_concept("k1", "X")], chunks, [], custom_prompt=None,
        )
        self.assertLessEqual(len(payload["supporting_chunks"]), 12)


if __name__ == "__main__":
    unittest.main()
