from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import main  # noqa: E402
from ai.router import ClaudeRouter, get_default_router  # noqa: E402
from services.ingestion import ingest_document_record  # noqa: E402
from services.retrieval.hybrid import search_hybrid  # noqa: E402
from services.tutor import GroundedAnswer, grounded_tutor_response  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = EVALS_DIR / "fixtures"
CASES_DIR = EVALS_DIR / "cases"
REPORTS_DIR = EVALS_DIR / "reports"
SUPPORTED_CASE_KINDS = {"definition", "comparison", "cause", "mechanism", "negative"}


@dataclass(frozen=True)
class FixtureDefinition:
    filename: str
    path: Path
    file_type: str
    subject_name: str


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    kind: str
    question: str
    fixture_filenames: list[str]
    expected_doc_filenames: list[str]
    expected_topics: list[str]
    expected_quote_substrings: list[str]
    scope: dict[str, Any]
    notes: str


@contextmanager
def _temporary_env(values: dict[str, str | None]) -> Iterator[None]:
    original = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _isolated_runtime(mode: str) -> Iterator[None]:
    original = (
        main.BASE_DIR,
        main.DATA_DIR,
        main.UPLOAD_DIR,
        main.DB_PATH,
        main.SCHEMA_PATH,
    )
    env_overrides = {
        "EMBED_ON_INGEST": "0" if mode == "smoke" else os.environ.get("EMBED_ON_INGEST"),
        "RUN_VECTOR_BACKFILL": "0" if mode == "smoke" else os.environ.get("RUN_VECTOR_BACKFILL"),
    }
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            with _temporary_env(env_overrides):
                main.BASE_DIR = base_dir
                main.DATA_DIR = base_dir / "data"
                main.UPLOAD_DIR = main.DATA_DIR / "uploads"
                main.DB_PATH = main.DATA_DIR / "evals.db"
                main.SCHEMA_PATH = original[4]
                main.initialize_database()
                with main.get_db() as conn:
                    conn.execute("PRAGMA foreign_keys = OFF")
                    rows = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                    for row in rows:
                        table_name = str(row["name"])
                        if (
                            table_name.startswith("sqlite_")
                            or table_name == "schema_migrations"
                            or table_name.startswith("chunks_fts")
                            or table_name.startswith("chunks_vec")
                        ):
                            continue
                        conn.execute(f"DELETE FROM {table_name}")
                    if any(row["name"] == "chunks_vec" for row in rows):
                        conn.execute("DELETE FROM chunks_vec")
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.commit()
                yield
    finally:
        (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        ) = original


def _load_fixture_manifest() -> dict[str, FixtureDefinition]:
    payload = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    fixtures: dict[str, FixtureDefinition] = {}
    for item in payload:
        filename = str(item["filename"])
        fixtures[filename] = FixtureDefinition(
            filename=filename,
            path=FIXTURES_DIR / str(item["path"]),
            file_type=str(item["file_type"]),
            subject_name=str(item["subject_name"]),
        )
    return fixtures


def _parse_case(payload: dict[str, Any]) -> EvalCase:
    fixture_filenames = [str(item) for item in payload.get("fixture_filenames", [])]
    expected_doc_filenames = [
        str(item) for item in payload.get("expected_doc_filenames", fixture_filenames)
    ]
    return EvalCase(
        case_id=str(payload.get("id", "")),
        kind=str(payload.get("kind", "")),
        question=str(payload.get("question", "")),
        fixture_filenames=fixture_filenames,
        expected_doc_filenames=expected_doc_filenames,
        expected_topics=[str(item) for item in payload.get("expected_topics", [])],
        expected_quote_substrings=[
            str(item) for item in payload.get("expected_quote_substrings", [])
        ],
        scope=dict(payload.get("scope", {}) or {}),
        notes=str(payload.get("notes", "")),
    )


