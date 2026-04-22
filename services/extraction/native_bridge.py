from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .utils import NATIVE_BRIDGE_CANDIDATES


class NativeBridge:
    @staticmethod
    def available_binary() -> Optional[Path]:
        for candidate in NATIVE_BRIDGE_CANDIDATES:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    @classmethod
    def run(cls, path: Path) -> Optional[Dict[str, Any]]:
        binary = cls.available_binary()
        if binary is None:
            return None
        try:
            completed = subprocess.run(
                [str(binary), str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except Exception:
            return None
        stdout = completed.stdout.strip()
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return None
