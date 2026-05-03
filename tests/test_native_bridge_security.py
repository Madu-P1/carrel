from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE_BRIDGE = ROOT / "macos-app/Sources/EinsteinDesktopApp/NativeBridge.swift"


class NativeBridgeSecurityTests(unittest.TestCase):
    def test_storage_bridge_callbacks_have_timeout_cleanup(self) -> None:
        source = NATIVE_BRIDGE.read_text(encoding="utf-8")

        self.assertIn("STORAGE_TIMEOUT_MS", source)
        self.assertIn("window.setTimeout", source)
        self.assertIn("callbacks.delete(id);", source)
        self.assertIn("window.clearTimeout(callback.timeout);", source)
        self.assertIn("Native storage request timed out", source)


if __name__ == "__main__":
    unittest.main()
