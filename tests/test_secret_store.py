from __future__ import annotations

import unittest

from services.secret_store import (
    MemorySecretStore,
    delete_secret,
    get_secret,
    set_default_secret_store_for_testing,
    store_secret,
)


class SecretStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        # Force the process-memory store so the suite never touches the
        # real Keychain — works on CI / non-Darwin identically.
        set_default_secret_store_for_testing(MemorySecretStore())

    def tearDown(self) -> None:
        set_default_secret_store_for_testing(None)

    def test_store_get_delete_round_trip(self) -> None:
        store_secret("carrel.ai.anthropic-key", "sk-ant-test-123")
        self.assertEqual("sk-ant-test-123", get_secret("carrel.ai.anthropic-key"))

        delete_secret("carrel.ai.anthropic-key")
        self.assertIsNone(get_secret("carrel.ai.anthropic-key"))

    def test_get_unknown_name_returns_none(self) -> None:
        self.assertIsNone(get_secret("carrel.ai.does-not-exist"))

    def test_delete_unknown_name_is_noop(self) -> None:
        # No exception, no side effect.
        delete_secret("carrel.ai.does-not-exist")
        self.assertIsNone(get_secret("carrel.ai.does-not-exist"))

    def test_store_overwrites_existing_value(self) -> None:
        store_secret("carrel.ai.anthropic-key", "sk-ant-old")
        store_secret("carrel.ai.anthropic-key", "sk-ant-new")
        self.assertEqual("sk-ant-new", get_secret("carrel.ai.anthropic-key"))

    def test_secrets_are_isolated_by_name(self) -> None:
        store_secret("name.a", "value-a")
        store_secret("name.b", "value-b")
        self.assertEqual("value-a", get_secret("name.a"))
        self.assertEqual("value-b", get_secret("name.b"))


if __name__ == "__main__":
    unittest.main()
