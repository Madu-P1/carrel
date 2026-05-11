"""Shared discovery for Carrel's Swift sidecar binaries.

Two bridges live in macos-app/:

* `EinsteinIngestionBridge` (PDF + Vision OCR), called by
  `services/extraction/native_bridge.py`.
* `EinsteinAFMBridge` (Apple Foundation Models), called by
  `ai/afm_client.py`.

Both are produced by `swift build` and copied into `dist/` (or the
.app bundle's `Contents/MacOS/` in production builds). This module
centralizes the candidate-path walk so neither caller hardcodes its
own list.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root is two levels up from this file: ai/native_bridge_paths.py.
ROOT_DIR = Path(__file__).resolve().parents[1]


def _candidates_for(name: str) -> list[Path]:
    """Standard search order for a Swift sidecar binary by name."""
    candidates: list[Path] = []

    # Production layout: when launched from a packaged .app, the Swift
    # shell sets CARREL_BUNDLE_MACOS to the bundle's Contents/MacOS dir
    # so Python finds the bridge that was copied beside the main binary.
    bundle_macos = os.environ.get("CARREL_BUNDLE_MACOS")
    if bundle_macos:
        candidates.append(Path(bundle_macos) / name)

    # Dev layouts:
    candidates.extend(
        [
            ROOT_DIR / "dist" / name,
            ROOT_DIR / "macos-app" / ".build" / "arm64-apple-macosx" / "debug" / name,
            ROOT_DIR / "macos-app" / ".build" / "debug" / name,
            ROOT_DIR / "macos-app" / ".build" / "arm64-apple-macosx" / "release" / name,
            ROOT_DIR / "macos-app" / ".build" / "release" / name,
        ]
    )
    return candidates


INGESTION_BRIDGE_CANDIDATES: list[Path] = _candidates_for("EinsteinIngestionBridge")
AFM_BRIDGE_CANDIDATES: list[Path] = _candidates_for("EinsteinAFMBridge")


def find_binary(candidates: list[Path]) -> Path | None:
    """Return the first existing executable binary from the candidate list."""
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None