def _load_cases(suite: str) -> list[EvalCase]:
    case_path = CASES_DIR / f"{suite}.jsonl"
    cases: list[EvalCase] = []
    for line_number, raw_line in enumerate(
        case_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {case_path.name} line {line_number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Case {suite}:{line_number} must be a JSON object.")
        cases.append(_parse_case(payload))
    return cases


def _validate_case_shape(case: EvalCase, fixtures: dict[str, FixtureDefinition]) -> list[str]:
    errors: list[str] = []
    if not case.case_id:
        errors.append("missing id")
    if case.kind not in SUPPORTED_CASE_KINDS:
        errors.append(f"unsupported kind: {case.kind!r}")
    if not case.question:
        errors.append("missing question")
    if not case.fixture_filenames:
        errors.append("missing fixture_filenames")
    for filename in case.fixture_filenames:
        if filename not in fixtures:
            errors.append(f"unknown fixture filename: {filename}")
    for filename in case.expected_doc_filenames:
        if filename not in fixtures:
            errors.append(f"unknown expected_doc_filename: {filename}")
    doc_scope = case.scope.get("doc_filenames")
    if doc_scope is not None:
        if not isinstance(doc_scope, list) or not doc_scope:
            errors.append("scope.doc_filenames must be a non-empty list when provided")
        else:
            for filename in doc_scope:
                if str(filename) not in fixtures:
                    errors.append(f"unknown scope.doc_filename: {filename}")
    subject_scope = case.scope.get("subject_name")
    if subject_scope is not None and not str(subject_scope).strip():
        errors.append("scope.subject_name must be non-empty when provided")
    return errors


def _ingest_fixtures(fixtures: dict[str, FixtureDefinition]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    with main.get_db() as conn:
        for filename, fixture in fixtures.items():
            text = fixture.path.read_text(encoding="utf-8")
            result = ingest_document_record(
                conn=conn,
                filename=fixture.filename,
                file_type=fixture.file_type,
                extracted_text=text,
                page_count=1,
                subject_name=fixture.subject_name,
            )
            resolved[filename] = str(result["doc_id"])
    return resolved


def _resolve_fixture_doc_ids(
    filename_to_doc_id: dict[str, str],
    filenames: Sequence[str],
) -> list[str]:
    return [
        filename_to_doc_id[str(filename)]
        for filename in filenames
        if str(filename) in filename_to_doc_id
    ]


_WHITESPACE = re.compile(r"\s+")


def _normalize_text(value: str) -> str:
    return _WHITESPACE.sub(" ", value.strip().lower())


def _normalized_substring_match(needle: str, haystack: str) -> bool:
    normalized_needle = _normalize_text(needle)
    normalized_haystack = _normalize_text(haystack)
    return bool(normalized_needle) and normalized_needle in normalized_haystack


def _resolve_expected_chunks(
    conn: sqlite3.Connection,
    case: EvalCase,
    filename_to_doc_id: dict[str, str],
) -> set[str]:
    if not case.expected_quote_substrings:
        return set()
    doc_ids = _resolve_fixture_doc_ids(filename_to_doc_id, case.expected_doc_filenames)
    if not doc_ids:
        return set()
    placeholders = ",".join("?" * len(doc_ids))
    rows = conn.execute(
        f"SELECT id, content FROM chunks WHERE doc_id IN ({placeholders})",
        doc_ids,
    ).fetchall()
    expected: set[str] = set()
    for row in rows:
        content = str(row["content"] or "")
        if any(
            _normalized_substring_match(fragment, content)
            for fragment in case.expected_quote_substrings
        ):
            expected.add(str(row["id"]))
    return expected


def _scope_doc_ids(case: EvalCase, filename_to_doc_id: dict[str, str]) -> list[str] | None:
    doc_filenames = case.scope.get("doc_filenames")
    if not isinstance(doc_filenames, list):
        return None
    resolved = _resolve_fixture_doc_ids(filename_to_doc_id, [str(item) for item in doc_filenames])
    return resolved or None


def _scope_subject(case: EvalCase) -> str | None:
    subject = case.scope.get("subject_name")
    return str(subject).strip() or None


def _case_doc_ids(case: EvalCase, filename_to_doc_id: dict[str, str]) -> list[str]:
    return _resolve_fixture_doc_ids(filename_to_doc_id, case.fixture_filenames)


def _detect_scope_fallback(answer: GroundedAnswer) -> bool:
    return bool(getattr(answer, "scope_fallback_used", False))


def run_case(
    case: EvalCase,
    conn: sqlite3.Connection,
    mode: str,
    filename_to_doc_id: dict[str, str],
    router: ClaudeRouter | None = None,
) -> dict[str, Any]:
    scope_doc_ids = _scope_doc_ids(case, filename_to_doc_id)
    scope_subject = _scope_subject(case)
    fixture_doc_ids = _case_doc_ids(case, filename_to_doc_id)
    expected_doc_ids = _resolve_fixture_doc_ids(filename_to_doc_id, case.expected_doc_filenames)
    expected_chunks = _resolve_expected_chunks(conn, case, filename_to_doc_id)
    load_errors: list[str] = []
    if len(fixture_doc_ids) != len(case.fixture_filenames):
        load_errors.append("one or more fixture_filenames did not resolve to ingested documents")
    if len(expected_doc_ids) != len(case.expected_doc_filenames):
        load_errors.append(
            "one or more expected_doc_filenames did not resolve to ingested documents"
        )
    if case.expected_quote_substrings and not expected_chunks:
        load_errors.append("expected_quote_substrings did not resolve to any ingested chunk")

    hits = search_hybrid(
        conn,
        case.question,
        doc_ids=scope_doc_ids,
        subject_name=scope_subject,
        limit=8,
    )
    retrieved_chunk_ids = [hit.chunk_id for hit in hits]
    grounded_at_k = int(bool(set(retrieved_chunk_ids) & expected_chunks))
    metrics: dict[str, Any] = {
        "case_id": case.case_id,
        "kind": case.kind,
        "question": case.question,
        "fixture_filenames": case.fixture_filenames,
        "expected_doc_filenames": case.expected_doc_filenames,
        "scope": case.scope,
        "groundedness_at_k": grounded_at_k,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "expected_chunk_ids": sorted(expected_chunks),
        "load_errors": load_errors,
        "notes": case.notes,
    }
    if mode == "smoke":
        return metrics

    answer = grounded_tutor_response(
        conn,
        case.question,
        doc_ids=scope_doc_ids,
        subject_name=scope_subject,
        router=router,
    )
    # Post-T05: Citation.node_id is `int | str` (chunks branch surfaces
    # the legacy chunks.id str-UUID; nodes branch surfaces nodes.id int).
    # The chunks WHERE lookup below is correct on the default chunks
    # branch (the only branch the smoke eval exercises today); the
    # nodes-branch comparison in T08 wires a parallel `FROM nodes` path.
    cited_node_ids = {citation.node_id for claim in answer.claims for citation in claim.citations}
    overlap = cited_node_ids & expected_chunks
    citation_precision = len(overlap) / max(len(cited_node_ids), 1)
    citation_recall = len(overlap) / max(len(expected_chunks), 1)

    quote_total = 0
    quote_valid_count = 0
    for claim in answer.claims:
        for citation in claim.citations:
            quote_total += 1
            chunk_row = conn.execute(
                "SELECT content FROM chunks WHERE id = ?",
                (citation.node_id,),
            ).fetchone()
            if chunk_row and _normalized_substring_match(
                citation.quote, str(chunk_row["content"] or "")
            ):
                quote_valid_count += 1

    metrics.update(
        {
            "ok": answer.ok,
            "fallback": not answer.ok,
            "scope_fallback": _detect_scope_fallback(answer),
            "citation_precision": citation_precision,
            "citation_recall": citation_recall,
            "quote_validity": round(quote_valid_count / quote_total, 4) if quote_total else None,
            "quote_valid_count": quote_valid_count,
            "quote_total": quote_total,
            "citation_attempt_count": answer.citation_attempt_count,
            "citation_drop_count": answer.citation_drop_count,
            "citation_repair_count": answer.citation_repair_count,
            "citation_drop_rate": answer.citation_drop_count
            / max(answer.citation_attempt_count, 1),
            "citation_repair_rate": answer.citation_repair_count
            / max(answer.citation_attempt_count, 1),
            "claim_count": len(answer.claims),
            "unsupported_count": len(answer.unsupported_spans),
            "latency_ms": answer.latency_ms,
            "model": answer.model,
            "input_tokens": answer.input_tokens,
            "output_tokens": answer.output_tokens,
        }
    )
    return metrics


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile))))
    return round(ordered[rank], 2)


