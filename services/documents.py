import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

import db
from services import stale_tracker
from services.extraction_pipeline import IngestedAsset
from services.ingestion.persistence import delete_chunk_vectors, node_embeddings_table_exists
from services.ingestion import normalize_subject_name, summarize_document
from services.ingestion.text_utils import clean_learning_text


def load_messages(raw):
    if not raw:
        return []
    try:
        import json

        return json.loads(raw)
    except Exception:
        return []


SELECTOR_CACHE_PREFIX = "concept_selector:"
SELECTOR_LIMIT = 8
SELECTOR_NOISE_PATTERNS = [
    r"all rights reserved",
    r"all right reserved",
    r"copyright",
    r"pearson education",
    r"\bltd\b",
    r"\breserved\b",
]


def _get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def compute_document_source_hash(
    *,
    asset: Optional[IngestedAsset] = None,
    raw_text: Optional[str] = None,
) -> str:
    """Compute the `documents.source_hash` value for an upload.

    Matches the derivation used by `services.ingestion.orchestrator.ingest_document_record`
    so a pre-write duplicate check sees the same value the orchestrator would
    store. Truncated to 32 hex chars (128 bits) — the column convention.

    - File uploads: pass the extraction `asset`. Its `content_hash` is a
      SHA-256 of the raw file bytes, so re-exports with different metadata
      still hash the same as the original.
    - Manual text: pass `raw_text`. We hash the cleaned learning text, which
      normalises whitespace + de-boilerplates. Two pastes that only differ
      in trailing whitespace therefore match.
    """
    if asset is not None and getattr(asset, "content_hash", None):
        return str(asset.content_hash)[:32]
    text_for_hash = clean_learning_text(raw_text or "")
    return stale_tracker.compute_source_hash(text_for_hash)[:32]


def find_duplicate_groups(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Find every cluster of documents that share a source_hash.

    Returns one entry per cluster with 2+ members. Each entry exposes:

      source_hash    — the shared hash
      canonical      — the survivor (oldest upload_date, rowid tiebreak)
      duplicates     — every other row in the cluster, oldest-first
      total_cards    — SRS cards bound to the duplicate-only docs (what a
                       cleanup would delete from the review queue). Useful
                       so the UI can warn "this will remove 47 flashcards."

    Canonical choice: oldest. Rationale — earliest upload is what the user's
    existing citation flights, annotations, and session history probably
    reference. Newer dupes tend to be accidental re-drops.

    Rows with NULL source_hash are ignored (pre-hashing legacy rows). An
    empty DB returns []; a DB with no duplicates returns [].
    """
    rows = conn.execute(
        """
        SELECT source_hash, COUNT(*) AS cnt
        FROM documents
        WHERE source_hash IS NOT NULL AND source_hash <> ''
        GROUP BY source_hash
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        """
    ).fetchall()

    groups: List[Dict[str, Any]] = []
    for row in rows:
        source_hash = row["source_hash"]
        members = [
            dict(member)
            for member in conn.execute(
                """
                SELECT id, filename, subject_name, file_type, upload_date,
                       page_count, status, duplicate_of
                FROM documents
                WHERE source_hash = ?
                ORDER BY
                    CASE WHEN upload_date IS NULL THEN 1 ELSE 0 END,
                    upload_date ASC,
                    rowid ASC
                """,
                (source_hash,),
            ).fetchall()
        ]
        if len(members) < 2:
            continue
        canonical = members[0]
        duplicates = members[1:]
        duplicate_ids = [d["id"] for d in duplicates]
        if duplicate_ids:
            placeholders = ",".join("?" * len(duplicate_ids))
            card_row = conn.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM srs_cards s
                JOIN concepts c ON s.concept_id = c.id
                WHERE c.doc_id IN ({placeholders})
                """,
                duplicate_ids,
            ).fetchone()
            total_cards = int(card_row["n"] if card_row else 0)
        else:
            total_cards = 0
        groups.append(
            {
                "source_hash": source_hash,
                "canonical": canonical,
                "duplicates": duplicates,
                "total_cards": total_cards,
            }
        )
    return groups


