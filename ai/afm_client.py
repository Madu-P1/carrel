"""Apple Foundation Models provider for Carrel.

Talks to the `EinsteinAFMBridge` Swift sidecar via subprocess + JSON
over stdin/stdout. Implements the `AIProvider` Protocol so callers do
not know they are running on Apple Intelligence vs Claude vs Ollama.

Requires macOS 26 (Tahoe) + Apple Silicon + Apple Intelligence enabled.
The bridge surfaces specific error codes when those preconditions fail
so the UI can guide the user (e.g., open System Settings → Apple
Intelligence & Siri).

Wire protocol matches `macos-app/Sources/EinsteinAFMBridge/main.swift`.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ai.afm_grounded import (
    _split_sentences,
    detect_fabricated_terms,
    extract_best_span,
)
from ai.native_bridge_paths import AFM_BRIDGE_CANDIDATES, find_binary
from ai.prompt_sanitization import escape_afm_chunk_marker
from ai.router import ClaudeCallResult, parse_or_rescue_json, resolve_ai_timeout_seconds

# Python-side ProviderKind tag. The literal type lives in ai/providers.py.
PROVIDER_KIND_AFM = "afm"


@dataclass(frozen=True)
class GroundedChunk:
    """Input chunk for AFM's grounded-answer flow.

    `text` is what we render in the numbered prompt for the model.
    `chunk_id`, `doc_id`, `page_num`, `section` flow through to the
    Citation entries on the returned `json_payload` so the frontend can
    deep-link to the source span.
    """

    chunk_id: str
    text: str
    doc_id: str | None = None
    page_num: int | None = None
    section: str | None = None


class AFMClient:
    """AIProvider backed by the EinsteinAFMBridge Swift sidecar.

    The bridge spawns once per call (matches the existing
    EinsteinIngestionBridge precedent). Subprocess overhead (~50-200ms)
    is dwarfed by inference time. A long-lived NDJSON bridge is a
    follow-up task; out of scope until streaming or multi-turn arrives.
    """

    kind = "afm"

    def __init__(
        self,
        *,
        bridge_path: Path | None = None,
        timeout_seconds: float | None = None,
        # Test seam: inject a callable matching subprocess.run's signature.
        run_subprocess: Any = None,
    ) -> None:
        self.bridge_path = (
            bridge_path if bridge_path is not None else find_binary(AFM_BRIDGE_CANDIDATES)
        )
        # PR-P2: prefer the unified CARREL_AI_TIMEOUT_SECONDS over the
        # legacy AFM_TIMEOUT_SECONDS env var. AFM's default of 120s is
        # double Claude/Ollama because cold-spawn + on-device inference
        # on a loaded Mac can legitimately need that headroom; the env
        # vars let power users tune it.
        self.timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else resolve_ai_timeout_seconds(
                default=120.0,
                legacy_env_name="AFM_TIMEOUT_SECONDS",
            )
        )
        self._run = run_subprocess if run_subprocess is not None else subprocess.run

    # ------------------------------------------------------------------
    # AIProvider Protocol surface
    # ------------------------------------------------------------------

    def ai_enabled(self) -> bool:
        """Cheap check: bridge binary exists. Real Apple Intelligence
        availability is surfaced at call time as ok=False with a
        specific error_code (apple_intelligence_not_enabled etc.)."""
        return self.bridge_path is not None

    def model_for_task(self, task: Any) -> str:
        # AFM exposes one on-device model. Tier does not apply.
        del task
        return "afm-3b"

    def request_text(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        max_tokens: int = 1600,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        del cache_system_prompt
        return self._call(
            kind="request_text",
            request_kind=request_kind,
            task=task,
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
        )

    def request_json(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        fallback: Any = None,
        max_tokens: int = 1600,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        del cache_system_prompt
        # Mirror OllamaClient: append a strict-JSON instruction to the
        # system prompt, then post-hoc parse + rescue. AFM has no
        # runtime guided-generation; @Generable is a compile-time macro
        # so we cannot drive it from a runtime schema.
        system_with_json = (
            (system or "") + "\n\nReply with a single JSON object. No prose, no markdown, "
            "no leading or trailing text."
        )
        result = self._call(
            kind="request_json",
            request_kind=request_kind,
            task=task,
            system=system_with_json,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        if not result.ok:
            if fallback is not None:
                return replace(result, json_payload=fallback)
            return result
        parsed = _parse_or_rescue(result.text)
        if parsed is None:
            if fallback is not None:
                return replace(
                    result,
                    ok=False,
                    error_code="invalid_json",
                    error_message="Bridge response did not contain parseable JSON.",
                    json_payload=fallback,
                )
            return replace(
                result,
                ok=False,
                error_code="invalid_json",
                error_message="Bridge response did not contain parseable JSON.",
            )
        return replace(result, json_payload=parsed)

    def supports_grounded_answer(self) -> bool:
        """AFM is the only provider with a true grounded-answer flow."""
        return True

    def request_grounded_answer(
        self,
        *,
        request_kind: str,
        system: str,
        question: str,
        chunks: list[GroundedChunk],
        max_tokens: int = 1200,
        task: Any = "balanced",
        temperature: float = 0.0,
    ) -> ClaudeCallResult:
        """Tutor-grade grounded-answer flow using AFM's @Generable path.

        This is the preferred method for the Carrel Ask flow when AFM
        is the active provider. It uses Apple's guided-generation (the
        Swift bridge constrains the model's output to a fixed schema
        via the `@Generable GroundedAnswer` type), so the model
        literally cannot emit invalid structure. The 3B model only has
        to identify which chunk supports the answer, not produce a
        verbatim quote -- quotes are extracted server-side from the
        chunk text via lexical overlap.

        Args:
            request_kind: telemetry label, e.g. "tutor.grounded_answer".
            system: terse system instructions. Keep under ~400 tokens
                for AFM. Most important instruction should go LAST per
                small-model recency bias.
            question: the user's natural-language question.
            chunks: 3-5 retrieval results, pre-trimmed to ~300 tokens
                each for best AFM accuracy. The list order maps to
                the 1-based chunk numbers in the prompt.
            max_tokens: cap on the generated answer length.
            temperature: 0.0 for factual grounding; constrained
                decoding combined with greedy sampling gives
                near-deterministic output.

        Returns:
            A ClaudeCallResult whose `json_payload` matches
            services.tutor.SUBMIT_GROUNDED_ANSWER_TOOL.input_schema:
              {
                "summary": str,
                "claims": [{"text": str, "citations": [
                    {"chunk_index": int, "quote": str}, ...
                ]}],
                "unsupported_spans": [str, ...]
              }
            so the tutor's existing parser at services/tutor.py:705
            consumes it identically to a Claude tool_use response.
        """
        if not chunks:
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="empty_chunks",
                error_message="request_grounded_answer requires at least one chunk",
            )

        # Render numbered chunks in the prompt. AFM is reliably better
        # at "[Chunk 2]" than at content-based references. Keep the
        # rendering compact so we don't burn the model's context budget.
        #
        # PR-S3: a malicious source could contain a literal "[Chunk 999]"
        # prefix to fake an additional chunk. Escape the boundary token
        # in each chunk body before insertion. The AFM system prompt
        # documents the sentinel as reference text.
        chunk_lines = []
        for idx, chunk in enumerate(chunks, start=1):
            sanitized = escape_afm_chunk_marker(chunk.text.strip())
            chunk_lines.append(f"[Chunk {idx}] {sanitized}")
        chunks_block = "\n".join(chunk_lines)
        prompt = f"{chunks_block}\n\nQuestion: {question.strip()}"

        result = self._call(
            kind="request_grounded_answer",
            request_kind=request_kind,
            task=task,
            system=system or "",
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if not result.ok:
            return result

        # The bridge populates `structured.grounded_answer` for this
        # kind. _call returns json_payload populated with the raw
        # bridge data when it sees a `structured` field; map it to
        # the tutor schema here.
        raw = result.json_payload
        if not isinstance(raw, dict):
            return replace(
                result,
                ok=False,
                error_code="bridge_missing_structured",
                error_message="grounded_answer kind returned no structured payload",
            )

        answer = (raw.get("answer") or "").strip()
        supporting = raw.get("supporting_chunks") or []
        unsupported = raw.get("unsupported_claims") or []

        # Filter to valid 1-based chunk indices that the prompt actually
        # contained. Models occasionally emit out-of-range indices when
        # the question doesn't match any chunk well.
        valid_indices = [
            idx for idx in supporting if isinstance(idx, int) and 1 <= idx <= len(chunks)
        ]

        # Build the citations array via server-side span extraction.
        # Each cited chunk yields one citation; the verbatim quote is
        # the highest-overlap sentence from that chunk against the
        # answer text. We also track the best score across chunks so
        # we can refuse cases where the model claimed to cite a
        # chunk but no sentence in it actually overlaps with the
        # answer (a soft form of citation fabrication).
        citations = []
        best_overlap_score = 0.0
        cited_chunks: list[tuple[int, GroundedChunk]] = []
        for idx in valid_indices:
            chunk = chunks[idx - 1]
            span = extract_best_span(chunk.text, answer)
            best_overlap_score = max(best_overlap_score, span.score)
            citations.append(
                {
                    "chunk_index": idx,
                    "quote": span.text,
                }
            )
            cited_chunks.append((idx, chunk))

        # Second ungrounded guard: model said "these chunks support
        # my answer" but the actual sentences in those chunks don't
        # share enough vocabulary with the answer to back it up.
        # `_tokens` already filters stopwords, so this Jaccard is over
        # content words only. Threshold tuned empirically against the
        # corporate-finance variance/BFI test set:
        #   * 0.06 lets through "capital budgeting" answers cited
        #     against chapter-title chunks (one shared content word).
        #   * 0.10 catches those without false-rejecting answers that
        #     genuinely cite the right chunk.
        if best_overlap_score < 0.10 and answer:
            return replace(
                result,
                ok=False,
                error_code="ungrounded_answer",
                error_message=(
                    "The on-device model produced an answer but no sentence "
                    "in the cited chunks supports it. Your sources may not "
                    "cover this question."
                ),
                json_payload={
                    "summary": "",
                    "claims": [],
                    "unsupported_spans": [
                        "The provided sources do not directly answer this question.",
                        *[str(u).strip() for u in unsupported if str(u).strip()],
                    ],
                    "ungrounded_draft": answer,
                },
            )

        # Ungrounded-answer guard: AFM occasionally synthesizes an
        # answer entirely from training data when the chunks don't
        # cover the concept (e.g. asked to define a term the chunks
        # only compute). It correctly signals this by emitting
        # supporting_chunks=[]. Honour the signal rather than show an
        # ungrounded answer: Carrel's contract is "no fabrication."
        # The frontend will render this as "Your sources don't cover
        # this question" with the retrieved chunks shown for context.
        if not valid_indices:
            return replace(
                result,
                ok=False,
                error_code="ungrounded_answer",
                error_message=(
                    "The on-device model produced an answer but could not "
                    "cite any of your sources. Your sources may not cover "
                    "this question."
                ),
                json_payload={
                    "summary": "",
                    "claims": [],
                    "unsupported_spans": [
                        "The provided sources do not directly answer this question.",
                        *[str(u).strip() for u in unsupported if str(u).strip()],
                    ],
                    "ungrounded_draft": answer,
                },
            )

        # Fabrication guard (hard refuse, not warn): AFM 3B occasionally
        # substitutes proper nouns AND specific numeric values from
        # training data. Real case: answer said "Microsoft" when chunks
        # said "BFI". Same failure mode applies to invented numbers
        # ("0.05" when chunks say "0.045") and dates.
        #
        # Per Carrel's "no fabrication" contract, refuse instead of
        # surfacing a poisoned answer with a "we may have lied"
        # disclaimer. A refusal with the retrieved chunks shown is
        # strictly better than a wrong answer with a footnote.
        chunk_texts = [chunk.text for chunk in chunks]
        fabrication = detect_fabricated_terms(answer, chunk_texts)
        unsupported_spans = [str(item).strip() for item in unsupported if str(item).strip()]
        if not fabrication.is_clean:
            suspect_list = ", ".join(fabrication.suspect_terms)
            return replace(
                result,
                ok=False,
                error_code="fabricated_content",
                error_message=(
                    "The on-device model introduced terms that are not in "
                    "your sources: " + suspect_list + ". Refusing to surface "
                    "a potentially-wrong answer."
                ),
                json_payload={
                    "summary": "",
                    "claims": [],
                    "unsupported_spans": [
                        "Model produced terms not found in sources: " + suspect_list,
                        *unsupported_spans,
                    ],
                    "ungrounded_draft": answer,
                },
            )

        # Per-claim grounding: split the answer into sentences and
        # ground each independently against the cited chunks. One
        # well-supported sentence does not vouch for the rest of a
        # multi-claim answer (Codex P1: previously the whole answer
        # was wrapped in a single Claim, so a single supported clause
        # made unsupported clauses ride along invisibly).
        #
        # For each answer sentence we find the cited chunk with the
        # highest token-overlap span. Sentences whose best span clears
        # the per-claim threshold get their own Claim with that
        # chunk's citation. Sentences below threshold are surfaced in
        # `unsupported_spans` so the tutor renders them dimmed/flagged
        # rather than treating them as verified.
        per_claim_threshold = 0.08
        answer_sentences = _split_sentences(answer) if answer else []
        # If the answer is a single short sentence, _split_sentences
        # may drop it (min 20 chars). Fall back to the whole answer.
        if not answer_sentences and answer:
            answer_sentences = [answer.strip()]

        claims: list[dict[str, Any]] = []
        unsupported_sentences: list[str] = []
        for sentence in answer_sentences:
            best_for_sentence: tuple[float, int, str] | None = None
            for idx, chunk in cited_chunks:
                span = extract_best_span(chunk.text, sentence)
                if best_for_sentence is None or span.score > best_for_sentence[0]:
                    best_for_sentence = (span.score, idx, span.text)
            if best_for_sentence is None:
                unsupported_sentences.append(sentence)
                continue
            score, idx, quote = best_for_sentence
            if score < per_claim_threshold:
                unsupported_sentences.append(sentence)
                continue
            claims.append(
                {
                    "text": sentence,
                    "citations": [{"chunk_index": idx, "quote": quote}],
                }
            )

        # If every sentence dropped, the model produced text that
        # looked grounded in aggregate (best_overlap_score cleared 0.10
        # somewhere) but no individual claim is supported. Refuse.
        if answer and not claims:
            return replace(
                result,
                ok=False,
                error_code="ungrounded_answer",
                error_message=(
                    "The on-device model produced an answer but no individual "
                    "sentence is supported by your sources."
                ),
                json_payload={
                    "summary": "",
                    "claims": [],
                    "unsupported_spans": [
                        "The provided sources do not directly answer this question.",
                        *unsupported_sentences,
                        *unsupported_spans,
                    ],
                    "ungrounded_draft": answer,
                },
            )

        payload = {
            "summary": answer,
            "claims": claims,
            "unsupported_spans": [*unsupported_sentences, *unsupported_spans],
        }
        return replace(result, json_payload=payload)

    def request_tool_call(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        tool: dict[str, Any],
        max_tokens: int = 2400,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        del cache_system_prompt
        if not isinstance(tool, dict):
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="invalid_tool_schema",
                error_message="tool argument must be a dict",
            )
        if not isinstance(tool.get("input_schema"), dict):
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="invalid_tool_schema",
                error_message="tool.input_schema must be a dict",
            )
        # Mirror OllamaClient: prepend a tool description preamble to
        # the system prompt so the on-device model emits a JSON object
        # matching the schema. Same enforcement strategy Ollama already
        # uses, since neither has runtime guided-generation.
        tool_name = tool.get("name", "tool")
        tool_desc = tool.get("description", "")
        preamble = (
            f"You must respond by populating the `{tool_name}` payload.\n"
            f"{tool_desc}\n"
            "Your entire response MUST be a single JSON object matching the required schema. "
            "Do not include explanations, markdown, or text outside the JSON object."
        )
        full_system = preamble + "\n\n" + (system or "")
        result = self._call(
            kind="request_tool_call",
            request_kind=request_kind,
            task=task,
            system=full_system,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        if not result.ok:
            return result
        parsed = _parse_or_rescue(result.text)
        if parsed is None:
            return replace(
                result,
                ok=False,
                error_code="invalid_json",
                error_message="Bridge response did not contain parseable JSON.",
            )
        return replace(result, json_payload=parsed)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _call(
        self,
        *,
        kind: str,
        request_kind: str,
        task: Any,
        system: str,
        prompt: str,
        max_tokens: int,
        temperature: float | None = None,
    ) -> ClaudeCallResult:
        if self.bridge_path is None:
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="bridge_unavailable",
                error_message=(
                    "EinsteinAFMBridge binary not found. Run `cd macos-app && swift build`."
                ),
            )
        request_id = str(uuid.uuid4())
        req: dict[str, Any] = {
            "kind": kind,
            "request_id": request_id,
            "system": system,
            "prompt": prompt,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            req["temperature"] = float(temperature)
        start = time.perf_counter()
        try:
            completed = self._run(
                [str(self.bridge_path)],
                input=json.dumps(req),
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="timeout",
                error_message=f"AFM bridge timed out after {self.timeout_seconds}s",
                latency_ms=(time.perf_counter() - start) * 1000.0,
                request_id=request_id,
            )
        except OSError as exc:
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="bridge_spawn_failed",
                error_message=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000.0,
                request_id=request_id,
            )

        # Exit code 64 = invalid JSON on stdin. Stderr carries the diag.
        if completed.returncode == 64:
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="bridge_protocol_error",
                error_message=(completed.stderr or "").strip() or "Invalid bridge request",
                latency_ms=(time.perf_counter() - start) * 1000.0,
                request_id=request_id,
            )

        stdout = (completed.stdout or "").strip()
        if not stdout:
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="bridge_empty_response",
                error_message=(completed.stderr or "").strip() or "Bridge returned no output",
                latency_ms=(time.perf_counter() - start) * 1000.0,
                request_id=request_id,
            )

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return _bridge_error_result(
                task=task,
                request_kind=request_kind,
                error_code="bridge_invalid_response",
                error_message=f"Bridge stdout not valid JSON: {exc}",
                latency_ms=(time.perf_counter() - start) * 1000.0,
                request_id=request_id,
            )

        # For @Generable / guided-generation kinds the bridge returns
        # the structured payload under `structured.<kind_payload>`.
        # Lift the inner payload into json_payload so the typed
        # request method (e.g. request_grounded_answer) can consume it
        # without poking at the wire format. request_json /
        # request_tool_call still populate json_payload post-hoc by
        # rescue-parsing `text`.
        structured = data.get("structured")
        initial_json_payload: Any = None
        if isinstance(structured, dict) and structured:
            # The bridge emits exactly one populated key per call,
            # matching the request kind. Surface its value directly.
            for inner in structured.values():
                if isinstance(inner, dict):
                    initial_json_payload = inner
                    break

        return ClaudeCallResult(
            ok=bool(data.get("ok")),
            task=task,
            model=data.get("model") or "afm-3b",
            request_kind=request_kind,
            text=data.get("text"),
            json_payload=initial_json_payload,
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            latency_ms=float(
                data.get("latency_ms")
                if data.get("latency_ms") is not None
                else (time.perf_counter() - start) * 1000.0
            ),
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
            cache_hit=False,
            service_tier=None,
            stop_reason=data.get("stop_reason"),
            request_id=request_id,
            provider="afm",
        )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


# PR-P2: AFM previously had a local copy of this rescue logic that
# diverged from Claude's `_extract_json_from_text` (AFM stripped
# markdown fences and did `rfind` truncation; Claude only did
# find-first-opener). Same malformed output → different `ok` value
# depending on provider. The canonical implementation now lives in
# `ai/router.py:parse_or_rescue_json`; AFM aliases the local name to
# preserve in-module call sites without diverging again.
_parse_or_rescue = parse_or_rescue_json


def _bridge_error_result(
    *,
    task: Any,
    request_kind: str,
    error_code: str,
    error_message: str,
    latency_ms: float = 0.0,
    request_id: str | None = None,
) -> ClaudeCallResult:
    return ClaudeCallResult(
        ok=False,
        task=task,
        model="afm-3b",
        request_kind=request_kind,
        text=None,
        json_payload=None,
        error_code=error_code,
        error_message=error_message,
        latency_ms=latency_ms,
        input_tokens=None,
        output_tokens=None,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
        cache_hit=False,
        service_tier=None,
        stop_reason=None,
        request_id=request_id,
        provider="afm",
    )


# ----------------------------------------------------------------------
# Module-level singleton (matches get_default_router / get_default_ollama_client)
# ----------------------------------------------------------------------


_DEFAULT_AFM_CLIENT: AFMClient | None = None


def get_default_afm_client() -> AFMClient:
    global _DEFAULT_AFM_CLIENT
    if _DEFAULT_AFM_CLIENT is None:
        _DEFAULT_AFM_CLIENT = AFMClient()
    return _DEFAULT_AFM_CLIENT


def reset_default_afm_client() -> None:
    """Drop the cached client. Tests use this between env mutations."""
    global _DEFAULT_AFM_CLIENT
    _DEFAULT_AFM_CLIENT = None
