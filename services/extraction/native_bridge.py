from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .utils import NATIVE_BRIDGE_CANDIDATES


@dataclass
class BridgeFailure:
    """Returned when the bridge runs and exits non-zero. The stderr message
    is surfaced verbatim so parsers can render a precise user-facing error
    (e.g. 'Speech Recognition permission is denied — grant it in System
    Settings then re-upload')."""

    exit_code: int
    message: str


class NativeBridge:
    @staticmethod
    def available_binary() -> Optional[Path]:
        for candidate in NATIVE_BRIDGE_CANDIDATES:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    @classmethod
    def run(cls, path: Path) -> Optional[Dict[str, Any]]:
        """Backward-compatible runner. Returns parsed JSON on success,
        None for the historical 'binary missing or generic failure' path.
        For richer error reporting use `run_or_failure()`."""
        result = cls.run_or_failure(path)
        if isinstance(result, dict):
            return result
        return None

    @classmethod
    def run_or_failure(cls, path: Path) -> Optional[Any]:
        """Returns one of:
          - dict: parsed JSON payload on success.
          - BridgeFailure: bridge ran and exited non-zero; stderr surfaced.
          - None: bridge binary not present or unparseable output.
        """
        binary = cls.available_binary()
        if binary is None:
            return None
        try:
            completed = subprocess.run(
                [str(binary), str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=720,
            )
        except subprocess.TimeoutExpired:
            return BridgeFailure(exit_code=124, message="The macOS bridge timed out.")
        except Exception:
            return None
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            return BridgeFailure(
                exit_code=completed.returncode,
                message=stderr or f"Bridge exited with code {completed.returncode}.",
            )
        stdout = (completed.stdout or "").strip()
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return None
