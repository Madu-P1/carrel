from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

import main


class ApiSchemaCleanupTests(unittest.TestCase):
    def test_workspace_shell_routes_have_response_schemas(self) -> None:
        schema = TestClient(main.app).get("/openapi.json").json()
        paths = schema["paths"]

        for route, method in [
            ("/api/health", "get"),
            ("/api/local-token", "get"),
            ("/api/sessions/active", "get"),
            ("/api/plan/suggestions/{suggestion_id}/accept", "post"),
            ("/api/plan/suggestions/{suggestion_id}/dismiss", "post"),
            ("/api/plan/suggestions/{suggestion_id}/restore", "post"),
        ]:
            with self.subTest(route=route):
                response = paths[route][method]["responses"]["200"]
                self.assertIn("schema", response["content"]["application/json"])

    def test_plan_suggestion_status_schema_is_tightly_enumerated(self) -> None:
        schema = TestClient(main.app).get("/openapi.json").json()

        status_schema = schema["components"]["schemas"]["StudySuggestionStatusResponse"]["properties"]["status"]
        self.assertEqual(["accepted", "dismissed", "pending"], status_schema["enum"])


if __name__ == "__main__":
    unittest.main()
