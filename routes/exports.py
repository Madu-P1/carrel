"""Export API routes — download artifacts and notes as files."""
from fastapi import Query
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional

from db import get_db
from services import export_service


def register_export_routes(app) -> None:

    @app.post("/api/exports/artifact/{artifact_id}")
    def export_artifact(artifact_id: str, export_format: str = Query("markdown")):
        with get_db() as conn:
            result = export_service.export_artifact(conn, artifact_id, export_format=export_format)
            return result

    @app.get("/api/exports/artifact/{artifact_id}/download")
    def download_artifact_export(artifact_id: str, export_format: str = Query("markdown")):
        with get_db() as conn:
            result = export_service.export_artifact(conn, artifact_id, export_format=export_format)
            filepath = Path(result["path"])
            media_types = {
                "markdown": "text/markdown",
                "md": "text/markdown",
                "text": "text/plain",
                "txt": "text/plain",
                "json": "application/json",
            }
            return FileResponse(
                filepath,
                filename=result["filename"],
                media_type=media_types.get(export_format, "application/octet-stream"),
            )

    @app.get("/api/exports")
    def list_exports(artifact_id: Optional[str] = Query(None), limit: int = Query(20)):
        with get_db() as conn:
            return {"exports": export_service.list_exports(conn, artifact_id=artifact_id, limit=limit)}

    @app.post("/api/exports/notes")
    def export_notes(doc_id: Optional[str] = Query(None), export_format: str = Query("markdown")):
        with get_db() as conn:
            return export_service.export_notes_bundle(conn, doc_id=doc_id, export_format=export_format)
