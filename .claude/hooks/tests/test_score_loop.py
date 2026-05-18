"""Branch coverage for .claude/hooks/score-loop.py.

Pins the three exit paths so a regression in the Stop-event envelope is
caught: HALT short-circuit, per-session nudge cap, and the normal block
decision. Invokes the hook as a subprocess so the test exercises the real
stdin/stdout JSON contract Claude Code uses.
"""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "score-loop.py"


def _run(stdin_obj, project_dir):
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(stdin_obj),
        capture_output=True,
        text=True,
        env={
            "CARREL_AUTONOMOUS": "true",
            "CLAUDE_PROJECT_DIR": str(project_dir),
            "PATH": "/usr/bin:/bin",
        },
        timeout=10,
        check=False,
    )
    return proc.returncode, proc.stdout


def test_halt_file_emits_system_message_and_exits(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "HALT").write_text("")

    rc, out = _run({"hook_event_name": "Stop", "session_id": "halt"}, tmp_path)

    assert rc == 0
    payload = json.loads(out)
    assert "systemMessage" in payload
    assert "HALT" in payload["systemMessage"]
    assert "decision" not in payload


def test_cap_hit_emits_warning_and_exits(tmp_path):
    score_dir = tmp_path / ".claude" / "logs" / "scores"
    score_dir.mkdir(parents=True)
    (score_dir / "nudge-count-cap.txt").write_text("100")

    rc, out = _run({"hook_event_name": "Stop", "session_id": "cap"}, tmp_path)

    assert rc == 0
    payload = json.loads(out)
    assert "systemMessage" in payload
    assert "cap hit" in payload["systemMessage"].lower()
    assert "decision" not in payload


def test_normal_path_emits_block_decision_with_reason(tmp_path):
    (tmp_path / ".claude").mkdir()

    rc, out = _run({"hook_event_name": "Stop", "session_id": "normal"}, tmp_path)

    assert rc == 0
    payload = json.loads(out)
    assert payload.get("decision") == "block"
    assert "reason" in payload
    assert "quality-rater" in payload["reason"]
