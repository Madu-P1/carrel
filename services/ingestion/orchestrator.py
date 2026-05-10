from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import db
from app_logging import get_logger, log_event
from services import provenance_service, stale_tracker
from services.extraction_pipeline import IngestedAsset

from . import docling_parser, typed_walker
from .cards import build_card_records
from .concept_candidates import clean_candidate_label, select_concept_phrases
from .concepts import chunk_text, sentence_for_term, summarize_document
from .persistence import (
    embed_and_index_nodes,
    index_chunk_rowids_on_ingest,
    insert_typed_nodes,
    mark_vector_backfill_pending,
)
from .questions import build_question_record
from .relationships import _extract_concept_depth, infer_relationship, rank_supporting_chunk_ids
from .text_utils import clean_learning_text, normalize_subject_name
from .topics import build_concept_payloads_from_chunks

LOGGER = get_logger("ingestion.orchestrator")


def _docling_enabled_for(extension: str) -> bool:
    """Two env-var feature flags gate the typed-node ingest path.

    INGEST_USE_DOCLING (default false) — master switch.
    INGEST_DOCLING_FORMATS (default 'pdf') — comma-separated allowlist of
    file extensions to route through Docling. Start with PDF only;
    expand once parity is proven on real documents.
    """
    if os.getenv("INGEST_USE_DOCLING", "false").lower() not in ("1", "true", "yes"):
        return False
    formats = os.getenv("INGEST_DOCLING_FORMATS", "pdf").lower().split(",")
    allowed = {fmt.strip() for fmt in formats if fmt.strip()}
    return extension.lstrip(".").lower() in allowed


# PR 0a — auto-card-generation on upload is OFF by default. Users
# explicitly trigger card drafting from the document detail view via
# CardAiDraftDialog. The flag exists as an escape hatch for testing
# and for the rare integration path that still wants the legacy
# behaviour. It is read per-call so tests can flip it via env var.
_AUTO_CARD_DRAFT_ENV = "CARREL_AUTO_CARD_DRAFT"
# app_settings key gating the once-per-upgrade telemetry emission.
_AUTO_DISABLED_LOGGED_KEY = "cards_auto_generation_disabled_logged"


def _auto_card_draft_enabled() -> bool:
    """Return True when the legacy auto-card-creation path on upload is
    enabled. Default is False (PR 0a). Same parsing convention as
    ``INGEST_USE_DOCLING`` for consistency with other ingest flags.
    """
    return os.getenv(_AUTO_CARD_DRAFT_ENV, "false").lower() in ("1", "true", "yes")


def _maybe_log_auto_generation_disabled(conn: sqlite3.Connection) -> None:
    """Emit ``cards.auto_generation_disabled`` once per database lifetime
    when the flag is off, so the dashboard can confirm the migration
    flipped. Re-emission is suppressed via an ``app_settings`` flag so
    we don't add a row on every upload.

    Best-effort: any failure here must not break the ingest path.
    """
    try:
        from services import app_state, usage_events as usage_events_service

        if app_state.get_setting(conn, _AUTO_DISABLED_LOGGED_KEY):
            return
        usage_events_service.record_event(
            conn,
            event_name="cards.auto_generation_disabled",
            properties=None,
            surface="ingestion",
        )
        app_state.set_setting(conn, _AUTO_DISABLED_LOGGED_KEY, "1")
    except Exception as exc:  # pragma: no cover - defensive
        log_event(
            LOGGER,
            logging.WARNING,
            "auto_generation_disabled_log_failed",
            error=str(exc),
        )


def _resolve_ingest_path(filename: str, storage_name: Optional[str]) -> Optional[Path]:
    """Best-effort resolution of the original file path on disk.

    Manual-text ingests have no file. Uploaded files live under
    `db.UPLOAD_DIR / storage_name`. Returns None when no readable file
    is reachable so callers can skip the Docling path silently.
    """
    if not storage_name:
        return None
    try:
        candidate = (db.UPLOAD_DIR / storage_name).resolve(strict=False)
    except Exception:
        return None
    return candidate if candidate.exists() else None


