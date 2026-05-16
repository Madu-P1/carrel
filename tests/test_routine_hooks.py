"""Regression tests for the Carrel autonomous-build hook scripts.

These tests run the hook scripts via subprocess and assert on their stdout
JSON envelope. They catch the class of bug that occurred in the first
autonomous run, where score-loop.py emitted `hookSpecificOutput` with a
`Stop` event name, which Claude Code's schema does not accept and which
caused every Stop event to log a validation error.

Tests are deliberately small and self-contained: no fixtures, no plugins,
no external dependencies beyond stdlib. They exercise the three score-loop
branches (HALT present, nudge-cap exceeded, normal nudge) and the
outreach/major/destructive/none branches of audit-gate.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def run_hook(
    script_name: str, payload: dict, env_extra: dict | None = None, project_dir: str | None = None
) -> tuple[int, str, str]:
    """Invoke a hook script with a JSON stdin payload, return (rc, stdout, stderr)."""
    env = {
        "CARREL_AUTONOMOUS": "true",
        "CLAUDE_PROJECT_DIR": project_dir or str(REPO_ROOT),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [str(HOOKS_DIR / script_name)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=15,
    )
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


class ScoreLoopEnvelopeTests(unittest.TestCase):
    """The Stop and SubagentStop schema does not accept hookSpecificOutput.

    This regression test pins the score-loop.py output to the supported
    top-level fields only: decision, reason, systemMessage. If a future
    edit re-introduces hookSpecificOutput with hookEventName=Stop, this
    test fires immediately rather than letting the bug ship.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="carrel-test-")
        self.project_dir = Path(self.tmpdir)
        (self.project_dir / ".claude").mkdir()
        (self.project_dir / ".claude" / "hooks").mkdir()
        # Copy the real hook in so it can write to .claude/logs/ inside the temp dir.
        shutil.copy(
            HOOKS_DIR / "score-loop.py", self.project_dir / ".claude" / "hooks" / "score-loop.py"
        )
        (self.project_dir / ".claude" / "hooks" / "score-loop.py").chmod(0o755)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, payload: dict) -> dict:
        proc = subprocess.run(
            [str(self.project_dir / ".claude" / "hooks" / "score-loop.py")],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            env={
                "CARREL_AUTONOMOUS": "true",
                "CLAUDE_PROJECT_DIR": str(self.project_dir),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            },
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
        out = proc.stdout.decode("utf-8").strip()
        return json.loads(out) if out else {}

    def test_normal_nudge_uses_decision_block_not_hookSpecificOutput(self) -> None:
        out = self._run({"hook_event_name": "Stop", "session_id": "test-normal"})
        self.assertNotIn(
            "hookSpecificOutput",
            out,
            "Stop hooks do not accept hookSpecificOutput; use top-level decision/reason.",
        )
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("quality-rater", out.get("reason", "").lower())

    def test_subagentstop_uses_decision_block_not_hookSpecificOutput(self) -> None:
        out = self._run({"hook_event_name": "SubagentStop", "session_id": "test-sub"})
        self.assertNotIn("hookSpecificOutput", out)
        self.assertEqual(out.get("decision"), "block")

    def test_halt_signal_emits_systemMessage_not_hookSpecificOutput(self) -> None:
        (self.project_dir / ".claude" / "HALT").touch()
        out = self._run({"hook_event_name": "Stop", "session_id": "test-halt"})
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("systemMessage", out)
        self.assertIn("HALT", out["systemMessage"])

    def test_nudge_cap_emits_systemMessage_not_hookSpecificOutput(self) -> None:
        # Pre-populate the counter above the cap.
        score_dir = self.project_dir / ".claude" / "logs" / "scores"
        score_dir.mkdir(parents=True)
        (score_dir / "nudge-count-test-cap.txt").write_text("99")
        out = self._run({"hook_event_name": "Stop", "session_id": "test-cap"})
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("systemMessage", out)
        self.assertIn("nudge cap", out["systemMessage"].lower())

    def test_non_stop_event_is_silent(self) -> None:
        proc = subprocess.run(
            [str(self.project_dir / ".claude" / "hooks" / "score-loop.py")],
            input=json.dumps({"hook_event_name": "PreToolUse"}).encode("utf-8"),
            capture_output=True,
            env={
                "CARREL_AUTONOMOUS": "true",
                "CLAUDE_PROJECT_DIR": str(self.project_dir),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            },
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode("utf-8").strip(), "")

    def test_disabled_when_autonomous_unset(self) -> None:
        proc = subprocess.run(
            [str(self.project_dir / ".claude" / "hooks" / "score-loop.py")],
            input=json.dumps({"hook_event_name": "Stop"}).encode("utf-8"),
            capture_output=True,
            env={
                "CLAUDE_PROJECT_DIR": str(self.project_dir),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            },
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode("utf-8").strip(), "")


class AuditGateRoutingTests(unittest.TestCase):
    """The audit-gate must classify Bash commands into the right kind bucket.

    These tests pin the four-way classification (outreach, destructive,
    major, none) so a future regex tweak does not silently re-classify
    a destructive action as major (or vice versa).
    """

    def test_git_commit_classified_major(self) -> None:
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git commit -m wip"},
            },
        )
        self.assertEqual(rc, 0)
        out = json.loads(stdout)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("MAJOR ACTION GATE", reason)

    def test_force_push_classified_destructive(self) -> None:
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
            },
        )
        out = json.loads(stdout)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("DESTRUCTIVE ACTION GATE", reason)

    def test_slack_webhook_classified_outreach(self) -> None:
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "curl -X POST https://hooks.slack.com/services/foo"},
            },
        )
        out = json.loads(stdout)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("OUTREACH SCOPE GATE", reason)

    def test_plain_echo_passes_through(self) -> None:
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "echo hello"},
            },
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "")


