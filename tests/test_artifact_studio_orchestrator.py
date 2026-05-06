"""Tests for `services.artifact_studio._orchestrator`.

This is the FIRST set of orchestrator tests for code that has been in
production for months — the autoplan eng review flagged the zero
existing coverage as a CRITICAL gap. We pin:

  * Unknown artifact_kind logs a warning + echoes `requested_kind`
  * `custom_prompt` length cap is enforced at the route boundary
  * The route surface (`/api/studio/generate`, `/api/studio/artifacts`,
    `/api/studio/artifacts/{id}`) survives the package split

DB-fixture tests use the real schema via `main.initialize_database`
because the orchestrator hits 7+ tables (documents, concepts, chunks,
artifacts, evidence_references, study_events, sessions). A minimal
in-memory schema would be longer than the test.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from services.local_api_security import HEADER_NAME, get_local_api_token


class OrchestratorRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self._orig = (
            main.BASE_DIR, main.DATA_DIR, main.UPLOAD_DIR,
            main.DB_PATH, main.SCHEMA_PATH,
        )
        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self._orig[4]
        main.initialize_database()
        self.client = TestClient(
            main.app,
            headers={HEADER_NAME: get_local_api_token()},
        )

    def tearDown(self) -> None:
        (
            main.BASE_DIR, main.DATA_DIR, main.UPLOAD_DIR,
            main.DB_PATH, main.SCHEMA_PATH,
        ) = self._orig
        self.temp_dir.cleanup()

    def test_route_surface_survives_package_split(self) -> None:
        # The package split changed `services/artifact_studio.py` from a
        # flat module to a package directory. The route still imports
        # `from services import artifact_studio as studio_service` —
        # this test pins that the contract still resolves end-to-end.
        response = self.client.get("/api/studio/artifacts")
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertIn("artifacts", body)
        self.assertEqual([], body["artifacts"])  # empty DB → empty list

    def test_get_unknown_artifact_returns_404(self) -> None:
        response = self.client.get("/api/studio/artifacts/no-such-id")
        self.assertEqual(404, response.status_code)

    def test_generate_with_no_sources_uses_empty_concepts(self) -> None:
        # The orchestrator must tolerate empty scope — it falls back to
        # generating from whatever concepts exist (zero, in this case).
        # Should produce a study_guide artifact, not crash.
        response = self.client.post(
            "/api/studio/generate",
            json={"artifact_kind": "study_guide"},
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        artifact = body.get("artifact") or body
        self.assertEqual("study_guide", artifact["artifact_kind"])
        self.assertEqual("study_guide", artifact["requested_kind"])
        self.assertEqual(0, artifact["concept_count"])

    def test_unknown_artifact_kind_silently_falls_back_with_audit_field(self) -> None:
        # Backwards-compat: silent fallback persists. But the response
        # now telegraphs the rewrite via `requested_kind`, which the
        # frontend can use to surface a "your kind was substituted" toast.
        response = self.client.post(
            "/api/studio/generate",
            json={"artifact_kind": "totally_made_up"},
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        artifact = body.get("artifact") or body
        self.assertEqual("study_guide", artifact["artifact_kind"])
        self.assertEqual("totally_made_up", artifact["requested_kind"])

    def test_custom_prompt_over_4000_chars_rejected_at_route(self) -> None:
        # Pydantic max_length on StudioGenerateRequest.custom_prompt
        # should reject the request before it reaches the orchestrator.
        # 4001 chars triggers the 422.
        response = self.client.post(
            "/api/studio/generate",
            json={
                "artifact_kind": "study_guide",
                "custom_prompt": "x" * 4001,
            },
        )
        self.assertEqual(422, response.status_code)

    def test_custom_prompt_at_4000_chars_accepted(self) -> None:
        # Boundary: exactly 4000 chars must succeed.
        response = self.client.post(
            "/api/studio/generate",
            json={
                "artifact_kind": "study_guide",
                "custom_prompt": "x" * 4000,
            },
        )
        self.assertEqual(200, response.status_code, response.text)

    def test_list_artifacts_returns_preview_not_full_markdown(self) -> None:
        # First create an artifact so the list isn't empty.
        self.client.post("/api/studio/generate", json={"artifact_kind": "study_guide"})
        response = self.client.get("/api/studio/artifacts")
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(1, len(body["artifacts"]))
        item = body["artifacts"][0]
        # The list endpoint deliberately strips `output_markdown` and
        # exposes `preview` instead — protects the response size.
        self.assertIn("preview", item)
        self.assertNotIn("output_markdown", item)


if __name__ == "__main__":
    unittest.main()