def _aggregate(results: Sequence[dict[str, Any]], *, mode: str) -> dict[str, Any]:
    blocking_errors = sum(1 for result in results if result.get("load_errors"))
    grounded_hits = sum(int(result.get("groundedness_at_k", 0)) for result in results)
    total = len(results)
    summary: dict[str, Any] = {
        "total_cases": total,
        "blocking_errors": blocking_errors,
        "groundedness_at_k": {
            "hits": grounded_hits,
            "total": total,
            "value": round((grounded_hits / total), 4) if total else 0.0,
        },
        "warnings": [],
    }
    if mode == "full":
        citation_precision_values = [
            float(result.get("citation_precision", 0.0)) for result in results
        ]
        citation_recall_values = [float(result.get("citation_recall", 0.0)) for result in results]
        citation_attempt_count = sum(
            int(result.get("citation_attempt_count", 0)) for result in results
        )
        citation_drop_count = sum(int(result.get("citation_drop_count", 0)) for result in results)
        citation_repair_count = sum(
            int(result.get("citation_repair_count", 0)) for result in results
        )
        quote_valid_count = sum(int(result.get("quote_valid_count", 0)) for result in results)
        quote_total = sum(int(result.get("quote_total", 0)) for result in results)
        fallback_count = sum(1 for result in results if result.get("fallback"))
        scope_fallback_count = sum(1 for result in results if result.get("scope_fallback"))
        latencies = [
            float(result.get("latency_ms", 0.0))
            for result in results
            if result.get("latency_ms") is not None
        ]
        models = sorted(
            {str(result.get("model") or "") for result in results if result.get("model")}
        )
        summary.update(
            {
                "citation_precision": _mean(citation_precision_values),
                "citation_recall": _mean(citation_recall_values),
                "quote_validity": round(quote_valid_count / quote_total, 4)
                if quote_total
                else None,
                "quote_valid_count": quote_valid_count,
                "quote_total": quote_total,
                "citation_drop_rate": round(
                    citation_drop_count / max(citation_attempt_count, 1), 4
                ),
                "citation_repair_rate": round(
                    citation_repair_count / max(citation_attempt_count, 1), 4
                ),
                "citation_attempt_count": citation_attempt_count,
                "citation_drop_count": citation_drop_count,
                "citation_repair_count": citation_repair_count,
                "fallback_rate": {
                    "count": fallback_count,
                    "total": total,
                    "value": round((fallback_count / total), 4) if total else 0.0,
                },
                "scope_fallback_rate": {
                    "count": scope_fallback_count,
                    "total": total,
                    "value": round((scope_fallback_count / total), 4) if total else 0.0,
                },
                "latency_ms": {
                    "p50": _percentile(latencies, 0.5),
                    "p95": _percentile(latencies, 0.95),
                },
                "model": models[0] if len(models) == 1 else ", ".join(models),
            }
        )
        if summary["groundedness_at_k"]["value"] < 0.7:
            summary["warnings"].append("groundedness@8 fell below 0.70")
        if summary["quote_validity"] is not None and summary["quote_validity"] < 0.9:
            summary["warnings"].append("quote_validity fell below 0.90")
    else:
        if summary["groundedness_at_k"]["value"] < 0.7:
            summary["warnings"].append("groundedness@8 fell below 0.70")
    return summary


