"""Tests for `ai/afm_client.py`. Matches the style of
`tests/test_ollama_client.py`. Mocks subprocess.run via the
`run_subprocess` constructor seam so no real bridge or macOS 26 is
required for the unit suite.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ai.afm_client import AFMAvailability, AFMClient, GroundedChunk, reset_default_afm_client
from ai.router import ClaudeCallResult


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> SimpleNamespace:
    """Minimal stand-in for subprocess.CompletedProcess."""
    return SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)


def _bridge_ok_payload(text: str, **extra: object) -> str:
    payload: dict[str, object] = {
        "ok": True,
        "request_id": "test-id",
        "kind": "request_text",
        "text": text,
        "model": "afm-3b",
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": 412.3,
        "stop_reason": "stop",
        "error_code": None,
        "error_message": None,
        "availability_state": None,
    }
    payload.update(extra)
    return json.dumps(payload)


def _bridge_error_payload(
    error_code: str, error_message: str = "boom", returncode: int = 1
) -> SimpleNamespace:
    payload = {
        "ok": False,
        "request_id": "test-id",
        "kind": "request_text",
        "text": None,
        "model": "afm-3b",
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": 5.0,
        "stop_reason": None,
        "error_code": error_code,
        "error_message": error_message,
        "availability_state": (
            error_code
            if error_code in {"apple_intelligence_not_enabled", "device_not_eligible"}
            else None
        ),
    }
    return _completed(json.dumps(payload), returncode=returncode)


# ----------------------------------------------------------------------
# request_text
# ----------------------------------------------------------------------


class AFMRequestTextTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_default_afm_client()

    def test_request_text_happy_path(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(cmd, input=None, **kwargs):  # type: ignore[no-untyped-def]
            captured["cmd"] = cmd
            captured["input"] = json.loads(input)
            captured["kwargs"] = kwargs
            return _completed(_bridge_ok_payload("Mitosis produces two daughter cells."))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_text(
            request_kind="test.text",
            system="You are a tutor.",
            prompt="What is mitosis?",
        )

        self.assertIsInstance(result, ClaudeCallResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.model, "afm-3b")
        self.assertEqual(result.text, "Mitosis produces two daughter cells.")
        self.assertEqual(result.latency_ms, 412.3)
        self.assertEqual(result.stop_reason, "stop")
        self.assertFalse(result.cache_hit)
        self.assertIsNone(result.input_tokens)

        # Wire-format assertions: kind, system, prompt all flow through.
        self.assertEqual(captured["input"]["kind"], "request_text")
        self.assertEqual(captured["input"]["system"], "You are a tutor.")
        self.assertEqual(captured["input"]["prompt"], "What is mitosis?")
        self.assertIn("request_id", captured["input"])
        self.assertEqual(captured["kwargs"]["check"], False)
        self.assertTrue(captured["kwargs"]["capture_output"])

    def test_request_text_bridge_unavailable_when_binary_missing(self) -> None:
        # Mock find_binary so this test is filesystem-independent.
        # AFMClient(bridge_path=None) falls through to discovery, which
        # finds the real binary on a dev machine where swift build has run.
        with mock.patch("ai.afm_client.find_binary", return_value=None):
            client = AFMClient(bridge_path=None)
        result = client.request_text(request_kind="t", system="", prompt="x")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "bridge_unavailable")
        self.assertIsNone(result.text)

    def test_request_text_surfaces_subprocess_timeout(self) -> None:
        import subprocess as sp

        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise sp.TimeoutExpired(cmd="x", timeout=10)

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_text(request_kind="t.timeout", system="", prompt="x")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "timeout")
        self.assertIn("timed out", (result.error_message or "").lower())

    def test_request_text_surfaces_apple_intelligence_disabled(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _bridge_error_payload(
                "apple_intelligence_not_enabled",
                error_message="Enable Apple Intelligence in System Settings.",
            )

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_text(request_kind="t", system="", prompt="x")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "apple_intelligence_not_enabled")
        self.assertIn("System Settings", result.error_message or "")

    def test_request_text_surfaces_protocol_error_on_exit_64(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(stdout="", returncode=64, stderr="Invalid request JSON on stdin")

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_text(request_kind="t", system="", prompt="x")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "bridge_protocol_error")
        self.assertIn("Invalid request JSON", result.error_message or "")

    def test_request_text_handles_invalid_bridge_stdout(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(stdout="this is not json", returncode=0)

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_text(request_kind="t", system="", prompt="x")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "bridge_invalid_response")


# ----------------------------------------------------------------------
# request_json
# ----------------------------------------------------------------------


class AFMRequestJsonTests(unittest.TestCase):
    def test_request_json_strict_parse(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_ok_payload('{"answer": "mitosis", "confidence": 0.9}'))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_json(
            request_kind="t.json",
            system="return JSON",
            prompt="label this",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"answer": "mitosis", "confidence": 0.9})

    def test_request_json_appends_strict_json_instruction_to_system(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(cmd, input=None, **kwargs):  # type: ignore[no-untyped-def]
            captured["input"] = json.loads(input)
            return _completed(_bridge_ok_payload('{"x": 1}'))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        client.request_json(
            request_kind="t.json.system",
            system="You are a tutor.",
            prompt="x",
        )
        sys_text = captured["input"]["system"]  # type: ignore[index]
        self.assertIn("You are a tutor.", sys_text)
        self.assertIn("Reply with a single JSON object.", sys_text)

    def test_request_json_rescue_parses_prose_wrapped_json(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_ok_payload('Here is the JSON:\n{"x": 1}'))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_json(request_kind="t.rescue", system="return JSON", prompt="label")
        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"x": 1})

    def test_request_json_strips_markdown_fences(self) -> None:
        # AFM 3B often wraps JSON in ```json ... ``` fences. Confirmed
        # in the first real grounded-answer call against AFM where the
        # bare rescue parser failed; this case must keep working.
        fenced = '```json\n{"answer": "mitosis", "confidence": 0.9}\n```'

        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_ok_payload(fenced))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_json(request_kind="t.fenced", system="return JSON", prompt="label")
        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"answer": "mitosis", "confidence": 0.9})

    def test_request_json_strips_markdown_fences_without_language_tag(self) -> None:
        fenced = '```\n{"x": 1}\n```'

        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_ok_payload(fenced))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_json(
            request_kind="t.fenced.notag", system="return JSON", prompt="label"
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"x": 1})

    def test_request_json_handles_trailing_prose_after_brace(self) -> None:
        # Some small models emit `{...} <commentary>` instead of `{...}`.
        # The rescue parser truncates to the matching closing brace.
        trailing = '{"x": 1, "y": "ok"}\n\nThat is my answer.'

        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_ok_payload(trailing))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_json(
            request_kind="t.trailing", system="return JSON", prompt="label"
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"x": 1, "y": "ok"})

    def test_request_json_falls_back_on_unparseable(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_ok_payload("not json at all"))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_json(
            request_kind="t.json.fallback",
            system="",
            prompt="",
            fallback={"ok": False, "reason": "no parse"},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_json")
        self.assertEqual(result.json_payload, {"ok": False, "reason": "no parse"})

    def test_request_json_preserves_bridge_error(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _bridge_error_payload("apple_intelligence_not_enabled")

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_json(
            request_kind="t",
            system="",
            prompt="",
            fallback={"ok": False},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "apple_intelligence_not_enabled")
        # Fallback gets attached even when the bridge surfaced its own error.
        self.assertEqual(result.json_payload, {"ok": False})


# ----------------------------------------------------------------------
# request_tool_call
# ----------------------------------------------------------------------


class AFMRequestToolCallTests(unittest.TestCase):
    TOOL = {
        "name": "submit_grounded_answer",
        "description": "Return a grounded answer payload.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "claims": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["summary", "claims"],
        },
    }

    def test_request_tool_call_prepends_tool_preamble(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(cmd, input=None, **kwargs):  # type: ignore[no-untyped-def]
            captured["input"] = json.loads(input)
            return _completed(_bridge_ok_payload('{"summary": "ok", "claims": []}'))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_tool_call(
            request_kind="tutor.grounded_answer",
            system="You are Einstein.",
            prompt="Explain mitosis.",
            tool=self.TOOL,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"summary": "ok", "claims": []})
        sys_text = captured["input"]["system"]  # type: ignore[index]
        self.assertIn("submit_grounded_answer", sys_text)
        self.assertIn("grounded answer", sys_text.lower())
        self.assertIn("You are Einstein.", sys_text)

    def test_request_tool_call_rejects_invalid_schema(self) -> None:
        client = AFMClient(bridge_path=Path("/fake/EinsteinAFMBridge"))
        result = client.request_tool_call(
            request_kind="t",
            system="",
            prompt="",
            tool={"name": "x", "description": "", "input_schema": "not a dict"},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_tool_schema")

    def test_request_tool_call_rejects_non_dict_tool(self) -> None:
        client = AFMClient(bridge_path=Path("/fake/EinsteinAFMBridge"))
        result = client.request_tool_call(
            request_kind="t",
            system="",
            prompt="",
            tool="not a dict",  # type: ignore[arg-type]
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_tool_schema")

    def test_request_tool_call_invalid_json_response(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_ok_payload("not json"))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_tool_call(
            request_kind="t",
            system="",
            prompt="",
            tool=self.TOOL,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_json")


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------


class AFMConfigTests(unittest.TestCase):
    def test_timeout_from_env_var(self) -> None:
        with mock.patch.dict(os.environ, {"AFM_TIMEOUT_SECONDS": "45"}, clear=False):
            client = AFMClient(bridge_path=Path("/fake/EinsteinAFMBridge"))
        self.assertEqual(client.timeout_seconds, 45.0)

    def test_timeout_explicit_constructor_arg_wins_over_env(self) -> None:
        with mock.patch.dict(os.environ, {"AFM_TIMEOUT_SECONDS": "45"}, clear=False):
            client = AFMClient(
                bridge_path=Path("/fake/EinsteinAFMBridge"),
                timeout_seconds=12.0,
            )
        self.assertEqual(client.timeout_seconds, 12.0)

    def test_invalid_timeout_env_falls_back_to_default(self) -> None:
        with mock.patch.dict(os.environ, {"AFM_TIMEOUT_SECONDS": "not-a-number"}, clear=False):
            client = AFMClient(bridge_path=Path("/fake/EinsteinAFMBridge"))
        self.assertEqual(client.timeout_seconds, 120.0)

    def test_model_for_task_always_returns_afm_3b(self) -> None:
        client = AFMClient(bridge_path=Path("/fake/EinsteinAFMBridge"))
        self.assertEqual(client.model_for_task("fast"), "afm-3b")
        self.assertEqual(client.model_for_task("balanced"), "afm-3b")
        self.assertEqual(client.model_for_task("deep"), "afm-3b")

    def test_ai_enabled_requires_bridge_path(self) -> None:
        # Mock find_binary so this test is filesystem-independent.
        with mock.patch("ai.afm_client.find_binary", return_value=None):
            self.assertFalse(AFMClient(bridge_path=None).ai_enabled())
        self.assertTrue(AFMClient(bridge_path=Path("/fake/EinsteinAFMBridge")).ai_enabled())


# ----------------------------------------------------------------------
# request_grounded_answer (@Generable path)
# ----------------------------------------------------------------------


def _bridge_grounded_payload(
    answer: str,
    supporting_chunks: list[int],
    unsupported_claims: list[str] | None = None,
    *,
    request_id: str = "test-id",
    latency_ms: float = 1500.0,
) -> str:
    """JSON that mimics the bridge's response shape for the
    request_grounded_answer kind. The bridge sets `text=None` and
    populates `structured.grounded_answer`."""
    return json.dumps(
        {
            "ok": True,
            "request_id": request_id,
            "kind": "request_grounded_answer",
            "text": None,
            "structured": {
                "grounded_answer": {
                    "answer": answer,
                    "supporting_chunks": supporting_chunks,
                    "unsupported_claims": unsupported_claims or [],
                },
            },
            "model": "afm-3b",
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": latency_ms,
            "stop_reason": "stop",
            "error_code": None,
            "error_message": None,
            "availability_state": None,
        }
    )


_SAMPLE_CHUNKS = [
    GroundedChunk(
        chunk_id="c1",
        doc_id="biology.pdf",
        page_num=12,
        text=(
            "Mitosis is the process by which a single eukaryotic cell divides "
            "into two genetically identical daughter cells. It consists of five "
            "phases: prophase, prometaphase, metaphase, anaphase, and telophase."
        ),
    ),
    GroundedChunk(
        chunk_id="c2",
        doc_id="biology.pdf",
        page_num=14,
        text=(
            "During metaphase, chromosomes align at the cell equator. "
            "In anaphase, sister chromatids are pulled to opposite poles of the cell."
        ),
    ),
    GroundedChunk(
        chunk_id="c3",
        doc_id="biology.pdf",
        page_num=15,
        text="Telophase begins as the chromosomes reach opposite poles.",
    ),
]


class AFMRequestGroundedAnswerTests(unittest.TestCase):
    def test_happy_path_returns_tutor_schema(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(cmd, input=None, **kwargs):  # type: ignore[no-untyped-def]
            captured["input"] = json.loads(input)
            return _completed(
                _bridge_grounded_payload(
                    answer="In anaphase, sister chromatids are pulled to opposite poles of the cell.",
                    supporting_chunks=[2],
                )
            )

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_grounded_answer(
            request_kind="tutor.grounded_answer",
            system="Answer using only the chunks.",
            question="What happens in anaphase?",
            chunks=_SAMPLE_CHUNKS,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.model, "afm-3b")
        # Bridge was called with the new kind + greedy temperature.
        self.assertEqual(captured["input"]["kind"], "request_grounded_answer")
        self.assertEqual(captured["input"]["temperature"], 0.0)
        # Prompt contains numbered chunks.
        self.assertIn("[Chunk 1]", captured["input"]["prompt"])
        self.assertIn("[Chunk 2]", captured["input"]["prompt"])
        self.assertIn("Question: What happens in anaphase?", captured["input"]["prompt"])

        # json_payload matches the tutor schema.
        payload = result.json_payload
        self.assertIsInstance(payload, dict)
        self.assertIn("summary", payload)
        self.assertIn("claims", payload)
        self.assertIn("unsupported_spans", payload)
        self.assertEqual(len(payload["claims"]), 1)
        claim = payload["claims"][0]
        self.assertEqual(len(claim["citations"]), 1)
        citation = claim["citations"][0]
        self.assertEqual(citation["chunk_index"], 2)
        # Quote must be verbatim from chunk 2.
        chunk_2_text = _SAMPLE_CHUNKS[1].text
        self.assertIn(citation["quote"].rstrip("…").rstrip(), chunk_2_text)

    def test_rejects_empty_chunks(self) -> None:
        client = AFMClient(bridge_path=Path("/fake/EinsteinAFMBridge"))
        result = client.request_grounded_answer(
            request_kind="t",
            system="",
            question="anything",
            chunks=[],
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "empty_chunks")

    def test_filters_out_of_range_chunk_indices(self) -> None:
        # Model claims chunk 99 supports the answer; this should not
        # crash the response builder or fabricate a citation. The
        # answer text overlaps with chunk 2 so the ungrounded guard
        # does not trip; this isolates the index-filtering behaviour.
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(
                _bridge_grounded_payload(
                    answer="During anaphase sister chromatids are pulled to opposite poles.",
                    supporting_chunks=[2, 99, 0, -1],
                )
            )

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_grounded_answer(
            request_kind="t",
            system="",
            question="q?",
            chunks=_SAMPLE_CHUNKS,
        )
        self.assertTrue(result.ok)
        payload = result.json_payload
        # Only chunk 2 was a valid 1-based index into the 3-chunk list.
        citations = payload["claims"][0]["citations"]
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["chunk_index"], 2)

    def test_propagates_unsupported_claims(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(
                _bridge_grounded_payload(
                    answer="Mitosis produces two daughter cells.",
                    supporting_chunks=[1],
                    unsupported_claims=["The exact duration of mitosis."],
                )
            )

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_grounded_answer(
            request_kind="t",
            system="",
            question="How long does mitosis take?",
            chunks=_SAMPLE_CHUNKS,
        )
        self.assertTrue(result.ok)
        payload = result.json_payload
        self.assertEqual(
            payload["unsupported_spans"],
            ["The exact duration of mitosis."],
        )

    def test_surfaces_bridge_error(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(
                json.dumps(
                    {
                        "ok": False,
                        "request_id": "x",
                        "kind": "request_grounded_answer",
                        "text": None,
                        "structured": None,
                        "model": "afm-3b",
                        "input_tokens": None,
                        "output_tokens": None,
                        "latency_ms": 5.0,
                        "stop_reason": None,
                        "error_code": "apple_intelligence_not_enabled",
                        "error_message": "Enable Apple Intelligence in System Settings.",
                        "availability_state": "apple_intelligence_not_enabled",
                    }
                ),
                returncode=1,
            )

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_grounded_answer(
            request_kind="t",
            system="",
            question="q?",
            chunks=_SAMPLE_CHUNKS,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "apple_intelligence_not_enabled")

    def test_handles_missing_structured_payload(self) -> None:
        # Bridge says ok=true but never populated `structured`. Should
        # not crash; surface a specific error so the tutor can fall back.
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(
                json.dumps(
                    {
                        "ok": True,
                        "request_id": "x",
                        "kind": "request_grounded_answer",
                        "text": None,
                        "structured": None,
                        "model": "afm-3b",
                        "input_tokens": None,
                        "output_tokens": None,
                        "latency_ms": 100.0,
                        "stop_reason": "stop",
                        "error_code": None,
                        "error_message": None,
                        "availability_state": None,
                    }
                )
            )

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.request_grounded_answer(
            request_kind="t",
            system="",
            question="q?",
            chunks=_SAMPLE_CHUNKS,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "bridge_missing_structured")


# ----------------------------------------------------------------------
# probe_availability
# ----------------------------------------------------------------------


def _bridge_availability_payload(state: str) -> str:
    """JSON mimicking the Swift bridge's response to ``kind=="availability"``.

    The bridge (main.swift:328) sets ``ok = state == "available"`` and
    ``error_code = state == "available" ? nil : state``.
    """
    ok = state == "available"
    return json.dumps(
        {
            "ok": ok,
            "request_id": "test-id",
            "kind": "availability",
            "text": None,
            "structured": None,
            "model": "afm-3b",
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": 3.2,
            "stop_reason": None,
            "error_code": None if ok else state,
            "error_message": None,
            "availability_state": state,
        }
    )


class AFMProbeAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_default_afm_client()

    def test_probe_availability_happy_path_available(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(cmd, input=None, **kwargs):  # type: ignore[no-untyped-def]
            captured["input"] = json.loads(input)
            return _completed(_bridge_availability_payload("available"))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.probe_availability()

        self.assertIsInstance(result, AFMAvailability)
        self.assertTrue(result.ok)
        self.assertEqual(result.state, "available")
        self.assertIn("available", result.detail.lower())
        # The bridge is asked with the `availability` kind.
        self.assertEqual(captured["input"]["kind"], "availability")

    def test_probe_availability_device_not_eligible(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_availability_payload("device_not_eligible"))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.probe_availability()
        self.assertFalse(result.ok)
        self.assertEqual(result.state, "device_not_eligible")

    def test_probe_availability_apple_intelligence_not_enabled(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_availability_payload("apple_intelligence_not_enabled"))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.probe_availability()
        self.assertFalse(result.ok)
        self.assertEqual(result.state, "apple_intelligence_not_enabled")
        self.assertTrue(result.detail)

    def test_probe_availability_model_not_ready(self) -> None:
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(_bridge_availability_payload("model_not_ready"))

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.probe_availability()
        self.assertFalse(result.ok)
        self.assertEqual(result.state, "model_not_ready")

    def test_probe_availability_bridge_missing(self) -> None:
        # bridge_path=None and discovery also finds nothing → a dedicated
        # `bridge_missing` state, never a raise, never a subprocess call.
        with mock.patch("ai.afm_client.find_binary", return_value=None):
            client = AFMClient(bridge_path=None)
        result = client.probe_availability()
        self.assertIsInstance(result, AFMAvailability)
        self.assertFalse(result.ok)
        self.assertEqual(result.state, "bridge_missing")
        self.assertIn("swift build", result.detail)

    def test_probe_availability_transport_failure_does_not_raise(self) -> None:
        # A subprocess-level failure (not an availability state) is
        # surfaced as ok=False with the transport error code, no raise.
        def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            return _completed(stdout="not json", returncode=0)

        client = AFMClient(
            bridge_path=Path("/fake/EinsteinAFMBridge"),
            run_subprocess=fake_run,
        )
        result = client.probe_availability()
        self.assertFalse(result.ok)
        self.assertEqual(result.state, "bridge_invalid_response")


if __name__ == "__main__":
    unittest.main()
