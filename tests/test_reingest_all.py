"""Unit tests for script/reingest_all.py per-slice resume helpers (T12).

reingest_all.py parses a very large PDF in page-range slices and persists
each completed slice to a JSON sidecar so a process kill mid-parse resumes
from the last finished slice instead of restarting the whole document.
These tests cover the pure resume bookkeeping — sidecar serialization,
geometry-staleness rejection, atomic writes, and corrupt-file tolerance —
without invoking Docling or a database.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from services.ingestion.typed_walker import TypedNode

# script/ is not a package, so load reingest_all.py by file path.
_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("reingest_all", _ROOT / "script" / "reingest_all.py")
assert _SPEC is not None and _SPEC.loader is not None
reingest_all = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reingest_all)


def _node(reading_order: int, text: str) -> TypedNode:
    return TypedNode(
        node_type="body",
        heading_path="Chapter 1",
        page=reading_order + 1,
        char_start=reading_order * 10,
        char_end=reading_order * 10 + len(text),
        verbatim_text=text,
        parent_block_id=None,
        reading_order=reading_order,
    )


class NodeSerializationTests(unittest.TestCase):
    def test_typed_node_round_trips_through_json(self) -> None:
        # The sidecar stores walked nodes as JSON; the round trip must
        # reproduce the frozen dataclass field for field.
        node = _node(3, "mitosis splits one cell into two")
        restored = reingest_all._node_from_jsonable(
            json.loads(json.dumps(reingest_all._node_to_jsonable(node)))
        )
        self.assertEqual(restored, node)

    def test_optional_fields_survive_the_round_trip(self) -> None:
        # page and parent_block_id are int | None; None must stay None.
        node = TypedNode(
            node_type="heading",
            heading_path="",
            page=None,
            char_start=0,
            char_end=5,
            verbatim_text="alpha",
            parent_block_id=None,
            reading_order=0,
        )
        restored = reingest_all._node_from_jsonable(
            json.loads(json.dumps(reingest_all._node_to_jsonable(node)))
        )
        self.assertEqual(restored, node)


class ResumeSidecarTests(unittest.TestCase):
    def test_save_then_load_round_trips_completed_slices(self) -> None:
        completed = {
            1: [_node(0, "alpha"), _node(1, "beta")],
            2: [_node(2, "gamma")],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reingest-resume-doc.json"
            reingest_all._save_resume(path, "doc", "Biology.pdf", 1480, 60, completed)
            loaded = reingest_all._load_resume(path, 1480, 60)
        self.assertEqual(loaded, completed)

    def test_missing_sidecar_loads_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "absent.json"
            self.assertEqual(reingest_all._load_resume(path, 1480, 60), {})

    def test_stale_page_count_is_rejected(self) -> None:
        # A different page_count means a different file; every slice is
        # re-keyed, so a sidecar from another document must be discarded.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reingest-resume-doc.json"
            reingest_all._save_resume(path, "doc", "Biology.pdf", 1480, 60, {1: [_node(0, "x")]})
            self.assertEqual(reingest_all._load_resume(path, 999, 60), {})

    def test_stale_slice_pages_is_rejected(self) -> None:
        # A different --slice-pages re-keys every slice index, so the
        # recorded slices cannot be reused under the new geometry.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reingest-resume-doc.json"
            reingest_all._save_resume(path, "doc", "Biology.pdf", 1480, 60, {1: [_node(0, "x")]})
            self.assertEqual(reingest_all._load_resume(path, 1480, 10), {})

    def test_corrupt_sidecar_loads_as_empty(self) -> None:
        # A malformed sidecar must be discarded and re-parsed rather than
        # crash the run.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reingest-resume-doc.json"
            path.write_text("{not valid json", encoding="utf-8")
            self.assertEqual(reingest_all._load_resume(path, 1480, 60), {})

    def test_non_dict_sidecar_loads_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reingest-resume-doc.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(reingest_all._load_resume(path, 1480, 60), {})

    def test_save_is_atomic_and_leaves_no_temp_file(self) -> None:
        # _save_resume writes to a temp path then renames; a completed
        # write must leave exactly the sidecar, no .tmp residue.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reingest-resume-doc.json"
            reingest_all._save_resume(path, "doc", "Biology.pdf", 1480, 60, {1: [_node(0, "x")]})
            siblings = sorted(p.name for p in Path(tmp).iterdir())
        self.assertEqual(siblings, ["reingest-resume-doc.json"])

    def test_save_overwrites_a_prior_sidecar_with_more_slices(self) -> None:
        # Each slice re-saves the full completed set; a later save must
        # supersede the earlier one.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reingest-resume-doc.json"
            reingest_all._save_resume(path, "doc", "Biology.pdf", 1480, 60, {1: [_node(0, "a")]})
            reingest_all._save_resume(
                path,
                "doc",
                "Biology.pdf",
                1480,
                60,
                {1: [_node(0, "a")], 2: [_node(1, "b")]},
            )
            loaded = reingest_all._load_resume(path, 1480, 60)
        self.assertEqual(sorted(loaded), [1, 2])


class ResumePathTests(unittest.TestCase):
    def test_resume_path_lives_under_data_migrations(self) -> None:
        path = reingest_all._resume_path("abc-123")
        self.assertEqual(path.parent.name, "migrations")
        self.assertEqual(path.name, "reingest-resume-abc-123.json")


if __name__ == "__main__":
    unittest.main()