def _markdown_summary(
    *,
    suite: str,
    mode: str,
    generated_at: str,
    results: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    lines = [
        f"# Eval Report — {generated_at}",
        "",
        f"Mode: {mode}",
        f"Suite: {suite}",
        f"Cases: {summary['total_cases']}",
        f"Model: {summary.get('model', 'n/a')}",
        "",
        "## Aggregate",
        "| Metric | Value |",
        "|---|---|",
        f"| groundedness@8 | {summary['groundedness_at_k']['hits']}/{summary['groundedness_at_k']['total']} ({summary['groundedness_at_k']['value']:.1%}) |",
    ]
    if mode == "full":
        lines.extend(
            [
                f"| citation_precision | {summary['citation_precision']:.2f} |",
                f"| citation_recall | {summary['citation_recall']:.2f} |",
                f"| quote_validity | {summary['quote_valid_count']}/{summary['quote_total']} ({(summary['quote_validity'] or 0.0):.2f}) |",
                f"| citation_drop_rate | {summary['citation_drop_count']}/{summary['citation_attempt_count']} ({summary['citation_drop_rate']:.1%}) |",
                f"| citation_repair_rate | {summary['citation_repair_count']}/{summary['citation_attempt_count']} ({summary['citation_repair_rate']:.1%}) |",
                f"| fallback_rate | {summary['fallback_rate']['count']}/{summary['fallback_rate']['total']} ({summary['fallback_rate']['value']:.1%}) |",
                f"| scope_fallback_rate | {summary['scope_fallback_rate']['count']}/{summary['scope_fallback_rate']['total']} ({summary['scope_fallback_rate']['value']:.1%}) |",
                f"| p50 latency | {summary['latency_ms']['p50'] / 1000:.1f}s |",
                f"| p95 latency | {summary['latency_ms']['p95'] / 1000:.1f}s |",
            ]
        )
    if summary["warnings"]:
        lines.extend(["", "## Warnings"])
        for warning in summary["warnings"]:
            lines.append(f"- {warning}")
    worst = sorted(
        results,
        key=lambda item: (
            int(item.get("groundedness_at_k", 0)),
            float(item.get("citation_precision", 0.0)),
            float(item.get("quote_validity", 1.0) or 1.0),
        ),
    )[:5]
    lines.extend(["", "## Per-case (worst 5 by groundedness)"])
    for item in worst:
        lines.append(
            f"- `{item['case_id']}`: groundedness={item.get('groundedness_at_k', 0)}"
            + (
                f", citation_precision={item.get('citation_precision', 0.0):.2f}, quote_validity={(item.get('quote_validity', 1.0) if item.get('quote_validity') is not None else 1.0):.2f}, citation_drop_rate={item.get('citation_drop_rate', 0.0):.2f}"
                if mode == "full"
                else ""
            )
        )
    return "\n".join(lines) + "\n"


def _emit_reports(
    report_dir: Path,
    *,
    suite: str,
    mode: str,
    results: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    generated_at_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    generated_at_file = generated_at_iso.replace(":", "-")
    payload = {
        "generated_at": generated_at_iso,
        "suite": suite,
        "mode": mode,
        "summary": summary,
        "results": list(results),
    }
    json_path = report_dir / f"{generated_at_file}.json"
    md_path = report_dir / f"{generated_at_file}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(
        _markdown_summary(
            suite=suite,
            mode=mode,
            generated_at=generated_at_iso,
            results=results,
            summary=summary,
        ),
        encoding="utf-8",
    )
    print(json_path)
    print(md_path)
    return {"json": str(json_path), "markdown": str(md_path), "generated_at": generated_at_iso}


def run_suite(
    suite: str,
    mode: str,
    *,
    report_dir: str | Path = REPORTS_DIR,
    router: ClaudeRouter | None = None,
) -> dict[str, Any]:
    fixtures = _load_fixture_manifest()
    cases = _load_cases(suite)
    report_path = Path(report_dir)

    with _isolated_runtime(mode):
        filename_to_doc_id = _ingest_fixtures(fixtures)
        active_router = router if mode == "full" else None
        if mode == "full" and active_router is None:
            active_router = get_default_router()

        results: list[dict[str, Any]] = []
        with main.get_db() as conn:
            for case in cases:
                validation_errors = _validate_case_shape(case, fixtures)
                case_result = run_case(case, conn, mode, filename_to_doc_id, router=active_router)
                case_result["load_errors"] = validation_errors + list(
                    case_result.get("load_errors", [])
                )
                results.append(case_result)

    summary = _aggregate(results, mode=mode)
    emitted = _emit_reports(
        report_path,
        suite=suite,
        mode=mode,
        results=results,
        summary=summary,
    )
    report = {
        "suite": suite,
        "mode": mode,
        "summary": summary,
        "results": results,
        "reports": emitted,
    }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local-first Einstein Tutor eval suites.")
    parser.add_argument("--suite", default="smoke", help="Suite name under evals/cases/")
    parser.add_argument(
        "--mode",
        choices=("smoke", "full"),
        default="smoke",
        help="Smoke mode is retrieval-only; full mode runs grounded tutor calls.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(REPORTS_DIR),
        help="Directory where machine-readable and markdown reports will be written.",
    )
    return parser.parse_args(argv)


def main_cli(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_suite(args.suite, args.mode, report_dir=args.report_dir)
    if int(report["summary"]["blocking_errors"]) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
