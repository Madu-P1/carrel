"""Pure unit tests for the query-keyword -> node_types router."""

from __future__ import annotations

import unittest

from services.retrieval.node_type_router import (
    NON_CITABLE_NODE_TYPES,
    node_types_for_query,
)


class NodeTypeRouterTests(unittest.TestCase):
    def test_default_query_returns_prose_backbone_only(self) -> None:
        self.assertEqual(
            node_types_for_query("explain photosynthesis"),
            frozenset({"body", "list_item"}),
        )

    def test_empty_query_still_returns_base_set(self) -> None:
        # An empty query should not crash; callers gate retrieval on it.
        self.assertEqual(
            node_types_for_query(""),
            frozenset({"body", "list_item"}),
        )

    def test_table_keywords_pull_in_table_cell(self) -> None:
        for query in ("the table on page 3", "row 4 column 2", "the data in this cell"):
            with self.subTest(query=query):
                self.assertIn("table_cell", node_types_for_query(query))

    def test_figure_keywords_pull_in_caption(self) -> None:
        for query in ("figure 4 caption", "the diagram below", "see chart 2"):
            with self.subTest(query=query):
                self.assertIn("caption", node_types_for_query(query))

    def test_formula_keywords_pull_in_equation(self) -> None:
        self.assertIn("equation", node_types_for_query("the formula for entropy"))
        self.assertIn("equation", node_types_for_query("derive the equation"))

    def test_footnote_keywords_pull_in_footnote(self) -> None:
        for query in ("see footnote 7", "the citation says", "reference list"):
            with self.subTest(query=query):
                self.assertIn("footnote", node_types_for_query(query))

    def test_substring_match_does_not_trigger(self) -> None:
        # "tableau" contains "table" but must not pull in table_cell —
        # the matcher tokenises on whole words.
        self.assertNotIn("table_cell", node_types_for_query("tableau borders"))
        # "referendum" contains "reference" — same protection.
        self.assertNotIn("footnote", node_types_for_query("referendum results"))

    def test_case_insensitive_match(self) -> None:
        self.assertIn("table_cell", node_types_for_query("TABLE on page 3"))
        self.assertIn("caption", node_types_for_query("Figure 4 Caption"))

    def test_multiple_triggers_union(self) -> None:
        types = node_types_for_query("the formula in figure 3 references the table")
        self.assertEqual(
            types,
            frozenset({"body", "list_item", "equation", "caption", "footnote", "table_cell"}),
        )

    def test_header_and_footer_never_returned(self) -> None:
        # Page chrome must never show up — even when the query mentions
        # "header" or "footer". They aren't in the keyword map.
        types = node_types_for_query("the page header on page 3")
        self.assertNotIn("header", types)
        types = node_types_for_query("running footer on every page")
        self.assertNotIn("footer", types)

    def test_headings_never_retrievable(self) -> None:
        # A heading is a section label, not answer content. It must never
        # enter the candidate pool — not even when the query explicitly
        # names a heading, section, or title.
        for query in (
            "explain photosynthesis",
            "what does the heading on page 2 say",
            "the section title for chapter 3",
        ):
            with self.subTest(query=query):
                self.assertNotIn("heading", node_types_for_query(query))

    def test_non_citable_types_are_heading_and_chrome(self) -> None:
        # Single source of truth for the structural (non-answer-bearing)
        # node types shared by retrieval and the tutor citation path.
        self.assertEqual(
            NON_CITABLE_NODE_TYPES,
            frozenset({"heading", "header", "footer"}),
        )
        # None of them is ever produced by the router.
        for query in ("explain photosynthesis", "the table and figure and formula"):
            with self.subTest(query=query):
                self.assertEqual(
                    node_types_for_query(query) & NON_CITABLE_NODE_TYPES,
                    frozenset(),
                )


if __name__ == "__main__":
    unittest.main()