def _file_extension(filename: str, storage_name: Optional[str]) -> str:
    name = storage_name or filename or ""
    return Path(name).suffix.lstrip(".").lower()


def _draft_cards_for_concept(
    conn: sqlite3.Connection,
    *,
    concept: Dict[str, object],
    concept_payloads: List[Dict[str, object]],
    concept_id: str,
    concept_evidence_ids: List[str],
) -> None:
    """Create SRS cards for a single concept and link card→evidence.

    Extracted from ``ingest_document_record`` so the per-concept card
    creation can be gated independently of the rest of the ingest
    pipeline (PR 0a). The behavior is byte-identical to the inline
    block this replaced — same INSERT shape, same defaults, same
    evidence-link call. No callers other than ``ingest_document_record``
    today.
    """
    for card in build_card_records(concept, concept_payloads):
        card_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO srs_cards (id, concept_id, card_type, front, back, state, stability, difficulty, due_date)
            VALUES (?, ?, ?, ?, ?, 'new', 1.0, ?, ?)
            """,
            (
                card_id,
                concept_id,
                card["card_type"],
                card["front"],
                card["back"],
                card["difficulty"],
                date.today().isoformat(),
            ),
        )
        if concept_evidence_ids:
            provenance_service.link_evidence_to_card(conn, card_id, concept_evidence_ids)


def ingest_document_record(
    conn: sqlite3.Connection,
    filename: str,
    file_type: str,
    extracted_text: str,
    page_count: Optional[int],
    storage_name: Optional[str] = None,
    subject_name: Optional[str] = None,
    asset: Optional[IngestedAsset] = None,
) -> Dict[str, object]:
    # PR 0a telemetry: emit a single signal the first time the gated
    # path runs with the flag off, so the dashboard can confirm the
    # auto-generation migration has flipped on this install.
    if not _auto_card_draft_enabled():
        _maybe_log_auto_generation_disabled(conn)
    doc_id = str(uuid.uuid4())
    normalized_subject = normalize_subject_name(subject_name)
    raw_text = asset.cleaned_text if asset else extracted_text
    learning_text = clean_learning_text(raw_text)
    source_hash = (
        asset.content_hash if asset else stale_tracker.compute_source_hash(learning_text)
    )[:32]
    document_summary = summarize_document(learning_text)
    parser_diagnostics = (
        asset.diagnostics
        if asset
        else {
            "filename": filename,
            "detected_type": file_type,
            "preview_text": learning_text[:1200],
            "quality": {
                "parser": "manual_text",
                "extraction_modes": ["manual"],
                "warnings": [],
                "metrics": {
                    "page_count": page_count,
                    "char_count": len(learning_text),
                    "element_count": 1 if learning_text else 0,
                    "chunk_count": 0,
                    "warning_count": 0,
                },
                "confidence": 0.95 if learning_text else 0.2,
                "fallback_chain": [],
            },
            "element_count": 1 if learning_text else 0,
            "chunk_count": 0,
        }
    )
    duplicate_row = conn.execute(
        "SELECT id FROM documents WHERE source_hash = ? LIMIT 1",
        (source_hash,),
    ).fetchone()
    duplicate_of = duplicate_row["id"] if duplicate_row else None
    source_kind = "uploaded_file" if storage_name or asset else "manual_text"
    conn.execute(
        """
        INSERT INTO documents (
            id, filename, storage_name, subject_name, file_type, page_count, status,
            source_hash, source_kind, parser_status, parser_diagnostics, duplicate_of, updated_at, extracted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'processing', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            doc_id,
            filename,
            storage_name,
            normalized_subject,
            file_type,
            page_count,
            source_hash,
            source_kind,
            "ready" if learning_text else "warning",
            json.dumps(parser_diagnostics, ensure_ascii=False),
            duplicate_of,
        ),
    )

    if asset and asset.chunks:
        chunk_payloads = [
            {
                "content": chunk.content,
                "section": chunk.section or f"Section {index + 1}",
                "page_num": chunk.page_num,
                "chunk_index": chunk.chunk_index if chunk.chunk_index is not None else index,
                "provenance_json": json.dumps(chunk.provenance or {}, ensure_ascii=False),
            }
            for index, chunk in enumerate(asset.chunks)
            if str(chunk.content or "").strip()
        ]
    else:
        fallback_section = next(
            iter(select_concept_phrases(learning_text, filename, limit=1)),
            clean_candidate_label(Path(filename).stem.replace("-", " ").replace("_", " "))
            or "Core Ideas",
        )
        chunk_payloads = [
            {
                "content": content,
                "section": fallback_section,
                "page_num": None,
                "chunk_index": index,
                "provenance_json": json.dumps(
                    {
                        "parser": "manual_text",
                        "source_spans": [
                            {
                                "file_name": filename,
                                "file_id": source_hash,
                                "section": fallback_section,
                                "element_id": f"manual-{index + 1}",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
            for index, content in enumerate(chunk_text(learning_text))
        ]

    chunk_rows: List[Dict[str, object]] = []
    chunk_rowids: List[int] = []
    for payload in chunk_payloads:
        content = str(payload["content"])
        chunk_id = str(uuid.uuid4())
        chunk_rows.append(
            {
                "id": chunk_id,
                "content": content,
                "section": payload["section"],
                "page_num": payload["page_num"],
                "chunk_index": payload["chunk_index"],
                "provenance_json": payload["provenance_json"],
            }
        )
        cursor = conn.execute(
            """
            INSERT INTO chunks (
                id, doc_id, content, section, page_num, chunk_index, token_count, embedding_id,
                chunk_hash, source_version, provenance_json, embedding_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'pending')
            """,
            (
                chunk_id,
                doc_id,
                content,
                payload["section"],
                payload["page_num"],
                payload["chunk_index"],
                len(content.split()),
                None,
                stale_tracker.compute_source_hash(content),
                payload["provenance_json"],
            ),
        )
        if cursor.lastrowid is not None:
            chunk_rowids.append(int(cursor.lastrowid))

    if chunk_rowids:
        try:
            index_chunk_rowids_on_ingest(conn, chunk_rowids)
        except Exception:
            mark_vector_backfill_pending(conn)

    # PR 1: parallel typed-node ingest path (feature-flagged).
    #
    # Hard rule: this block must NEVER fail the chunks ingest. Any
    # exception is swallowed and logged — the user still gets a working
    # document on the legacy retrieval path. Once retrieval (PR 2) reads
    # from `nodes`, the flag flip happens behind its own gate.
    extension = _file_extension(filename, storage_name)
    if _docling_enabled_for(extension):
        if not docling_parser.is_available():
            log_event(LOGGER, logging.WARNING, "docling_unavailable", doc_id=doc_id)
        else:
            ingest_path = _resolve_ingest_path(filename, storage_name)
            if ingest_path is None:
                log_event(
                    LOGGER,
                    logging.WARNING,
                    "docling_skipped_no_file",
                    doc_id=doc_id,
                    storage_name=storage_name,
                )
            else:
                try:
                    doc = docling_parser.parse_document(ingest_path)
                    nodes = typed_walker.walk(doc)
                    node_ids = insert_typed_nodes(conn, doc_id, nodes)
                    embed_and_index_nodes(conn, nodes, node_ids)
                    log_event(
                        LOGGER,
                        logging.INFO,
                        "typed_nodes_indexed",
                        doc_id=doc_id,
                        node_count=len(nodes),
                    )
                except Exception as exc:
                    log_event(
                        LOGGER,
                        logging.ERROR,
                        "docling_ingest_failed",
                        doc_id=doc_id,
                        error=str(exc),
                    )

    concept_payloads = build_concept_payloads_from_chunks(chunk_rows, filename)
    # Local import to avoid the services.documents <-> services.ingestion
    # circular import. clean_concept_label is the canonical place to fix
    # doubled-phrase concept names; applying it here is the upstream
    # fence so doubled names never reach concepts.name in the first
    # place. (Other readers, like session_engine.py, also clean at
    # read-time as a backstop.)
    from services.documents import clean_concept_label

    concept_ids: List[str] = []
    for concept in concept_payloads:
        concept_id = str(uuid.uuid4())
        concept_ids.append(concept_id)
        cleaned_name = clean_concept_label(str(concept.get("name") or ""))
        concept["name"] = cleaned_name
        concept_chunk_ids = list(dict.fromkeys(concept.get("supporting_chunk_ids") or []))[:3]
        if not concept_chunk_ids:
            concept_chunk_ids = rank_supporting_chunk_ids(
                str(concept["name"]),
                str(concept["summary"]),
                chunk_rows,
                limit=3,
            )
        conn.execute(
            """
            INSERT INTO concepts (id, doc_id, name, description, mastery, source_chunks)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                concept_id,
                doc_id,
                cleaned_name,
                concept["description"],
                concept["mastery"],
                json.dumps(concept_chunk_ids),
            ),
        )

        question = build_question_record(concept, concept_payloads, filename)
        question_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO questions (id, concept_id, type, difficulty, question, answer, distractors, explanation)
            VALUES (?, ?, 'mcq', ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                concept_id,
                question["difficulty_value"],
                question["question"],
                question["answer"],
                json.dumps(question["distractors"]),
                question["explanation"],
            ),
        )

        concept_evidence_ids: List[str] = []
        for chunk_id in concept_chunk_ids:
            chunk_item = next((item for item in chunk_rows if item["id"] == chunk_id), None)
            if not chunk_item:
                continue
            snippet = sentence_for_term(str(chunk_item["content"]), str(concept["name"]))
            if not snippet:
                continue
            try:
                evidence = provenance_service.build_evidence_reference(
                    conn,
                    {
                        "document_id": doc_id,
                        "chunk_id": chunk_id,
                        "snippet": snippet,
                        "page_num": chunk_item["page_num"],
                        "section": chunk_item["section"],
                    },
                    concept_id=concept_id,
                    confidence=0.7,
                )
                concept_evidence_ids.append(evidence["id"])
            except Exception:
                pass

        if concept_evidence_ids:
            provenance_service.link_evidence_to_quiz(conn, question_id, concept_evidence_ids)

        # PR 0a: auto-card creation on upload is gated. The default
        # (off) makes uploads a pure ingest-and-extract pass; the user
        # then triggers AI card drafting from the document detail view
        # via CardAiDraftDialog. Set CARREL_AUTO_CARD_DRAFT=true to
        # restore the legacy behaviour (escape hatch for tests).
        if _auto_card_draft_enabled():
            _draft_cards_for_concept(
                conn,
                concept=concept,
                concept_payloads=concept_payloads,
                concept_id=concept_id,
                concept_evidence_ids=concept_evidence_ids,
            )

        _extract_concept_depth(conn, concept_id, concept["name"], learning_text, concept_chunk_ids)

    fallback_edges = [
        {
            "source_name": left["name"],
            "target_name": right["name"],
            "relationship": relationship,
        }
        for index, left in enumerate(concept_payloads)
        for right in concept_payloads[index + 1 :]
        for relationship in [infer_relationship(left["name"], right["name"], learning_text)]
        if relationship
    ]
    concept_id_by_name = {
        concept["name"]: concept_id for concept, concept_id in zip(concept_payloads, concept_ids)
    }
    for edge in fallback_edges:
        source_id = concept_id_by_name.get(edge["source_name"])
        target_id = concept_id_by_name.get(edge["target_name"])
        if not source_id or not target_id or source_id == target_id:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO concept_edges (source_id, target_id, doc_id, relationship, weight)
            VALUES (?, ?, ?, ?, 1)
            """,
            (source_id, target_id, doc_id, edge["relationship"]),
        )

    conn.execute(
        """
        UPDATE documents
        SET status = 'ready',
            parser_status = ?,
            parser_diagnostics = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            "ready" if learning_text else "warning",
            json.dumps(parser_diagnostics, ensure_ascii=False),
            doc_id,
        ),
    )
    conn.commit()
    return {
        "doc_id": doc_id,
        "status": "ready",
        "summary": document_summary,
        "subject_name": normalized_subject,
        "preview_text": parser_diagnostics.get("preview_text") or learning_text[:1200],
        "parser_status": "ready" if learning_text else "warning",
        "extraction": parser_diagnostics,
        "filename": filename,
        "file_type": file_type,
        "page_count": page_count,
        "duplicate_of": duplicate_of,
    }
