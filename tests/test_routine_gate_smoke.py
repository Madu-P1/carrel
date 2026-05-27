"""Pre-flight gate-machinery smoke test.

Asserts the auditor sub-routine produces a verdict file on a benign
synthetic pending action within ``TIMEOUT_S``. Runs at watchdog startup
via ``script/autonomous-watchdog.sh``; the watchdog refuses to launch on
failure. Lives under ``tests/`` but is intentionally NOT in the
canonical verify chain (the chain explicitly lists modules under
``python -m unittest`` and uses pytest only for opt-in suites). The
watchdog invokes it directly: ``python -m pytest
tests/test_routine_gate_smoke.py``.

Override the smoke test in the watchdog with ``CARREL_SKIP_SMOKE=1``.
Override the underlying ``claude`` invocation here with
``CARREL_SMOKE_CLAUDE_BIN=/path/to/claude`` (useful when ``claude`` is
not on PATH or when pointing at a specific binary in CI).

T68 Phase 4 - see ``docs/plans/routine-hardening-2026-05-27.md``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SYNTHETIC_HASH = "smoke-test-synthetic-action"
TIMEOUT_S = 60
REPO_ROOT = Path(__file__).resolve().parent.parent


def _claude_binary() -> str | None:
    override = os.environ.get("CARREL_SMOKE_CLAUDE_BIN")
    if override:
        return override if Path(override).exists() else None
    return shutil.which("claude")


def _auditor_agent_present() -> bool:
    return (REPO_ROOT / ".claude" / "agents" / "independent-auditor.md").exists()


def _clean_verdict_files() -> tuple[Path, Path, Path]:
    pending = REPO_ROOT / ".claude/logs/audits/pending" / f"{SYNTHETIC_HASH}.json"
    approved = REPO_ROOT / ".claude/logs/audits/approved" / f"{SYNTHETIC_HASH}.json"
    rejected = REPO_ROOT / ".claude/logs/audits/rejected" / f"{SYNTHETIC_HASH}.json"
    for p in (pending, approved, rejected):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.unlink(missing_ok=True)
    return pending, approved, rejected


def test_auditor_writes_verdict_on_synthetic_action() -> None:
    if not _auditor_agent_present():
        pytest.fail(
            "independent-auditor agent definition missing at "
            ".claude/agents/independent-auditor.md - gate machinery is broken"
        )

    claude_bin = _claude_binary()
    if not claude_bin:
        pytest.skip(
            "claude CLI not on PATH and CARREL_SMOKE_CLAUDE_BIN unset; "
            "skipping gate smoke (watchdog launcher should treat this as a pass)"
        )

    pending, approved, rejected = _clean_verdict_files()

    pending.write_text(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "hash": SYNTHETIC_HASH,
                "kind": "smoke-test",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "echo smoke-test no-op",
                    "description": "synthetic gate-smoke probe",
                },
            }
        )
    )

    prompt = (
        f"Audit pending action {SYNTHETIC_HASH}. Read "
        f".claude/logs/audits/pending/{SYNTHETIC_HASH}.json and write a verdict "
        f"file to .claude/logs/audits/approved/{SYNTHETIC_HASH}.json or "
        f".claude/logs/audits/rejected/{SYNTHETIC_HASH}.json per "
        ".claude/agents/independent-auditor.md. The pending action is a benign "
        "no-op echo command; APPROVED is the expected verdict."
    )
    cmd = [
        claude_bin,
        "--print",
        "--permission-mode",
        "default",
        "--model",
        "haiku",
        prompt,
    ]
    try:
        subprocess.run(
            cmd,
            timeout=TIMEOUT_S,
            check=False,
            capture_output=True,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"auditor spawn exceeded {TIMEOUT_S}s on synthetic action; "
            "gate machinery is broken - refuse to launch the autonomous loop"
        ) from exc

    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        if approved.exists() or rejected.exists():
            break
        time.sleep(1)

    assert approved.exists() or rejected.exists(), (
        f"auditor did not write a verdict file within {TIMEOUT_S}s on the synthetic "
        f"action; gate machinery is broken - refuse to launch the autonomous loop. "
        f"Inspect {pending} and the auditor agent definition."
    )
