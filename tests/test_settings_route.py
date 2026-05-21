from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import main
from routes.settings import ANTHROPIC_KEY_SECRET_NAME
from services.local_api_security import HEADER_NAME, get_local_api_token
from services.secret_store import (
    MemorySecretStore,
    get_secret,
    set_default_secret_store_for_testing,
)


class SettingsRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        # Memory secret store: never touches the real Keychain.
        set_default_secret_store_for_testing(MemorySecretStore())

        # The route legitimately mutates os.environ (hot-swap). Snapshot
        # the provider/key env vars so a test never leaks into the next.
        self._env_snapshot = {
            name: os.environ.get(name) for name in ("CARREL_AI_PROVIDER", "ANTHROPIC_API_KEY")
        }

        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.original_base_dir = main.BASE_DIR
        self.original_data_dir = main.DATA_DIR
        self.original_upload_dir = main.UPLOAD_DIR
        self.original_db_path = main.DB_PATH
        self.original_schema_path = main.SCHEMA_PATH

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        set_default_secret_store_for_testing(None)
        for name, value in self._env_snapshot.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def test_get_returns_documented_shape(self) -> None:
        response = self.client.get("/api/settings/ai")
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertIn("provider", body)
        self.assertIn("key_set", body)
        self.assertIn("availability", body)
        # Default provider with nothing persisted is "auto".
        self.assertEqual("auto", body["provider"])
        self.assertFalse(body["key_set"])
        # availability is keyed by provider kind, each a serialized dict.
        for kind in ("claude", "ollama", "afm"):
            self.assertIn(kind, body["availability"])
            verdict = body["availability"][kind]
            self.assertEqual(kind, verdict["kind"])
            self.assertIn("configured", verdict)
            self.assertIn("available", verdict)
            self.assertIn("detail", verdict)
            self.assertIn("error_code", verdict)

    def test_post_provider_persists_and_get_reflects_it(self) -> None:
        posted = self.client.post("/api/settings/ai", json={"provider": "ollama"})
        self.assertEqual(200, posted.status_code, posted.text)
        self.assertEqual("ollama", posted.json()["provider"])

        fetched = self.client.get("/api/settings/ai")
        self.assertEqual("ollama", fetched.json()["provider"])

    def test_post_invalid_provider_returns_422(self) -> None:
        response = self.client.post("/api/settings/ai", json={"provider": "not-a-provider"})
        self.assertEqual(422, response.status_code, response.text)

    def test_set_and_clear_key_flips_key_set(self) -> None:
        # Mock validation so the suite never hits the Anthropic network.
        with mock.patch(
            "routes.settings.validate_anthropic_key",
            return_value=(True, "ok"),
        ):
            posted = self.client.post(
                "/api/settings/ai", json={"anthropic_key": "sk-ant-secret-xyz"}
            )
        self.assertEqual(200, posted.status_code, posted.text)
        body = posted.json()
        self.assertTrue(body["key_set"])
        self.assertTrue(body["key_valid"])
        # The key landed in the secret store, never in the response.
        self.assertEqual("sk-ant-secret-xyz", get_secret(ANTHROPIC_KEY_SECRET_NAME))

        # Empty string is the explicit "clear my key" path.
        cleared = self.client.post("/api/settings/ai", json={"anthropic_key": ""})
        self.assertEqual(200, cleared.status_code, cleared.text)
        self.assertFalse(cleared.json()["key_set"])
        self.assertIsNone(get_secret(ANTHROPIC_KEY_SECRET_NAME))

    def test_key_value_never_appears_in_any_response(self) -> None:
        secret = "sk-ant-super-secret-never-echo"
        with mock.patch(
            "routes.settings.validate_anthropic_key",
            return_value=(True, "ok"),
        ):
            posted = self.client.post("/api/settings/ai", json={"anthropic_key": secret})
        self.assertNotIn(secret, posted.text)

        fetched = self.client.get("/api/settings/ai")
        self.assertNotIn(secret, fetched.text)

    def test_offline_key_validation_still_saves_key(self) -> None:
        # validate_anthropic_key raising ConnectionError == offline:
        # key_valid is None ("not checked") but the key still persists.
        with mock.patch(
            "routes.settings.validate_anthropic_key",
            side_effect=ConnectionError("offline"),
        ):
            posted = self.client.post("/api/settings/ai", json={"anthropic_key": "sk-ant-offline"})
        self.assertEqual(200, posted.status_code, posted.text)
        body = posted.json()
        self.assertTrue(body["key_set"])
        self.assertIsNone(body["key_valid"])
        self.assertEqual("sk-ant-offline", get_secret(ANTHROPIC_KEY_SECRET_NAME))

    def test_rejected_key_reports_invalid_but_still_saves(self) -> None:
        with mock.patch(
            "routes.settings.validate_anthropic_key",
            return_value=(False, "rejected"),
        ):
            posted = self.client.post("/api/settings/ai", json={"anthropic_key": "sk-ant-bad"})
        self.assertEqual(200, posted.status_code, posted.text)
        body = posted.json()
        self.assertTrue(body["key_set"])
        self.assertFalse(body["key_valid"])


if __name__ == "__main__":
    unittest.main()
