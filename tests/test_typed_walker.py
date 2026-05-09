"""Walker unit tests — exercise the (NodeItem, level) → TypedNode mapping.

These tests use minimal duck-typed stand-ins for Docling's NodeItem so
they run in seconds without invoking the Docling pipeline. The walker
contract is documented at the top of services/ingestion/typed_walker.py.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Iterable

from services.ingestion.typed_walker import DOCLING_TYPE_MAP, TypedNode, walk


@dataclass
class _Label:
    value: str


@dataclass
class _Prov:
    page_no: int | None = None


class _Item:
    """Duck-typed Docling NodeItem stand-in with the four fields the walker reads."""

    def __init__(
        self,
        label: str,
        text: str,
        *,
        level: int = 1,
        page: int | None = None,
    ) -> None:
        self.label = _Label(label)
        self.text = text
        self.level = level
        self.prov = [_Prov(page_no=page)] if page is not None else []


class _FakeDoc:
    def __init__(self, items: Iterable[_Item]) -> None:
        self._items = list(items)

    def iterate_items(self):
        for item in self._items:
            yield item, 0  # walker reads level from the element, not from the tuple


class TypedWalkerTests(unittest.TestCase):
    def test_empty_document_yields_no_nodes(self) -> None:
        nodes = walk(_FakeDoc([]))
        self.assertEqual(nodes, [])

    def test_skips_blank_text_without_advancing_reading_order(self) -> None:
        nodes = walk(
            _FakeDoc(
                [
                    _Item("text", "First paragraph"),
                    _Item("text", "   "),  # whitespace-only, must be skipped
                    _Item("text", "Second paragraph"),
                ]
            )
        )
        self.assertEqual([n.reading_order for n in nodes], [0, 1])
        self.assertEqual([n.verbatim_text for n in nodes], ["First paragraph", "Second paragraph"])

    def test_label_to_node_type_mapping_covers_seven_retrievable_kinds(self) -> None:
        # Every retrievable type lands somewhere in DOCLING_TYPE_MAP.
        retrievable = {"heading", "body", "list_item", "caption", "footnote", "equation"}
        for target in retrievable:
            with self.subTest(target=target):
                self.assertIn(target, DOCLING_TYPE_MAP.values())

    def test_unknown_label_falls_back_to_body(self) -> None:
        nodes = walk(_FakeDoc([_Item("never-heard-of-this-label", "fallback text")]))
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].node_type, "body")

    def test_heading_path_tracks_section_stack(self) -> None:
        nodes = walk(
            _FakeDoc(
                [
                    _Item("section_header", "Chapter 1", level=1),
                    _Item("text", "intro paragraph"),
                    _Item("section_header", "1.1 Photosynthesis", level=2),
                    _Item("text", "sub-section paragraph"),
                    _Item("section_header", "Chapter 2", level=1),  # pops 1.1
                    _Item("text", "chapter-two paragraph"),
                ]
            )
        )
        paths = {n.verbatim_text: n.heading_path for n in nodes}
        self.assertEqual(paths["intro paragraph"], "Chapter 1")
        self.assertEqual(paths["sub-section paragraph"], "Chapter 1 > 1.1 Photosynthesis")
        self.assertEqual(paths["chapter-two paragraph"], "Chapter 2")

    def test_char_offsets_index_a_canonical_text_with_double_newline_separators(self) -> None:
        a, b = "alpha", "beta"
        nodes = walk(_FakeDoc([_Item("text", a), _Item("text", b)]))
        self.assertEqual(nodes[0].char_start, 0)
        self.assertEqual(nodes[0].char_end, len(a))
        self.assertEqual(nodes[1].char_start, len(a) + 2)  # +2 for "\n\n"
        self.assertEqual(nodes[1].char_end, nodes[1].char_start + len(b))
        # Reconstructed canonical text matches what the walker computed
        # against — important for PR 2 citation grounding.
        canonical = a + "\n\n" + b
        for node in nodes:
            self.assertEqual(canonical[node.char_start : node.char_end], node.verbatim_text)

    def test_page_pulled_from_first_provenance_entry(self) -> None:
        nodes = walk(
            _FakeDoc(
                [
                    _Item("text", "no provenance"),
                    _Item("text", "page two", page=2),
                ]
            )
        )
        self.assertIsNone(nodes[0].page)
        self.assertEqual(nodes[1].page, 2)

    def test_typed_node_is_frozen_dataclass(self) -> None:
        node = TypedNode(
            node_type="body",
            heading_path="",
            page=None,
            char_start=0,
            char_end=5,
            verbatim_text="hello",
            parent_block_id=None,
            reading_order=0,
        )
        with self.assertRaises(Exception):
            node.node_type = "heading"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
