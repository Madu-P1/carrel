import sqlite3
from typing import Any, Dict, List, Optional

from services.documents import clean_concept_label
from services.helpers import concept_positions
from services.ingestion import normalize_subject_name


def fetch_graph(
    conn: sqlite3.Connection,
    doc_id: Optional[str] = None,
    subject_name: Optional[str] = None,
) -> Dict[str, List[Dict[str, object]]]:
    conditions: List[str] = []
    params: List[Any] = []
    if doc_id:
        conditions.append("c.doc_id = ?")
        params.append(doc_id)
    elif subject_name:
        conditions.append("d.subject_name = ?")
        params.append(normalize_subject_name(subject_name))
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    nodes = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT c.id, c.doc_id AS document_id, c.name AS raw_label, c.mastery, c.description,
                   d.filename AS document_name, d.subject_name
            FROM concepts c
            JOIN documents d ON d.id = c.doc_id
            {where_clause}
            ORDER BY d.subject_name ASC, d.filename ASC, c.rowid ASC
            """,
            params,
        ).fetchall()
    ]
    for node in nodes:
        node["label"] = clean_concept_label(node.get("raw_label"))
    nodes = concept_positions(nodes)
    node_ids = [node["id"] for node in nodes]
    if not node_ids:
        return {"nodes": [], "edges": []}
    placeholders = ",".join("?" * len(node_ids))
    edges = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT source_id AS source, target_id AS target, relationship, weight, doc_id AS document_id
            FROM concept_edges
            WHERE source_id IN ({placeholders}) AND target_id IN ({placeholders})
            ORDER BY rowid ASC
            """,
            node_ids + node_ids,
        ).fetchall()
    ]
    return {"nodes": nodes, "edges": edges}