def cleanup_duplicate_documents(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Delete every non-canonical row in every duplicate cluster.

    Returns a structured summary so the caller can render "N deleted across
    M groups; kept K canonicals." On `dry_run=True` the function computes
    the same plan but does not mutate the DB — useful for a preview endpoint
    or test assertions.

    Safety notes:
      - Uses `delete_document_record` per row, which cascades through
        concepts, srs_cards, notes, chunks, and chunk vectors. Same semantics
        as a manual "Delete document" click.
      - Commits per row (via delete_document_record's internal commit). If
        one delete fails midway, the prior successful deletes stay — the
        summary records `deleted` accurately.
      - After cleanup, any remaining row that pointed at a now-deleted
        canonical (via `duplicate_of`) would be orphaned, but because we
        only delete the NON-canonical members and canonicals stay, this
        cannot happen. Still, we null out dangling `duplicate_of` for the
        canonicals we keep (they might reference each other by accident if
        the history is tangled).
    """
    groups = find_duplicate_groups(conn)
    plan: List[Dict[str, Any]] = []
    for group in groups:
        plan.append(
            {
                "source_hash": group["source_hash"],
                "kept": group["canonical"]["id"],
                "kept_filename": group["canonical"]["filename"],
                "removed": [d["id"] for d in group["duplicates"]],
                "removed_filenames": [d["filename"] for d in group["duplicates"]],
                "cards_removed": group["total_cards"],
            }
        )

    if dry_run:
        return {
            "dry_run": True,
            "groups": len(groups),
            "would_delete": sum(len(p["removed"]) for p in plan),
            "would_remove_cards": sum(p["cards_removed"] for p in plan),
            "plan": plan,
        }

    deleted_total = 0
    cards_removed_total = 0
    for group, summary in zip(groups, plan):
        for duplicate in group["duplicates"]:
            if delete_document_record(conn, duplicate["id"]):
                deleted_total += 1
        cards_removed_total += summary["cards_removed"]
        # Clear any lingering duplicate_of on the canonical so the UI's
        # "duplicates" indicator goes away immediately, even if a race
        # left it pointed at a now-dead row.
        conn.execute(
            "UPDATE documents SET duplicate_of = NULL WHERE id = ?",
            (group["canonical"]["id"],),
        )
    conn.commit()
    return {
        "dry_run": False,
        "groups": len(groups),
        "deleted": deleted_total,
        "cards_removed": cards_removed_total,
        "plan": plan,
    }


def find_canonical_duplicate(
    conn: sqlite3.Connection,
    source_hash: str,
) -> Optional[Dict[str, Any]]:
    """Return the existing canonical document for `source_hash`, if one exists.

    "Canonical" means `duplicate_of IS NULL` — a previously-rejected duplicate
    upload doesn't count as an obstacle to re-uploading after the user has
    deleted the original. We also skip rows whose status marks them as
    aborted (`'deleted'`) so transient failures never block a legitimate
    re-ingest.
    """
    if not source_hash:
        return None
    row = conn.execute(
        """
        SELECT id, filename, subject_name, file_type, upload_date, page_count,
               status
        FROM documents
        WHERE source_hash = ?
          AND duplicate_of IS NULL
          AND COALESCE(status, '') <> 'deleted'
        ORDER BY upload_date ASC
        LIMIT 1
        """,
        (source_hash,),
    ).fetchone()
    return dict(row) if row else None


def _set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


def _selector_cache_key(doc_id: str) -> str:
    return f"{SELECTOR_CACHE_PREFIX}{doc_id}"


def _collapse_repeated_phrase(words: List[str]) -> List[str]:
    """Collapse a token list that is one phrase repeated 2+ times back
    to a single copy: "X Y X Y" -> "X Y", "A B A B A B" -> "A B".

    The doubled-phrase shape leaks in when an LLM emits a concept name
    as "X / X", "X - X", or "X, X" and the separator normalizes to a
    space. The adjacent-word loop in clean_concept_label only catches
    "foo foo bar"; it cannot see "foo bar foo bar". Tokens are compared
    with surrounding punctuation stripped so "Approach," still matches
    "Approach", and the smallest repeating period wins so "X X X X"
    collapses all the way to "X".
    """
    n = len(words)
    if n < 2:
        return words
    norm = [word.lower().strip(".,:;!?-_/\"'()[]") for word in words]
    for period in range(1, n // 2 + 1):
        if n % period != 0:
            continue
        if all(norm[i] == norm[i % period] for i in range(n)):
            return words[:period]
    return words


def clean_concept_label(value: str) -> str:
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(value or ""))
    cleaned = re.sub(r"[_/\\-]+", " ", cleaned)
    cleaned = re.sub(r"([A-Za-z])(\d)", r"\1 \2", cleaned)
    cleaned = re.sub(r"(\d)([A-Za-z])", r"\1 \2", cleaned)
    for pattern in SELECTOR_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-_")
    deduped_words: List[str] = []
    for word in cleaned.split():
        if not deduped_words or deduped_words[-1].lower() != word.lower():
            deduped_words.append(word)
    # Phrase-level dedup. The adjacent-word loop above only catches
    # "foo foo bar"; it cannot see "foo bar foo bar" as a duplicate
    # phrase. _collapse_repeated_phrase folds any whole-list repetition
    # (any period, any repeat count, punctuation-tolerant).
    deduped_words = _collapse_repeated_phrase(deduped_words)
    cleaned = " ".join(deduped_words).strip(" .,:;-_")
    return cleaned or "Study concept"


def _concept_name_replacements(concepts: List[Dict[str, Any]]) -> List[tuple[str, str]]:
    pairs: List[tuple[str, str]] = []
    seen = set()
    for concept in concepts:
        raw_name = str(concept.get("name") or "").strip()
        if not raw_name or raw_name in seen:
            continue
        seen.add(raw_name)
        cleaned = clean_concept_label(raw_name)
        if cleaned and cleaned != raw_name:
            pairs.append((raw_name, cleaned))
    return pairs


def _normalize_concept_text(text: str, replacements: List[tuple[str, str]]) -> str:
    value = str(text or "")
    for raw_name, cleaned in replacements:
        value = value.replace(raw_name, cleaned)
    return value


def _selector_reason(concept: Dict[str, Any], goal: str) -> str:
    reason_parts = []
    if goal:
        goal_tokens = {token for token in re.findall(r"[a-z0-9]+", goal.lower()) if len(token) > 3}
        concept_text = f"{concept.get('name', '')} {concept.get('description', '')}".lower()
        if goal_tokens and any(token in concept_text for token in goal_tokens):
            reason_parts.append("Aligned with the current learning goal")
    if concept.get("description"):
        reason_parts.append("Grounded in the document's extracted explanation")
    if concept.get("source_chunk_ids"):
        reason_parts.append("Backed by source chunks")
    return ". ".join(reason_parts[:2]) or "Selected as a high-signal study concept."


def _selector_score(concept: Dict[str, Any], goal: str) -> float:
    raw_name = str(concept.get("name") or "")
    clean_name = clean_concept_label(raw_name)
    description = str(concept.get("description") or "")
    score = 50.0
    if clean_name != raw_name.strip():
        score += 8
    if 2 <= len(clean_name.split()) <= 6:
        score += 10
    if description:
        score += min(len(description) / 24, 12)
    if concept.get("source_chunk_ids"):
        score += 8
    try:
        score += float(concept.get("mastery") or 0) * 5
    except (TypeError, ValueError):
        pass
    if goal:
        goal_tokens = {token for token in re.findall(r"[a-z0-9]+", goal.lower()) if len(token) > 3}
        concept_text = f"{raw_name} {description}".lower()
        score += sum(6 for token in goal_tokens if token in concept_text)
    if len(clean_name) < 4:
        score -= 25
    if any(
        re.search(pattern, raw_name, flags=re.IGNORECASE) for pattern in SELECTOR_NOISE_PATTERNS
    ):
        score -= 20
    return score


def _build_selector_context(
    concepts: List[Dict[str, Any]],
    chunk_items: List[Dict[str, Any]],
) -> str:
    chunk_lookup = {item["id"]: item.get("content", "") for item in chunk_items}
    blocks = []
    for concept in concepts:
        chunk_preview = ""
        for chunk_id in concept.get("source_chunk_ids", [])[:2]:
            content = chunk_lookup.get(chunk_id, "").strip()
            if content:
                chunk_preview = " ".join(content.split())[:280]
                break
        blocks.append(
            "\n".join(
                [
                    f"Concept id: {concept['id']}",
                    f"Raw name: {concept.get('name', '')}",
                    f"Description: {concept.get('description', '')}",
                    f"Preview: {chunk_preview}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _fallback_concept_options(
    concepts: List[Dict[str, Any]],
    goal: str,
) -> List[Dict[str, Any]]:
    ordered = sorted(
        concepts,
        key=lambda item: (-_selector_score(item, goal), str(item.get("name") or "").lower()),
    )
    if len(ordered) > SELECTOR_LIMIT:
        ordered = ordered[:SELECTOR_LIMIT]
    curated: List[Dict[str, Any]] = []
    seen_labels = set()
    for concept in ordered:
        label = clean_concept_label(str(concept.get("name") or ""))
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        curated.append(
            {
                "concept_id": concept["id"],
                "display_name": label,
                "reason": _selector_reason(concept, goal),
            }
        )
    return curated or [
        {
            "concept_id": concept["id"],
            "display_name": clean_concept_label(str(concept.get("name") or "Study concept")),
            "reason": "Fallback selector option.",
        }
        for concept in concepts[:1]
    ]


def _concept_selector_signature(
    document_row: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    goal: str,
) -> str:
    payload = {
        "doc_id": document_row["id"],
        "filename": document_row["filename"],
        "goal": goal,
        "concepts": [
            {
                "id": item["id"],
                "name": item.get("name"),
                "description": item.get("description"),
                "mastery": item.get("mastery"),
            }
            for item in concepts
        ],
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()


def build_concept_options(
    conn: sqlite3.Connection,
    *,
    document_row: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    chunk_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not concepts:
        return []

    goal = _get_setting(conn, "learning_goal", "")
    signature = _concept_selector_signature(document_row, concepts, goal)
    cache_key = _selector_cache_key(document_row["id"])
    cached = load_messages(_get_setting(conn, cache_key, ""))
    if (
        isinstance(cached, dict)
        and cached.get("signature") == signature
        and isinstance(cached.get("options"), list)
    ):
        cached_options = cached["options"]
    else:
        cached_options = _fallback_concept_options(concepts, goal)
        _set_setting(
            conn, cache_key, json.dumps({"signature": signature, "options": cached_options})
        )

    by_id = {concept["id"]: concept for concept in concepts}
    selected: List[Dict[str, Any]] = []
    seen = set()
    for rank, item in enumerate(cached_options):
        concept = by_id.get(item.get("concept_id"))
        if not concept or concept["id"] in seen:
            continue
        seen.add(concept["id"])
        selected.append(
            {
                **concept,
                "raw_name": concept.get("name"),
                "name": item.get("display_name")
                or clean_concept_label(str(concept.get("name") or "")),
                "selector_reason": item.get("reason") or _selector_reason(concept, goal),
                "selector_rank": rank,
            }
        )

    if not selected:
        return [
            {
                **concept,
                "raw_name": concept.get("name"),
                "name": clean_concept_label(str(concept.get("name") or "")),
                "selector_reason": _selector_reason(concept, goal),
                "selector_rank": index,
            }
            for index, concept in enumerate(concepts[:SELECTOR_LIMIT])
        ]
    return selected


def collect_document_concepts(conn: sqlite3.Connection, doc_id: str) -> List[Dict[str, object]]:
    if not doc_id:
        return []
    rows = conn.execute(
        """
        SELECT c.id, c.doc_id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name,
               d.subject_name
        FROM concepts c
        JOIN documents d ON d.id = c.doc_id
        WHERE c.doc_id = ?
        ORDER BY c.rowid ASC
        """,
        (doc_id,),
    ).fetchall()
    concepts: List[Dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["source_chunk_ids"] = load_messages(item["source_chunks"])
        item.pop("source_chunks", None)
        item["display_name"] = clean_concept_label(item.get("name"))
        concepts.append(item)
    return concepts


def fetch_documents(conn: sqlite3.Connection) -> List[Dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, filename, storage_name, subject_name, file_type, upload_date, page_count, status,
               source_kind, source_hash, parser_status, parser_diagnostics, duplicate_of, updated_at, extracted_at
        FROM documents
        ORDER BY subject_name ASC, upload_date DESC
        """
    ).fetchall()
    documents: List[Dict[str, object]] = []
    for row in rows:
        item = dict(row)
        try:
            item["parser_diagnostics"] = json.loads(item.get("parser_diagnostics") or "{}")
        except Exception:
            item["parser_diagnostics"] = {}
        item["confidence"] = _document_confidence(item["parser_diagnostics"])
        detail = fetch_document_detail(
            conn, item["id"], include_chunks=False, include_selector_options=False
        )
        item["summary"] = detail["summary"]
        item["concept_count"] = detail["counts"]["concepts"]
        item["question_count"] = detail["counts"]["questions"]
        documents.append(item)
    return documents


def fetch_document_detail(
    conn: sqlite3.Connection,
    doc_id: str,
    include_chunks: bool = True,
    include_selector_options: bool = True,
) -> Dict[str, object]:
    document_row = conn.execute(
        """
        SELECT id, filename, storage_name, subject_name, file_type, upload_date, page_count, status,
               source_kind, source_hash, parser_status, parser_diagnostics, duplicate_of, updated_at, extracted_at
        FROM documents
        WHERE id = ?
        """,
        (doc_id,),
    ).fetchone()
    if not document_row:
        raise HTTPException(status_code=404, detail="Document not found")

    chunk_rows = conn.execute(
        """
        SELECT id, section, page_num, chunk_index, token_count, content, chunk_hash, provenance_json, embedding_status
        FROM chunks
        WHERE doc_id = ?
        ORDER BY chunk_index ASC
        """,
        (doc_id,),
    ).fetchall()
    chunk_items = []
    for row in chunk_rows:
        item = dict(row)
        try:
            item["provenance_json"] = json.loads(item.get("provenance_json") or "{}")
        except Exception:
            item["provenance_json"] = {}
        chunk_items.append(item)
    combined_text = "\n\n".join(item["content"] for item in chunk_items)
    summary = summarize_document(combined_text) if combined_text else "No extracted content yet."
    document_item = dict(document_row)
    try:
        document_item["parser_diagnostics"] = json.loads(
            document_item.get("parser_diagnostics") or "{}"
        )
    except Exception:
        document_item["parser_diagnostics"] = {}
    document_item["confidence"] = _document_confidence(document_item["parser_diagnostics"])

    concepts = collect_document_concepts(conn, doc_id)
    replacements = _concept_name_replacements(concepts)
    concept_ids = [item["id"] for item in concepts]
    questions: List[Dict[str, object]] = []
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        question_rows = conn.execute(
            f"""
            SELECT q.id, q.question, q.answer, q.explanation, q.difficulty, c.name AS concept
            FROM questions q
            JOIN concepts c ON q.concept_id = c.id
            WHERE q.concept_id IN ({placeholders})
            ORDER BY q.rowid ASC
            """,
            concept_ids,
        ).fetchall()
        for row in question_rows:
            item = dict(row)
            item["difficulty"] = (
                "Hard"
                if item["difficulty"] >= 0.7
                else "Medium"
                if item["difficulty"] >= 0.45
                else "Easy"
            )
            item["raw_concept"] = item["concept"]
            item["concept"] = clean_concept_label(item["concept"])
            item["question"] = _normalize_concept_text(item["question"], replacements)
            item["answer"] = _normalize_concept_text(item["answer"], replacements)
            item["explanation"] = _normalize_concept_text(item["explanation"], replacements)
            questions.append(item)

    cards_count = 0
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        cards_count = conn.execute(
            f"SELECT COUNT(*) AS total FROM srs_cards WHERE concept_id IN ({placeholders})",
            concept_ids,
        ).fetchone()["total"]

    detail = {
        "document": document_item,
        "summary": summary,
        "concepts": concepts,
        "questions": questions,
        "counts": {
            "chunks": len(chunk_items),
            "concepts": len(concepts),
            "questions": len(questions),
            "cards": cards_count,
        },
    }
    if include_selector_options:
        detail["concept_options"] = build_concept_options(
            conn,
            document_row=dict(document_row),
            concepts=concepts,
            chunk_items=chunk_items,
        )
    if include_chunks:
        detail["chunks"] = chunk_items
    return detail


def delete_document_record(conn: sqlite3.Connection, doc_id: str) -> bool:
    document_row = conn.execute(
        "SELECT storage_name FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    if not document_row:
        return False
    # Concept-graph cascade: a document's concepts and everything bound to them.
    # (Empty for a Cachet-ingested record, which carries no tutor concepts.)
    # Deliberately scoped: this sweeps the concept's own leaves; the deeper Carrel
    # junction/log tables keyed off questions/cards/notes (quiz_log, review_events,
    # flashcard_evidence, quiz_evidence, note_evidence, card_pairs, mastery_states,
    # dialogue_sessions) are a pre-existing study-app cascade gap, never populated by
    # a Cachet record, and are left out here rather than risk a Carrel regression.
    # Session/goal/artifact rows are NOT document-scoped and must never be deleted on
    # a document delete.
    concept_ids = [concept["id"] for concept in collect_document_concepts(conn, doc_id)]
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        conn.execute(f"DELETE FROM questions WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(f"DELETE FROM srs_cards WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(f"DELETE FROM notes WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(f"DELETE FROM study_events WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(f"DELETE FROM claims WHERE concept_id IN ({placeholders})", concept_ids)
        conn.execute(
            f"DELETE FROM concept_examples WHERE concept_id IN ({placeholders})", concept_ids
        )
        conn.execute(
            f"DELETE FROM misconceptions WHERE concept_id IN ({placeholders})", concept_ids
        )
        conn.execute(
            f"DELETE FROM concept_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
            concept_ids * 2,
        )
        conn.execute(f"DELETE FROM concepts WHERE id IN ({placeholders})", concept_ids)
    # Document-bound rows NOT reached through a concept. PRAGMA foreign_keys is off
    # on these connections (db.py sets WAL/busy_timeout/synchronous only), so the
    # schema's ON DELETE CASCADE never fires; every child is removed by hand,
    # children before the parent, all inside the single transaction committed below.
    conn.execute("DELETE FROM notes WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM study_events WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM srs_cards WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM concept_edges WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM evidence_references WHERE source_id = ?", (doc_id,))
    conn.execute("DELETE FROM stale_dependencies WHERE source_id = ?", (doc_id,))
    conn.execute("DELETE FROM anchors WHERE document_id = ?", (doc_id,))
    # Typed nodes (the verification retrieval path): drop their vec0 embeddings
    # first (no trigger maintains node_embeddings), then the nodes; the
    # nodes_fts_delete trigger keeps the node_fts index in sync.
    if node_embeddings_table_exists(conn):
        conn.execute(
            "DELETE FROM node_embeddings WHERE node_id IN (SELECT id FROM nodes WHERE doc_id = ?)",
            (doc_id,),
        )
    conn.execute("DELETE FROM nodes WHERE doc_id = ?", (doc_id,))
    # Chunks and their vec0 vectors; chunks_fts is trigger-maintained.
    chunk_rowids = [
        int(row["rowid"])
        for row in conn.execute(
            "SELECT rowid FROM chunks WHERE doc_id = ?",
            (doc_id,),
        ).fetchall()
    ]
    delete_chunk_vectors(conn, chunk_rowids)
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    # A document can be the duplicate_of target of others; clear the dangling pointer
    # so no row points at an id that is about to disappear.
    conn.execute("UPDATE documents SET duplicate_of = NULL WHERE duplicate_of = ?", (doc_id,))
    # These two carry a doc pointer the schema marks ON DELETE SET NULL, but FK
    # enforcement is off, so null them by hand to honor that intent (otherwise a
    # planning suggestion or ingestion job keeps a pointer to a deleted record).
    conn.execute("UPDATE study_suggestions SET doc_id = NULL WHERE doc_id = ?", (doc_id,))
    conn.execute("UPDATE ingestion_jobs SET document_id = NULL WHERE document_id = ?", (doc_id,))
    conn.execute("DELETE FROM app_settings WHERE key = ?", (_selector_cache_key(doc_id),))
    deleted = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,)).rowcount
    conn.commit()
    storage_name = document_row["storage_name"]
    if deleted and storage_name:
        stored_path = db.UPLOAD_DIR / storage_name
        if stored_path.exists():
            stored_path.unlink()
    return bool(deleted)


def fetch_subject_groups(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT subject_name, COUNT(*) AS document_count
        FROM documents
        GROUP BY subject_name
        ORDER BY subject_name ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def list_vault_names(conn: sqlite3.Connection) -> List[str]:
    """Every vault the UI should show: the distinct subject_names documents are
    filed under, plus the empty-vault registry. A vault appears whether it was
    created empty or implied by a filed record.

    Vault identity is case-insensitive ('General' and 'general' are one vault), so
    the list is deduped on lowercased name. The registry spelling wins over a filed
    subject's, so the canonical folder name is what shows."""
    registry = [
        row["name"]
        for row in conn.execute("SELECT name FROM document_vaults").fetchall()
        if row["name"]
    ]
    filed = [
        row["name"]
        for row in conn.execute(
            "SELECT DISTINCT subject_name AS name FROM documents WHERE subject_name IS NOT NULL"
        ).fetchall()
        if row["name"]
    ]
    by_lower: Dict[str, str] = {}
    for name in registry:  # registry first: its spelling is canonical
        by_lower.setdefault(name.lower(), name)
    for name in filed:
        by_lower.setdefault(name.lower(), name)
    return sorted(by_lower.values(), key=str.lower)


def _existing_vault_spelling(conn: sqlite3.Connection, normalized: str) -> Optional[str]:
    """The spelling already in use for this name, compared case-insensitively, so a
    case-variant resolves to the existing vault instead of forking a duplicate. The
    registry spelling is preferred over a filed subject's. None if the name is new."""
    row = conn.execute(
        "SELECT name FROM document_vaults WHERE name = ? COLLATE NOCASE LIMIT 1",
        (normalized,),
    ).fetchone()
    if row:
        return row["name"]
    row = conn.execute(
        "SELECT subject_name FROM documents "
        "WHERE subject_name IS NOT NULL AND subject_name = ? COLLATE NOCASE LIMIT 1",
        (normalized,),
    ).fetchone()
    return row["subject_name"] if row else None


def create_vault(conn: sqlite3.Connection, name: str) -> str:
    """Register a (possibly empty) vault so it persists before its first record.
    Idempotent and case-insensitive: registering an existing name (in any casing)
    is a no-op that returns the existing spelling. Returns the canonical name.
    Raises ValueError on a blank name (rather than silently defaulting it to
    'General', which would create a vault the user did not name)."""
    if not name or not name.strip():
        raise ValueError("A vault needs a name.")
    normalized = normalize_subject_name(name)
    canonical = _existing_vault_spelling(conn, normalized) or normalized
    conn.execute("INSERT OR IGNORE INTO document_vaults (name) VALUES (?)", (canonical,))
    conn.commit()
    return canonical


def delete_vault(conn: sqlite3.Connection, name: str) -> bool:
    """Forget an EMPTY vault. Refuses (returns False) if any record is still filed
    under it, so deleting a vault never silently moves or destroys records. The
    caller surfaces the refusal; the records are moved or deleted first."""
    # Guard the RAW name: normalize_subject_name defaults a blank to 'General', so
    # checking the normalized value would let an all-whitespace name silently
    # target the General vault. Refuse a blank name outright.
    if not name or not name.strip():
        return False
    normalized = normalize_subject_name(name)
    in_use = conn.execute(
        "SELECT 1 FROM documents WHERE subject_name = ? LIMIT 1", (normalized,)
    ).fetchone()
    if in_use:
        return False
    conn.execute("DELETE FROM document_vaults WHERE name = ?", (normalized,))
    conn.commit()
    return True


def list_subject_summaries(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Per-subject dashboard payload for the Library home grid.

    Each row returns the stats a subject card needs to render:
      subject_name       — the group label
      source_count       — total documents in this subject
      failed_count       — documents whose parser_status is not 'ready'
      flashcard_count    — SRS cards bound to concepts in this subject
      last_studied_at    — max(study_events.created_at) across docs in this
                           subject; null when the user has never studied any
                           source here
      first_failed_doc   — {id, filename, error} for the first failed doc so
                           the card can render an inline error with a direct
                           "Retry" action. Null when nothing failed.

    This is a pure read. One query per metric, joined in Python — the
    workspace has <100 subjects in any realistic deployment, so the extra
    round-trip beats a four-way JOIN that SQLite would plan badly.
    """
    subject_rows = conn.execute(
        """
        SELECT
            COALESCE(NULLIF(TRIM(subject_name), ''), 'General') AS subject_name,
            COUNT(*) AS source_count,
            SUM(CASE WHEN COALESCE(parser_status, 'ready') != 'ready' THEN 1 ELSE 0 END) AS failed_count
        FROM documents
        GROUP BY COALESCE(NULLIF(TRIM(subject_name), ''), 'General')
        ORDER BY source_count DESC, subject_name ASC
        """
    ).fetchall()

    summaries: List[Dict[str, Any]] = []
    for row in subject_rows:
        subject = row["subject_name"]
        cards_row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM srs_cards s
            JOIN concepts c ON s.concept_id = c.id
            JOIN documents d ON c.doc_id = d.id
            WHERE COALESCE(NULLIF(TRIM(d.subject_name), ''), 'General') = ?
            """,
            (subject,),
        ).fetchone()
        last_studied_row = conn.execute(
            """
            SELECT MAX(e.created_at) AS ts
            FROM study_events e
            JOIN documents d ON e.doc_id = d.id
            WHERE COALESCE(NULLIF(TRIM(d.subject_name), ''), 'General') = ?
            """,
            (subject,),
        ).fetchone()
        failed_doc_row = conn.execute(
            """
            SELECT id, filename, parser_status, parser_diagnostics
            FROM documents
            WHERE COALESCE(NULLIF(TRIM(subject_name), ''), 'General') = ?
              AND COALESCE(parser_status, 'ready') != 'ready'
            ORDER BY upload_date ASC
            LIMIT 1
            """,
            (subject,),
        ).fetchone()
        first_failed: Optional[Dict[str, Any]] = None
        if failed_doc_row:
            diagnostics = failed_doc_row["parser_diagnostics"] or "{}"
            try:
                diag_dict = json.loads(diagnostics) if isinstance(diagnostics, str) else diagnostics
            except Exception:
                diag_dict = {}
            warnings = []
            if isinstance(diag_dict, dict):
                quality = diag_dict.get("quality") or {}
                if isinstance(quality, dict):
                    warnings = [str(w) for w in (quality.get("warnings") or [])]
            first_failed = {
                "id": failed_doc_row["id"],
                "filename": failed_doc_row["filename"],
                "status": failed_doc_row["parser_status"],
                "error": warnings[0] if warnings else "Parser reported a problem with this source.",
            }
        summaries.append(
            {
                "subject_name": subject,
                "source_count": int(row["source_count"] or 0),
                "failed_count": int(row["failed_count"] or 0),
                "flashcard_count": int(cards_row["n"] if cards_row else 0),
                "last_studied_at": last_studied_row["ts"] if last_studied_row else None,
                "first_failed_doc": first_failed,
            }
        )
    return summaries


def set_document_subject(
    conn: sqlite3.Connection, doc_id: str, subject_name: str
) -> Dict[str, Any]:
    normalized_subject = normalize_subject_name(subject_name)
    updated = conn.execute(
        "UPDATE documents SET subject_name = ? WHERE id = ?",
        (normalized_subject, doc_id),
    ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")
    conn.commit()
    row = conn.execute(
        """
        SELECT id, filename, storage_name, subject_name, file_type, upload_date, page_count, status,
               source_kind, source_hash, parser_status, parser_diagnostics, duplicate_of, updated_at, extracted_at
        FROM documents
        WHERE id = ?
        """,
        (doc_id,),
    ).fetchone()
    item = dict(row)
    try:
        item["parser_diagnostics"] = json.loads(item.get("parser_diagnostics") or "{}")
    except Exception:
        item["parser_diagnostics"] = {}
    item["confidence"] = _document_confidence(item["parser_diagnostics"])
    detail = fetch_document_detail(
        conn, doc_id, include_chunks=False, include_selector_options=False
    )
    item["summary"] = detail["summary"]
    item["concept_count"] = detail["counts"]["concepts"]
    item["question_count"] = detail["counts"]["questions"]
    return item


def _document_confidence(parser_diagnostics: Dict[str, Any]) -> Optional[float]:
    quality = parser_diagnostics.get("quality")
    if not isinstance(quality, dict):
        return None

    confidence = quality.get("confidence")
    if isinstance(confidence, (int, float)):
        return float(confidence)
    return None
