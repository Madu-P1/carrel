from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List

import db
from services import extraction_pipeline
from services.ingestion import ingest_document_record


DEMO_LIBRARY_DIR = Path(__file__).resolve().parent.parent / "assets" / "demo-library"

SAMPLES = [
    {
        "filename": "carrel-demo-clean-reading.pdf",
        "subject_name": "Demo Sources",
        "title": "Clean Reading Sample",
        "fallback_text": """Clean Reading Sample

Active recall improves retention when a learner retrieves an answer before rereading it. A useful study system should turn source evidence into small review prompts. The prompt should test one idea, cite the source, and return later when memory is likely to fade.

Spacing helps because each review happens after some forgetting has occurred. The effort of retrieval strengthens later recall more than immediate repetition.
""",
    },
    {
        "filename": "carrel-demo-table-heavy.pdf",
        "subject_name": "Demo Sources",
        "title": "Table-Heavy Sample",
        "fallback_text": """Table-Heavy Sample

Method                 Strength                       Weakness
Rereading              Fast to start                  Weak retrieval practice
Flashcards             Strong recall loop             Can create backlog pressure
Source-grounded Q&A    Explains with citations        Needs reliable evidence links

The table shows why Carrel combines reading, grounded answers, anchors, and spaced review. Each method solves one part of the learning loop but becomes stronger when connected to the others.
""",
    },
    {
        "filename": "carrel-demo-ocr-boundary.pdf",
        "subject_name": "Demo Sources",
        "title": "OCR Boundary Sample",
        "fallback_text": """OCR Boundary Sample

This sample stands in for a scanned document. A real scanned PDF may need OCR before Carrel can extract reliable chunks. When extraction quality is low, the app should say so directly and keep the source visible in the Jobs Tray rather than failing silently.

Trust comes from clear status: importing, extracting text, indexing, ready, partial, or failed.
""",
    },
]


def _sample_path(sample: Dict[str, Any]) -> Path:
    return DEMO_LIBRARY_DIR / str(sample["filename"])


def _copy_sample_to_uploads(path: Path) -> str:
    db.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    storage_name = f"demo-{uuid.uuid4()}{path.suffix}"
    shutil.copyfile(path, db.UPLOAD_DIR / storage_name)
    return storage_name


def seed_demo_library(conn: sqlite3.Connection, *, force: bool = False) -> Dict[str, Any]:
    existing = int(conn.execute("SELECT COUNT(*) AS total FROM documents").fetchone()["total"] or 0)
    already_seeded = conn.execute(
        "SELECT value FROM onboarding_state WHERE key = 'demo_library_seeded'"
    ).fetchone()
    if existing and not force:
        return {"seeded": False, "documents": [], "skipped_reason": "library_not_empty"}
    if already_seeded and not force:
        return {"seeded": False, "documents": [], "skipped_reason": "already_seeded"}

    documents: List[Dict[str, Any]] = []
    for sample in SAMPLES:
        path = _sample_path(sample)
        if not path.exists():
            raise FileNotFoundError(f"Bundled demo source is missing: {path}")

        asset = extraction_pipeline.extract_asset(path)
        storage_name = _copy_sample_to_uploads(path)
        result = ingest_document_record(
            conn=conn,
            filename=sample["filename"],
            file_type=asset.detected_type,
            extracted_text=str(asset.cleaned_text or asset.raw_text or sample["fallback_text"]),
            page_count=asset.quality.metrics.get("page_count") or 1,
            storage_name=storage_name,
            subject_name=sample["subject_name"],
            asset=asset,
        )
        documents.append(result)

    conn.execute(
        """
        INSERT INTO onboarding_state (key, value, updated_at)
        VALUES ('demo_library_seeded', '1', CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = '1', updated_at = CURRENT_TIMESTAMP
        """
    )
    conn.commit()
    return {"seeded": True, "documents": documents, "skipped_reason": None}
