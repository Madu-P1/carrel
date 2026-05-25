"""Tests for the worktree-isolation PreToolUse hook.

Covers:
- Allows writes inside the current worktree.
- Blocks writes to the main repo from a worktree CLAUDE_PROJECT_DIR.
- Blocks writes to sibling worktrees.
- Allows writes to ~/.agent-cockpit, ~/.gstack, ~/.claude, /tmp.
- No-ops when CARREL_AUTONOMOUS is unset.
- Resolves relative paths against CLAUDE_PROJECT_DIR.
- Expands ~ in file_path.

The hook itself shells out to stdin JSON; we drive it via subprocess so
the env-gate + main() flow are exercised end-to-end. The pure `evaluate`
function is also imported for direct unit coverage.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK_PATH = Path("/Users/madu/Desktop/Codex/.claude/hooks/worktree-isolation.py")


def _import_hook():
    spec = importlib.util.spec_from_file_location("worktree_isolation", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_hook(tool_name: str, tool_input: dict, env: dict) -> tuple[int, str, str]:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    full_env = {**os.environ, **env}
    proc = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=10,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


class WorktreeIsolationEvaluateTests(unittest.TestCase):
    """Direct tests of the pure `evaluate` function."""

    def setUp(self) -> None:
        self.hook = _import_hook()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Simulate a worktree root in a real tmp directory so resolve() works.
        self.worktree = Path(self.tmp.name) / "worktree-a"
        self.worktree.mkdir()
        self.sibling = Path(self.tmp.name) / "worktree-b"
        self.sibling.mkdir()
        self.main_repo = Path(self.tmp.name) / "main"
        self.main_repo.mkdir()

    def test_allows_inside_worktree_relative(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "Write", {"file_path": "services/foo.py"}, self.worktree
        )
        self.assertTrue(allowed, reason)

    def test_allows_inside_worktree_absolute(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "Write",
            {"file_path": str(self.worktree / "services" / "foo.py")},
            self.worktree,
        )
        self.assertTrue(allowed, reason)

    def test_blocks_sibling_worktree(self) -> None:
        allowed, reason, _orig, _res = self.hook.evaluate(
            "Write",
            {"file_path": str(self.sibling / "docs" / "leak.md")},
            self.worktree,
        )
        self.assertFalse(allowed)
        self.assertIn("WORKTREE ISOLATION", reason)

    def test_blocks_path_outside_worktree(self) -> None:
        allowed, reason, _orig, _res = self.hook.evaluate(
            "Write",
            {"file_path": str(self.main_repo / "services" / "leak.py")},
            self.worktree,
        )
        self.assertFalse(allowed)
        self.assertIn("WORKTREE ISOLATION", reason)

    def test_allows_tmp(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "Write", {"file_path": "/tmp/scratch.txt"}, self.worktree
        )
        self.assertTrue(allowed, reason)

    def test_allows_home_agent_cockpit(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "Write",
            {"file_path": "~/.agent-cockpit/state/foo.json"},
            self.worktree,
        )
        self.assertTrue(allowed, reason)

    def test_allows_home_gstack(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "Edit", {"file_path": "~/.gstack/learnings.jsonl"}, self.worktree
        )
        self.assertTrue(allowed, reason)

    def test_allows_home_claude(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "Write", {"file_path": "~/.claude/projects/foo.md"}, self.worktree
        )
        self.assertTrue(allowed, reason)

    def test_relative_path_resolved_against_project_dir(self) -> None:
        # Relative path with no traversal stays in worktree.
        allowed, _r, _o, resolved = self.hook.evaluate(
            "Write", {"file_path": "tests/new_test.py"}, self.worktree
        )
        self.assertTrue(allowed)
        self.assertTrue(resolved == "" or resolved.startswith(str(self.worktree)))

    def test_relative_traversal_escapes_blocked(self) -> None:
        # ../leak.py from a worktree root resolves outside.
        allowed, reason, *_ = self.hook.evaluate(
            "Write", {"file_path": "../leak.py"}, self.worktree
        )
        self.assertFalse(allowed)
        self.assertIn("WORKTREE ISOLATION", reason)

    def test_multiedit_uses_file_path(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "MultiEdit",
            {
                "file_path": str(self.main_repo / "services" / "leak.py"),
                "edits": [{"old_string": "a", "new_string": "b"}],
            },
            self.worktree,
        )
        self.assertFalse(allowed)
        self.assertIn("WORKTREE ISOLATION", reason)

    def test_empty_file_path_passes_through(self) -> None:
        allowed, *_ = self.hook.evaluate("Write", {}, self.worktree)
        self.assertTrue(allowed)


class WorktreeIsolationCarrelLayoutTests(unittest.TestCase):
    """Tests using the real Carrel main/worktree paths to confirm leak
    classification messages. These use string paths, not on-disk dirs,
    because Path.resolve(strict=False) is what we rely on."""

    def setUp(self) -> None:
        self.hook = _import_hook()
        self.worktree = Path("/Users/madu/Desktop/Codex/.claude/worktrees/fleet-1")
        self.sibling = Path("/Users/madu/Desktop/Codex/.claude/worktrees/fleet-2")
        self.main_repo = Path("/Users/madu/Desktop/Codex")

    def test_blocks_main_repo_write_from_worktree(self) -> None:
        allowed, reason, _o, resolved = self.hook.evaluate(
            "Write",
            {"file_path": str(self.main_repo / "services" / "retrieval" / "quote_heuristics.py")},
            self.worktree,
        )
        self.assertFalse(allowed)
        self.assertIn("main-repo leak", reason)
        self.assertIn(resolved, reason)

    def test_blocks_sibling_worktree_write(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "Write",
            {"file_path": str(self.sibling / "docs" / "decisions" / "leak.md")},
            self.worktree,
        )
        self.assertFalse(allowed)
        self.assertIn("sibling worktree leak", reason)

    def test_allows_inside_own_worktree(self) -> None:
        allowed, reason, *_ = self.hook.evaluate(
            "Write",
            {"file_path": str(self.worktree / "docs" / "decisions" / "0007-foo.md")},
            self.worktree,
        )
        self.assertTrue(allowed, reason)


class WorktreeIsolationSubprocessTests(unittest.TestCase):
    """End-to-end via subprocess so the env-gate + stdin path are covered."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.worktree = Path(self.tmp.name) / "worktree-a"
        self.worktree.mkdir()
        self.main_repo = Path(self.tmp.name) / "main"
        self.main_repo.mkdir()

    def test_no_op_when_carrel_autonomous_unset(self) -> None:
        env = {"CLAUDE_PROJECT_DIR": str(self.worktree)}
        env.pop("CARREL_AUTONOMOUS", None)
        # Even a clearly-leaking write must pass through silently.
        rc, stdout, _ = _run_hook(
            "Write",
            {"file_path": str(self.main_repo / "leak.py"), "content": "x"},
            {**env, "CARREL_AUTONOMOUS": ""},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "")

    def test_blocks_main_repo_when_armed(self) -> None:
        env = {
            "CLAUDE_PROJECT_DIR": str(self.worktree),
            "CARREL_AUTONOMOUS": "true",
        }
        rc, stdout, _ = _run_hook(
            "Write",
            {"file_path": str(self.main_repo / "leak.py"), "content": "x"},
            env,
        )
        self.assertEqual(rc, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "WORKTREE ISOLATION",
            payload["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_allows_inside_worktree_when_armed(self) -> None:
        env = {
            "CLAUDE_PROJECT_DIR": str(self.worktree),
            "CARREL_AUTONOMOUS": "true",
        }
        rc, stdout, _ = _run_hook(
            "Write",
            {
                "file_path": str(self.worktree / "ok.py"),
                "content": "x",
            },
            env,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "")

    def test_block_writes_to_log(self) -> None:
        env = {
            "CLAUDE_PROJECT_DIR": str(self.worktree),
            "CARREL_AUTONOMOUS": "true",
        }
        _run_hook(
            "Write",
            {"file_path": str(self.main_repo / "leak.py"), "content": "x"},
            env,
        )
        log = self.worktree / ".claude" / "logs" / "worktree-isolation-blocks.jsonl"
        self.assertTrue(log.exists(), "block log was not created")
        line = log.read_text().splitlines()[-1]
        entry = json.loads(line)
        self.assertEqual(entry["tool_name"], "Write")
        self.assertIn("leak.py", entry["original_file_path"])

    def test_non_matching_tool_passes_through(self) -> None:
        # The settings.json matcher restricts to Write|Edit|MultiEdit, but
        # the hook itself also guards on tool_name. A Bash call dispatched
        # here must no-op.
        env = {
            "CLAUDE_PROJECT_DIR": str(self.worktree),
            "CARREL_AUTONOMOUS": "true",
        }
        rc, stdout, _ = _run_hook("Bash", {"command": "rm -rf /"}, env)
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
