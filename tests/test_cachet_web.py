"""Cachet localhost-browser delivery: serving the built frontend over loopback with
the local-API token injected, plus the DNS-rebinding Host guard.

See docs/plans/cachet-localhost-browser-2026-06-05.md.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.cachet_web import inject_local_api_bootstrap, register_cachet_web_routes
from services.local_api_security import (
    get_local_api_token,
    install_loopback_host_guard,
    is_loopback_host,
)

_HTML = (
    "<!doctype html><html><head>"
    '<meta charset="UTF-8" />'
    '<script type="module" crossorigin src="./assets/cachet.js"></script>'
    '</head><body><div id="root"></div></body></html>'
)


def _write_build(root: Path) -> Path:
    dist = root / "dist-cachet"
    (dist / "assets").mkdir(parents=True)
    (dist / "cachet.html").write_text(_HTML, encoding="utf-8")
    (dist / "assets" / "cachet.js").write_text("export const x = 1;\n", encoding="utf-8")
    return dist


class InjectBootstrapTests(unittest.TestCase):
    def test_injects_token_and_base_after_head(self) -> None:
        out = inject_local_api_bootstrap(_HTML, "tok-123", "")
        self.assertIn('window.__CARREL_LOCAL_API_TOKEN="tok-123"', out)
        self.assertIn('window.__CARREL_API_BASE=""', out)
        # The classic script must precede the deferred module bundle so the
        # globals exist before the app reads them.
        self.assertLess(out.index("__CARREL_LOCAL_API_TOKEN"), out.index("assets/cachet.js"))
        # And it sits inside <head>.
        self.assertLess(out.lower().index("<head>"), out.index("__CARREL_LOCAL_API_TOKEN"))

    def test_escapes_values(self) -> None:
        # json.dumps must escape a quote so injection can't break out of the string.
        out = inject_local_api_bootstrap(_HTML, 'a"b', "")
        self.assertIn(r'window.__CARREL_LOCAL_API_TOKEN="a\"b"', out)

    def test_no_head_falls_back_to_prepend(self) -> None:
        out = inject_local_api_bootstrap("<html><body>x</body></html>", "t", "")
        self.assertTrue(out.startswith("<script>"))


class LoopbackHostTests(unittest.TestCase):
    def test_accepts_loopback_forms(self) -> None:
        for h in (
            "127.0.0.1",
            "127.0.0.1:8000",
            "localhost",
            "localhost:5191",
            "::1",
            "[::1]:8000",
        ):
            self.assertTrue(is_loopback_host(h), h)

    def test_rejects_non_loopback(self) -> None:
        for h in ("evil.com", "evil.com:8000", "cachet.example", "169.254.0.1", "", None):
            self.assertFalse(is_loopback_host(h), h)


class ServeCachetTests(unittest.TestCase):
    def _client(self, dist: Path) -> TestClient:
        app = FastAPI()
        install_loopback_host_guard(app)
        register_cachet_web_routes(app, dist_dir=dist)
        # base_url sets the default Host to loopback so normal calls pass the guard.
        return TestClient(app, base_url="http://127.0.0.1")

    def test_serves_index_with_injected_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = _write_build(Path(tmp))
            resp = self._client(dist).get("/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(get_local_api_token(), resp.text)
            self.assertIn('window.__CARREL_API_BASE=""', resp.text)
            # The token-bearing page must never be cached (stale token after a
            # relaunch would 403 every API call; token must not hit disk cache).
            self.assertEqual(resp.headers.get("cache-control"), "no-store")

    def test_serves_static_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = _write_build(Path(tmp))
            resp = self._client(dist).get("/assets/cachet.js")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("export const x", resp.text)

    def test_rejects_non_loopback_host(self) -> None:
        # DNS-rebinding defense: a foreign Host is refused even on the ungated "/".
        with tempfile.TemporaryDirectory() as tmp:
            dist = _write_build(Path(tmp))
            resp = self._client(dist).get("/", headers={"host": "evil.com"})
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json()["detail"]["code"], "non_loopback_host")

    def test_missing_build_returns_503(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "dist-cachet"  # never created
            resp = self._client(empty).get("/")
            self.assertEqual(resp.status_code, 503)
            self.assertIn("build:cachet", resp.text)


if __name__ == "__main__":
    unittest.main()
