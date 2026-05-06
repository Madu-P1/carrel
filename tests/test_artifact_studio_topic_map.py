"""Tests for `services.artifact_studio.topic_map`.

Pure-function module — no DB I/O. The most important contract here is
the description-based dedup in `_select_focus_concepts` (which the
autoplan eng review flagged as a potential silent-overwrite bug).
"""

from __future__ import annotations

import unittest

from services.artifact_studio.topic_map import (
    _build_topic_map,
    _clean_description,
    _clean_section_label,
    _select_focus_concepts,
)


class CleanSectionLabelTests(unittest.TestCase):
    def test_drops_section_page_slide_prefixes(self) -> None:
        self.assertIsNone(_clean_section_label("Section 3"))
        self.assertIsNone(_clean_section_label("Page 12"))
        self.assertIsNone(_clean_section_label("Slide 7"))

    def test_passes_real_titles(self) -> None:
        self.assertEqual(
            "Mitosis Phases",
            _clean_section_label("Mitosis Phases"),
        )

    def test_drops_overly_long_labels(self) -> None:
        # >12 words is almost certainly body text, not a section title.
        long = " ".join(["word"] * 13)
        self.assertIsNone(_clean_section_label(long))


class CleanDescriptionTests(unittest.TestCase):
    def test_collapses_whitespace_within_sentence(self) -> None:
        # The function runs through `clean_learning_text` (which
        # normalises whitespace + may strip terminal punctuation) and
        # a sentence split. Pin the bits we care about: words preserved,
        # no internal whitespace runs.
        cleaned = _clean_description("  Mitosis   is\n\na process.  ")
        self.assertIn("Mitosis", cleaned)
        self.assertIn("is", cleaned)
        self.assertIn("process", cleaned)
        # No double spaces leak through.
        self.assertNotIn("  ", cleaned)

    def test_dedupes_repeated_word_groups(self) -> None:
        # The dedup is: if the first N tokens equal the next N tokens
        # (for N in 3,2,1), drop the first N. Useful for OCR'd PDFs
        # that repeat headings: "Mitosis Mitosis is a process".
        cleaned = _clean_description("Mitosis Mitosis is a process")
        # The leading repeated word is gone; only one "Mitosis".
        self.assertEqual(1, cleaned.count("Mitosis"))


class SelectFocusConceptsTests(unittest.TestCase):
    def test_returns_empty_for_empty_concepts(self) -> None:
        self.assertEqual([], _select_focus_concepts([], [], limit=10))

    def test_caps_at_limit(self) -> None:
        concepts = [
            {"id": f"c{i}", "name": f"Concept {i}", "description": f"description {i}"}
            for i in range(20)
        ]
        result = _select_focus_concepts(concepts, [], limit=8)
        self.assertEqual(8, len(result))

    def test_dedupe_by_name_lowercase(self) -> None:
        # The seen_names set is keyed by name.lower(); two concepts
        # with case variations should collapse to one.
        concepts = [
            {"id": "a", "name": "Mitosis", "description": "first"},
            {"id": "b", "name": "MITOSIS", "description": "second"},
            {"id": "c", "name": "Meiosis", "description": "third"},
        ]
        result = _select_focus_concepts(concepts, [], limit=10)
        names = [c["name"] for c in result]
        self.assertEqual(2, len(set(name.lower() for name in names)))


class BuildTopicMapTests(unittest.TestCase):
    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual([], _build_topic_map([]))

    def test_groups_concepts_by_topic(self) -> None:
        # Two concepts with the same `topic` collapse into one entry.
        # Output shape (per implementation): list of dicts with keys
        # `title`, `concept_ids`, `concept_names`, `summary`.
        concepts = [
            {"id": "a", "name": "Mitosis", "topic": "Cell Division", "study_description": "x"},
            {"id": "b", "name": "Meiosis", "topic": "Cell Division", "study_description": "y"},
            {"id": "c", "name": "Photosynthesis", "topic": "Energy", "study_description": "z"},
        ]
        topic_map = _build_topic_map(concepts)
        titles = sorted(item["title"] for item in topic_map)
        self.assertEqual(["Cell Division", "Energy"], titles)
        cell_div = next(t for t in topic_map if t["title"] == "Cell Division")
        self.assertEqual(sorted(["a", "b"]), sorted(cell_div["concept_ids"]))


if __name__ == "__main__":
    unittest.main()