class AuditGateHashStabilityTests(unittest.TestCase):
    """The audit-gate hash must be stable across cosmetic Bash `description` changes.

    Three independent auditors flagged this same friction on 2026-05-13:
    each cosmetic relabel of a Bash command (same command, different
    description string) was producing a fresh pending hash, forcing a
    re-audit with no risk-reduction value. The fix drops `description`
    from the hash domain while keeping `command` (and the staged-diff
    hash for git commit) load-bearing.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="carrel-audit-hash-")
        self.project_dir = Path(self.tmpdir)
        (self.project_dir / ".claude" / "logs" / "audits" / "approved").mkdir(parents=True)
        (self.project_dir / ".claude" / "logs" / "audits" / "pending").mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _extract_hash(self, stdout: str) -> str:
        import re as _re

        out = json.loads(stdout)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        m = _re.search(r"hash ([0-9a-f]{16})", reason)
        self.assertIsNotNone(m, f"no hash found in reason: {reason}")
        return m.group(1)

    def test_description_change_does_not_change_hash(self) -> None:
        cmd = "pnpm add some-package"
        _, stdout1, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd, "description": "alpha label"},
            },
            project_dir=str(self.project_dir),
        )
        _, stdout2, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd, "description": "beta wording, totally different"},
            },
            project_dir=str(self.project_dir),
        )
        self.assertEqual(self._extract_hash(stdout1), self._extract_hash(stdout2))
        pending_files = list(
            (self.project_dir / ".claude" / "logs" / "audits" / "pending").iterdir()
        )
        self.assertEqual(
            len(pending_files),
            1,
            "different descriptions should not produce different pending files",
        )

    def test_command_change_does_change_hash(self) -> None:
        _, stdout1, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "pnpm add foo", "description": "same desc"},
            },
            project_dir=str(self.project_dir),
        )
        _, stdout2, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "pnpm add bar", "description": "same desc"},
            },
            project_dir=str(self.project_dir),
        )
        self.assertNotEqual(self._extract_hash(stdout1), self._extract_hash(stdout2))

    def test_approval_with_canonical_hash_allows_relabel(self) -> None:
        # Approval file is keyed by canonical hash (description-free). Re-running
        # with a fresh description should be silently allowed (rc=0, empty stdout).
        cmd = "pnpm add some-package"
        _, stdout1, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd, "description": "first wording"},
            },
            project_dir=str(self.project_dir),
        )
        h = self._extract_hash(stdout1)
        approved = self.project_dir / ".claude" / "logs" / "audits" / "approved" / f"{h}.json"
        approved.write_text(json.dumps({"verdict": "APPROVED", "hash": h}))
        _, stdout2, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd, "description": "second wording, cosmetic relabel"},
            },
            project_dir=str(self.project_dir),
        )
        self.assertEqual(
            stdout2.strip(), "", "approved canonical hash should pass through after a relabel"
        )


class AuditGateHeredocFalsePositiveTests(unittest.TestCase):
    """The audit-gate must not fire on major-action verbs that appear
    only inside heredoc bodies.

    Surfaced by the quality-rater agent on 2026-05-13: writing a JSON
    score file via `cat > .claude/logs/scores/foo.json << EOF` whose
    body contained "git commit" / "migration" / "install" in prose
    blocked the rater's own Bash call. The fix strips heredoc bodies
    before pattern matching so verbs only count when they sit in
    actual command position.
    """

    def test_heredoc_body_git_commit_does_not_fire(self) -> None:
        cmd = (
            "cat > /tmp/score.json << 'EOF'\n"
            '{"score": 100, "note": "considered git commit and migration paths"}\n'
            "EOF"
        )
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
            },
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "", "heredoc-only mention of git commit should not fire")

    def test_heredoc_body_pip_install_does_not_fire(self) -> None:
        cmd = "cat > /tmp/notes.md << 'EOF'\nReminder: run `pip install` before testing.\nEOF"
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
            },
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "", "heredoc-only mention of pip install should not fire")

    def test_real_git_commit_still_fires(self) -> None:
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git commit -m wip"},
            },
        )
        out = json.loads(stdout)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(
            "MAJOR ACTION GATE", reason, "real git commit must still trigger the major gate"
        )

    def test_real_verb_after_heredoc_still_fires(self) -> None:
        cmd = (
            "cat > /tmp/note.txt << 'EOF'\n"
            "draft note that mentions pip install for context\n"
            "EOF\n"
            "git commit -m note"
        )
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
            },
        )
        out = json.loads(stdout)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("MAJOR ACTION GATE", reason, "real verb after a heredoc body must still fire")

    def test_quoted_heredoc_tag_handled(self) -> None:
        # Both <<'EOF' and <<"EOF" forms must strip the body.
        cmd = 'cat > /tmp/x.txt << "EOF"\ngit push --force is something we never do\nEOF'
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
            },
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "", "double-quoted heredoc tag must also be stripped")

    def test_dash_form_heredoc_body_does_not_fire(self) -> None:
        # <<-TAG strips leading tabs from the body and the closing tag
        # (bash semantics); our regex allows leading whitespace before
        # the closing tag via `\s*\1\s*`.
        cmd = "cat > /tmp/x.txt <<-EOF\n\tgit commit body inside dash-form heredoc\n\tEOF"
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
            },
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "", "<<-EOF dash-form must strip body verbs too")

    def test_unclosed_heredoc_falls_through_and_fires(self) -> None:
        # No closing EOF: regex cannot match, body is preserved, verb
        # fires. This is the safe-fail direction (over-fire, never
        # under-fire) — a malformed command in a future routine run
        # cannot smuggle a destructive verb past the gate.
        cmd = "cat > /tmp/x.txt << EOF\ngit commit -m wip\n"
        rc, stdout, _ = run_hook(
            "audit-gate.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
            },
        )
        out = json.loads(stdout)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(
            "MAJOR ACTION GATE",
            reason,
            "unclosed heredoc must fall through and fire (safe direction)",
        )

    def test_gh_pr_create_with_heredoc_git_commit_does_not_fold_staged_diff_hash(
        self,
    ) -> None:
        """Behavioral pin for main()'s staged_diff_hash decision: a
        non-commit action (gh pr create) whose body mentions "git commit"
        inside a heredoc must NOT drag the staged-diff hash into its
        canonical hash. Otherwise the hash would drift across
        staged-tree changes for an action that doesn't involve a commit.

        Run the same command against two temp project_dirs: one with no
        git context (compute_staged_diff_hash returns "no-diff"), one
        with an initialized repo and a staged file (compute_staged_diff_hash
        returns a real 16-char hex of the staged diff). If the strip is
        working, the hashes are identical because staged_diff_hash is
        never folded in. If the strip were reverted, the hashes would
        diverge because the heredoc-body "git commit" substring would
        match the git-commit regex and pull in the staged_diff_hash.
        """
        cmd = (
            "gh pr create --title test --body \"$(cat <<'EOF'\n"
            "Discussion of git commit policy in this PR.\n"
            'EOF\n)"'
        )

        dir_a = tempfile.mkdtemp(prefix="carrel-audit-noinit-")
        dir_b = tempfile.mkdtemp(prefix="carrel-audit-staged-")
        try:
            for d in (dir_a, dir_b):
                (Path(d) / ".claude" / "logs" / "audits" / "approved").mkdir(parents=True)
                (Path(d) / ".claude" / "logs" / "audits" / "pending").mkdir(parents=True)
            # dir_b: init a repo and stage a file so compute_staged_diff_hash
            # produces a non-empty diff hash.
            subprocess.run(
                ["git", "init", "-q"],
                cwd=dir_b,
                capture_output=True,
                check=True,
                timeout=10,
            )
            (Path(dir_b) / "staged.txt").write_text("staged content for the test\n")
            subprocess.run(
                ["git", "add", "staged.txt"],
                cwd=dir_b,
                capture_output=True,
                check=True,
                timeout=10,
            )

            _, stdout_a, _ = run_hook(
                "audit-gate.py",
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": cmd},
                },
                project_dir=dir_a,
            )
            _, stdout_b, _ = run_hook(
                "audit-gate.py",
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": cmd},
                },
                project_dir=dir_b,
            )

            import re as _re

            out_a = json.loads(stdout_a)
            out_b = json.loads(stdout_b)
            m_a = _re.search(
                r"hash ([0-9a-f]{16})", out_a["hookSpecificOutput"]["permissionDecisionReason"]
            )
            m_b = _re.search(
                r"hash ([0-9a-f]{16})", out_b["hookSpecificOutput"]["permissionDecisionReason"]
            )
            self.assertIsNotNone(m_a)
            self.assertIsNotNone(m_b)
            self.assertEqual(
                m_a.group(1),
                m_b.group(1),
                "gh pr create with heredoc-only 'git commit' mention must "
                "produce a stable hash regardless of git state; otherwise "
                "the strip is not being applied to the staged_diff_hash branch",
            )
        finally:
            shutil.rmtree(dir_a, ignore_errors=True)
            shutil.rmtree(dir_b, ignore_errors=True)

    def test_real_git_commit_does_fold_staged_diff_hash(self) -> None:
        """Sanity contrapositive: a REAL git commit (no heredoc trick)
        SHOULD fold staged_diff_hash, so the same git commit command
        produces different hashes when the staged tree differs.

        Without this contrapositive the previous test could spuriously
        pass if compute_staged_diff_hash always returned "no-diff" (e.g.,
        if git were missing). This test would fail in that case, so the
        pair together pins the actual behavior.
        """
        dir_x = tempfile.mkdtemp(prefix="carrel-audit-real-empty-")
        dir_y = tempfile.mkdtemp(prefix="carrel-audit-real-staged-")
        try:
            for d in (dir_x, dir_y):
                (Path(d) / ".claude" / "logs" / "audits" / "approved").mkdir(parents=True)
                (Path(d) / ".claude" / "logs" / "audits" / "pending").mkdir(parents=True)
                subprocess.run(
                    ["git", "init", "-q"],
                    cwd=d,
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
            (Path(dir_y) / "staged.txt").write_text("staged content\n")
            subprocess.run(
                ["git", "add", "staged.txt"],
                cwd=dir_y,
                capture_output=True,
                check=True,
                timeout=10,
            )

            cmd = "git commit -m sanity"
            _, stdout_x, _ = run_hook(
                "audit-gate.py",
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": cmd},
                },
                project_dir=dir_x,
            )
            _, stdout_y, _ = run_hook(
                "audit-gate.py",
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": cmd},
                },
                project_dir=dir_y,
            )

            import re as _re

            out_x = json.loads(stdout_x)
            out_y = json.loads(stdout_y)
            m_x = _re.search(
                r"hash ([0-9a-f]{16})", out_x["hookSpecificOutput"]["permissionDecisionReason"]
            )
            m_y = _re.search(
                r"hash ([0-9a-f]{16})", out_y["hookSpecificOutput"]["permissionDecisionReason"]
            )
            self.assertNotEqual(
                m_x.group(1),
                m_y.group(1),
                "real git commit must fold staged_diff_hash; identical hash "
                "across distinct staged trees means the approval-laundering "
                "protection from the prior commit (92186f19) is broken",
            )
        finally:
            shutil.rmtree(dir_x, ignore_errors=True)
            shutil.rmtree(dir_y, ignore_errors=True)


class DebateTriggerFalsePositiveTests(unittest.TestCase):
    """The debate-trigger must not fire on free-text inside heredoc commit messages.

    The previous regex matched the word "dependency" anywhere in a Bash
    command, which produced false positives for commit messages that
    mentioned managed-package-update workflows. The fix is to match only
    on actual command verbs at command-position boundaries.
    """

    def test_heredoc_commit_message_with_arch_words_does_not_fire(self) -> None:
        # Commit message text contains "dependency", "architecture", "data model".
        # The regex must NOT fire on free text inside a heredoc.
        cmd = (
            "git commit -m \"$(cat <<'EOF'\n"
            "chore(deps): document the managed package dependency story\n\n"
            "Discusses the architecture decision for the data model layer.\n"
            'EOF\n)"'
        )
        rc, stdout, _ = run_hook(
            "debate-trigger.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
            },
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "", "debate-trigger fired on heredoc free text")

    def test_pnpm_add_command_does_fire(self) -> None:
        rc, stdout, _ = run_hook(
            "debate-trigger.py",
            {
                "tool_name": "Bash",
                "tool_input": {"command": "pnpm add some-package"},
            },
        )
        out = json.loads(stdout)
        self.assertIn("hookSpecificOutput", out)
        self.assertIn("debate trigger", out["hookSpecificOutput"]["additionalContext"].lower())

    def test_editing_manifest_file_does_fire(self) -> None:
        rc, stdout, _ = run_hook(
            "debate-trigger.py",
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/Users/madu/Desktop/Codex/pyproject.toml",
                    "old_string": "x",
                    "new_string": "y",
                },
            },
        )
        out = json.loads(stdout)
        self.assertIn("hookSpecificOutput", out)

    def test_verb_in_heredoc_body_does_not_fire(self) -> None:
        # Real recurring false-positive: a Python snippet piped via heredoc
        # contains the literal text `pnpm add`, which the verb regex would
        # otherwise match. Mirrors the audit-gate heredoc-strip fix.
        cmd = (
            "cat << 'PY' | python\n"
            "import json\n"
            'cmd = "pnpm add lodash"\n'
            'print(detect("Bash", {"command": cmd}))\n'
            "PY"
        )
        rc, stdout, _ = run_hook(
            "debate-trigger.py",
            {"tool_name": "Bash", "tool_input": {"command": cmd}},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(stdout.strip(), "", "verb inside heredoc body must not fire")

    def test_real_verb_after_heredoc_still_fires(self) -> None:
        cmd = (
            "cat > /tmp/note.txt << 'EOF'\n"
            "draft note about pnpm add for context\n"
            "EOF\n"
            "pnpm add lodash"
        )
        rc, stdout, _ = run_hook(
            "debate-trigger.py",
            {"tool_name": "Bash", "tool_input": {"command": cmd}},
        )
        out = json.loads(stdout)
        self.assertIn("hookSpecificOutput", out)
        self.assertIn("debate trigger", out["hookSpecificOutput"]["additionalContext"].lower())

    def test_unclosed_heredoc_falls_through_and_fires(self) -> None:
        # Safe-fail direction: a malformed/unclosed heredoc preserves its
        # body; a real verb inside still fires. Over-fire is acceptable;
        # under-fire would let architectural changes ship undebated.
        cmd = "cat > /tmp/x.txt << EOF\npnpm add lodash\n"
        rc, stdout, _ = run_hook(
            "debate-trigger.py",
            {"tool_name": "Bash", "tool_input": {"command": cmd}},
        )
        out = json.loads(stdout)
        self.assertIn("hookSpecificOutput", out)


if __name__ == "__main__":
    unittest.main()
