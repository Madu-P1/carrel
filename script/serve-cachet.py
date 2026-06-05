#!/usr/bin/env python3
"""Run standalone Cachet in the user's own browser, cross-platform (Windows + Mac
+ Linux). No bash, no native shell: start the CACHET_ONLY backend, which serves the
built frontend over loopback with the local-API token injected, then open the
default browser at it.

This is the validation-phase delivery (see
docs/plans/cachet-localhost-browser-2026-06-05.md). Prereqs: a Python with the repo
deps (run with the project's venv python) and a built frontend
(`pnpm --dir frontend build:cachet`).

    python script/serve-cachet.py            # pick a free port, open the browser
    CACHET_PORT=8123 python script/serve-cachet.py   # prefer a specific port

The backend owns the token (random per run) and injects it into the served HTML,
so this launcher never has to handle the secret. Ctrl+C stops the backend.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_free_port(preferred: int) -> int:
    """Use `preferred` if free, else let the OS assign one. Same-origin serving
    makes the actual port irrelevant to the frontend, so any free port works."""
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", candidate))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free loopback port available")


def wait_for_health(port: int, proc: subprocess.Popen, timeout_s: int = 40) -> bool:
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        # Fail fast: if the backend exited (import error, bad config), don't make
        # the user wait out the full timeout for a health check that can't pass.
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 (loopback)
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def check_backend_deps() -> None:
    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
        import uvicorn  # noqa: F401
    except Exception:
        sys.stderr.write(
            f"serve-cachet: '{sys.executable}' is missing backend deps "
            "(fastapi / httpx / uvicorn).\n"
            "Run it with the project's venv python, e.g.:\n"
            "  ./.venv/bin/python script/serve-cachet.py   (macOS/Linux)\n"
            "  .venv\\Scripts\\python script\\serve-cachet.py   (Windows)\n"
        )
        raise SystemExit(1)


def main() -> int:
    check_backend_deps()
    dist = ROOT / "frontend" / "dist-cachet" / "cachet.html"
    if not dist.is_file():
        sys.stderr.write(
            "serve-cachet: no built frontend at frontend/dist-cachet/.\n"
            "Build it first:  pnpm --dir frontend build:cachet\n"
        )
        return 1

    port = find_free_port(int(os.getenv("CACHET_PORT", "8000")))
    env = {**os.environ, "CACHET_ONLY": "1"}
    # Do NOT set CARREL_API_OPEN_MODE: the token gate stays on. The backend
    # generates its own token and injects it into the served HTML.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--app-dir",
            str(ROOT),
        ],
        env=env,
    )
    url = f"http://127.0.0.1:{port}/"
    try:
        if wait_for_health(port, proc):
            # Open the browser on a short delay so the served page is ready.
            threading.Timer(0.3, lambda: webbrowser.open(url)).start()
            print(f"Cachet is running at {url}")
            print("Open that URL in your browser if it did not open automatically.")
            print("Press Ctrl+C to stop.")
        else:
            sys.stderr.write("serve-cachet: backend did not become healthy in time.\n")
            proc.terminate()
            return 1
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
