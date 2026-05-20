"""Walker unit tests — exercise the (NodeItem, level) → TypedNode mapping.

These tests use minimal duck-typed stand-ins for Docling's NodeItem so
they run in seconds without invoking the Docling pipeline. The walker
contract is documented at the top of services/ingestion/typed_walker.py.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Iterable

from services.ingestion.typed_walker import DOCLING_TYPE_MAP, TypedNode, stitch_walks, walk


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


class StitchWalksTests(unittest.TestCase):
    """`stitch_walks` merges per-page-range slice walks into one list.

    A very large PDF is parsed in page-range slices to bound memory; each
    slice is walked independently and restarts reading_order / char
    offsets at 0. `stitch_walks` must produce exactly the contiguous list
    a one-shot `walk` would have.
    """

    def test_no_slices_yields_empty_list(self) -> None:
        self.assertEqual(stitch_walks([]), [])

    def test_single_slice_is_returned_unchanged(self) -> None:
        only = walk(_FakeDoc([_Item("text", "alpha"), _Item("text", "beta")]))
        self.assertEqual(stitch_walks([only]), only)

    def test_reading_order_is_contiguous_across_slices(self) -> None:
        slice_a = walk(_FakeDoc([_Item("text", "a"), _Item("text", "b")]))
        slice_b = walk(_FakeDoc([_Item("text", "c"), _Item("text", "d"), _Item("text", "e")]))
        stitched = stitch_walks([slice_a, slice_b])
        self.assertEqual([n.reading_order for n in stitched], [0, 1, 2, 3, 4])

    def test_char_offsets_index_one_global_canonical_text(self) -> None:
        # Each slice walks in isolation (offsets restart at 0); the stitch
        # must shift them so they index the joined canonical document.
        texts_a, texts_b = ["alpha", "beta"], ["gamma", "delta"]
        slice_a = walk(_FakeDoc([_Item("text", t) for t in texts_a]))
        slice_b = walk(_FakeDoc([_Item("text", t) for t in texts_b]))
        stitched = stitch_walks([slice_a, slice_b])
        canonical = "\n\n".join(texts_a + texts_b)
        for node in stitched:
            self.assertEqual(canonical[node.char_start : node.char_end], node.verbatim_text)

    def test_empty_slices_contribute_nothing(self) -> None:
        # A page-range slice that parses to no nodes (blank/image pages)
        # must not advance offsets or insert a phantom separator.
        slice_a = walk(_FakeDoc([_Item("text", "alpha")]))
        slice_c = walk(_FakeDoc([_Item("text", "beta")]))
        with_gap = stitch_walks([slice_a, [], slice_c])
        without_gap = stitch_walks([slice_a, slice_c])
        self.assertEqual(with_gap, without_gap)

    def test_stitched_slices_equal_a_one_shot_walk(self) -> None:
        # The gold standard: splitting a document into slices and
        # stitching must reproduce the one-shot walk byte for byte. The
        # split sits between pages so no heading breadcrumb crosses it.
        items = [
            _Item("text", "alpha", page=1),
            _Item("text", "beta", page=1),
            _Item("text", "gamma", page=2),
            _Item("text", "delta", page=2),
            _Item("text", "epsilon", page=3),
        ]
        whole = walk(_FakeDoc(items))
        slice_a = walk(_FakeDoc(items[:2]))
        slice_b = walk(_FakeDoc(items[2:]))
        self.assertEqual(stitch_walks([slice_a, slice_b]), whole)

    def test_page_numbers_pass_through_untouched(self) -> None:
        # Docling page_range yields absolute page numbers, so per-slice
        # `page` is already document-global — the stitch must not shift it.
        slice_a = walk(_FakeDoc([_Item("text", "a", page=58)]))
        slice_b = walk(_FakeDoc([_Item("text", "b", page=61)]))
        stitched = stitch_walks([slice_a, slice_b])
        self.assertEqual([n.page for n in stitched], [58, 61])


if __name__ == "__main__":
    unittest.main()
