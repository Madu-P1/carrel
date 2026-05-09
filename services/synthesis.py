"""Cross-source synthesis — compare sources, detect contradictions, identify gaps."""

import sqlite3
from typing import Any, Dict, List

from services.documents import clean_concept_label
from services.helpers import split_sentences, tokenize


def _doc_concepts(conn: sqlite3.Connection, doc_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, description, mastery FROM concepts WHERE doc_id = ?",
        (doc_id,),
    ).fetchall()
    concepts: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["raw_name"] = item["name"]
        item["name"] = clean_concept_label(item["name"])
        concepts.append(item)
    return concepts


def _doc_chunks(conn: sqlite3.Connection, doc_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, content, section, page_num FROM chunks WHERE doc_id = ? ORDER BY chunk_index ASC LIMIT ?",
        (doc_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _token_overlap(text_a: str, text_b: str) -> float:
    tokens_a = set(tokenize(text_a))
    tokens_b = set(tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)


def _doc_meta(conn: sqlite3.Connection, doc_id: str) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT id, filename, subject_name, status FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    return (
        dict(row)
        if row
        else {"id": doc_id, "filename": "Unknown", "subject_name": None, "status": None}
    )


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------


def detect_contradictions(
    conn: sqlite3.Connection,
    source_ids: List[str],
) -> List[Dict[str, Any]]:
    """Heuristic contradiction detection: find concept pairs with low overlap across sources."""
    if len(source_ids) < 2:
        return []

    contradictions = []
    docs = [
        {"meta": _doc_meta(conn, sid), "concepts": _doc_concepts(conn, sid)} for sid in source_ids
    ]

    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            a_concepts = {c["name"].lower(): c for c in docs[i]["concepts"]}
            b_concepts = {c["name"].lower(): c for c in docs[j]["concepts"]}
            shared_names = set(a_concepts) & set(b_concepts)
            for name in shared_names:
                a_desc = a_concepts[name].get("description") or ""
                b_desc = b_concepts[name].get("description") or ""
                overlap = _token_overlap(a_desc, b_desc)
                if overlap < 0.25 and a_desc and b_desc:
                    contradictions.append(
                        {
                            "concept": name,
                            "source_a": docs[i]["meta"]["filename"],
                            "source_b": docs[j]["meta"]["filename"],
                            "source_a_excerpt": a_desc[:160],
                            "source_b_excerpt": b_desc[:160],
                            "overlap_score": round(overlap, 2),
                            "severity": "high" if overlap < 0.10 else "medium",
                        }
                    )

    return sorted(contradictions, key=lambda x: x["overlap_score"])[:8]


# ---------------------------------------------------------------------------
# Agreement summary
# ---------------------------------------------------------------------------


def summarize_agreement(
    conn: sqlite3.Connection,
    source_ids: List[str],
) -> Dict[str, Any]:
    """Find concepts that appear across multiple sources and share overlapping descriptions."""
    if not source_ids:
        return {"shared_concepts": [], "themes": [], "source_count": 0}

    name_to_docs: Dict[str, List[str]] = {}
    name_to_descriptions: Dict[str, List[str]] = {}

    for sid in source_ids:
        meta = _doc_meta(conn, sid)
        for concept in _doc_concepts(conn, sid):
            key = concept["name"].lower()
            name_to_docs.setdefault(key, []).append(meta["filename"])
            if concept.get("description"):
                name_to_descriptions.setdefault(key, []).append(concept["description"])

    shared = [
        {
            "concept": name,
            "appears_in": docs,
            "source_count": len(docs),
            "combined_excerpt": " ".join(name_to_descriptions.get(name, [])[:2])[:200],
        }
        for name, docs in name_to_docs.items()
        if len(docs) >= 2
    ]
    shared.sort(key=lambda x: -x["source_count"])

    # Extract repeated terms as themes
    all_tokens: Dict[str, int] = {}
    for sid in source_ids:
        for chunk in _doc_chunks(conn, sid, limit=6):
            for token in tokenize(chunk["content"]):
                all_tokens[token] = all_tokens.get(token, 0) + 1

    themes = [
        t for t, c in sorted(all_tokens.items(), key=lambda x: -x[1]) if c >= len(source_ids)
    ][:8]

    return {
        "shared_concepts": shared[:8],
        "themes": themes,
        "source_count": len(source_ids),
    }


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


def identify_gaps(
    conn: sqlite3.Connection,
    source_ids: List[str],
) -> List[Dict[str, Any]]:
    """Identify concepts in one source missing from others."""
    if len(source_ids) < 2:
        return []

    all_names: Dict[str, set] = {}  # concept_name -> set of doc_ids that have it
    for sid in source_ids:
        for concept in _doc_concepts(conn, sid):
            key = concept["name"].lower()
            all_names.setdefault(key, set()).add(sid)

    gaps = []
    for name, doc_set in all_names.items():
        missing = [sid for sid in source_ids if sid not in doc_set]
        if missing:
            meta_present = _doc_meta(conn, next(iter(doc_set)))
            gaps.append(
                {
                    "concept": name,
                    "present_in": meta_present["filename"],
                    "missing_from_count": len(missing),
                    "gap_severity": "high" if len(missing) >= len(source_ids) - 1 else "low",
                }
            )

    return sorted(gaps, key=lambda x: -x["missing_from_count"])[:10]


# ---------------------------------------------------------------------------
# Terminology alignment
# ---------------------------------------------------------------------------


def align_terminology(
    conn: sqlite3.Connection,
    source_ids: List[str],
) -> List[Dict[str, Any]]:
    """Find concepts where the name differs but descriptions overlap significantly."""
    if len(source_ids) < 2:
        return []

    all_concepts: List[Dict[str, Any]] = []
    for sid in source_ids:
        meta = _doc_meta(conn, sid)
        for c in _doc_concepts(conn, sid):
            all_concepts.append({**c, "source": meta["filename"], "source_id": sid})

    mismatches = []
    seen: set = set()
    for i, a in enumerate(all_concepts):
        for b in all_concepts[i + 1 :]:
            if a["source_id"] == b["source_id"]:
                continue
            key = tuple(sorted([a["id"], b["id"]]))
            if key in seen:
                continue
            seen.add(key)
            a_desc = a.get("description") or ""
            b_desc = b.get("description") or ""
            overlap = _token_overlap(a_desc, b_desc)
            name_overlap = _token_overlap(a["name"], b["name"])
            if overlap >= 0.45 and name_overlap < 0.3:
                mismatches.append(
                    {
                        "name_a": a["name"],
                        "name_b": b["name"],
                        "source_a": a["source"],
                        "source_b": b["source"],
                        "description_overlap": round(overlap, 2),
                        "note": f'"{a["name"]}" and "{b["name"]}" may refer to the same idea.',
                    }
                )

    return mismatches[:6]


# ---------------------------------------------------------------------------
# Full synthesis dispatch
# ---------------------------------------------------------------------------


def run_synthesis(
    conn: sqlite3.Connection,
    source_ids: List[str],
    synthesis_type: str = "compare",
) -> Dict[str, Any]:
    """Run one of the synthesis modes using only stored source-backed data."""
    sources_meta = [_doc_meta(conn, sid) for sid in source_ids]
    return _run_rule_based_synthesis(conn, source_ids, synthesis_type, sources_meta)


def _run_rule_based_synthesis(
    conn: sqlite3.Connection,
    source_ids: List[str],
    synthesis_type: str,
    sources_meta: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Rule-based fallback synthesis."""
    if synthesis_type == "agreement":
        agreement = summarize_agreement(conn, source_ids)
        return {
            "synthesis_type": "agreement",
            "sources": sources_meta,
            "shared_concepts": agreement["shared_concepts"],
            "themes": agreement["themes"],
            "contradictions": [],
            "gaps": [],
            "terminology_mismatches": [],
            "generator": "rule_based",
        }
    if synthesis_type == "gaps":
        gaps = identify_gaps(conn, source_ids)
        return {
            "synthesis_type": "gaps",
            "sources": sources_meta,
            "shared_concepts": [],
            "themes": [],
            "contradictions": [],
            "gaps": gaps,
            "terminology_mismatches": [],
            "generator": "rule_based",
        }
    if synthesis_type == "terminology":
        mismatches = align_terminology(conn, source_ids)
        return {
            "synthesis_type": "terminology",
            "sources": sources_meta,
            "shared_concepts": [],
            "themes": [],
            "contradictions": [],
            "gaps": [],
            "terminology_mismatches": mismatches,
            "generator": "rule_based",
        }
    # Default: full compare
    contradictions = detect_contradictions(conn, source_ids)
    agreement = summarize_agreement(conn, source_ids)
    gaps = identify_gaps(conn, source_ids)
    return {
        "synthesis_type": "compare",
        "sources": sources_meta,
        "shared_concepts": agreement["shared_concepts"],
        "themes": agreement["themes"],
        "contradictions": contradictions,
        "gaps": gaps,
        "terminology_mismatches": [],
        "generator": "rule_based",
    }
