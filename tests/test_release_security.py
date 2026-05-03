from __future__ import annotations

import unittest
from pathlib import Path

from app_logging import redact_context

ROOT = Path(__file__).resolve().parents[1]


class ReleaseSecurityTests(unittest.TestCase):
    def test_native_bootstrap_does_not_emit_href_or_error_filename(self) -> None:
        source = (ROOT / "macos-app/Sources/EinsteinDesktopApp/NativeBridge.swift").read_text(encoding="utf-8")

        self.assertNotIn("href: window.location.href", source)
        self.assertNotIn("filename: event.filename", source)

    def test_webview_logs_do_not_expose_bundled_file_paths(self) -> None:
        source = (ROOT / "macos-app/Sources/EinsteinDesktopApp/WebAppView.swift").read_text(encoding="utf-8")

        self.assertNotIn("htmlURL.path(percentEncoded: false), privacy: .public", source)

    def test_debug_banner_is_release_gated(self) -> None:
        source = (ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")

        self.assertIn("VITE_CARREL_DEBUG_BANNER", source)
        self.assertIn("if (showDebugBanner)", source)

    def test_redacts_urls_and_local_paths_inside_strings(self) -> None:
        payload = redact_context(
            {
                "message": (
                    "Failed at /Users/madu/Library/Application Support/Carrel/private.pdf "
                    "while fetching https://example.com/a/b?token=secret"
                )
            }
        )

        self.assertEqual(
            "Failed at [redacted-path] while fetching https://example.com/***",
            payload["message"],
        )


if __name__ == "__main__":
    unittest.main()
