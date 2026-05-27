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
import time
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

    def test_gate_subagent_stop_is_silent(self) -> None:
        """Gate-role subagents (auditor, rater, debate roles) must not be nudged.

        Diagnosed 2026-05-26: when the implementing agent spawned the
        independent-auditor and the auditor finished without writing its
        APPROVED/REJECTED JSON, the score-loop's SubagentStop nudge told
        the auditor to "respond with a brief status summary and stop",
        which the auditor adopted in place of writing its verdict file.
        The routine wedged because the audit-gate hook treats a missing
        verdict file as "still pending". Fix: skip gate subagents in the
        score-loop entirely.
        """
        for gate_type in (
            "independent-auditor",
            "quality-rater",
            "proponent",
            "adversary",
            "synthesizer",
        ):
            out = self._run(
                {
                    "hook_event_name": "SubagentStop",
                    "session_id": f"test-gate-{gate_type}",
                    "subagent_type": gate_type,
                }
            )
            self.assertEqual(out, {}, f"score-loop must be silent for gate subagent '{gate_type}'")

    def test_gate_subagent_alt_key_locations(self) -> None:
        """The subagent_type field arrives under several possible JSON keys
        depending on Claude Code version. The hook checks all four
        plausible locations defensively; this test pins each one."""
        for payload_extra in (
            {"agent_type": "independent-auditor"},
            {"subagent": {"type": "independent-auditor"}},
            {"agent": {"type": "independent-auditor"}},
        ):
            payload = {"hook_event_name": "SubagentStop", "session_id": "test-alt"}
            payload.update(payload_extra)
            out = self._run(payload)
            self.assertEqual(
                out,
                {},
                f"score-loop must detect gate type under alt key location: {payload_extra}",
            )

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


class RouteTaskRoutingTests(unittest.TestCase):
    """Pin the prompt-pattern → skill mapping in route-task.py.

    Catches regex regressions: a misrouted pattern would suggest the
    wrong skill, a dropped pattern would fall through silently and
    waste cycles on generic execution.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="carrel-route-")
        self.project_dir = Path(self.tmpdir)
        (self.project_dir / ".claude").mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _route(self, prompt: str) -> dict:
        rc, stdout, _ = run_hook(
            "route-task.py",
            {"prompt": prompt, "session_id": "test-session", "cwd": str(self.project_dir)},
            project_dir=str(self.project_dir),
        )
        self.assertEqual(rc, 0)
        return json.loads(stdout) if stdout.strip() else {}

    def test_bug_keyword_routes_to_investigate(self) -> None:
        out = self._route("there is a bug in the importer")
        self.assertIn("/investigate", out["hookSpecificOutput"]["additionalContext"])

    def test_security_keyword_routes_to_cso(self) -> None:
        out = self._route("review for security vulnerabilities in the auth path")
        self.assertIn("/cso", out["hookSpecificOutput"]["additionalContext"])

    def test_ship_keyword_routes_to_ship_chain(self) -> None:
        out = self._route("ship it to production")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("/ship", ctx)
        self.assertIn("/land-and-deploy", ctx)

    def test_refactor_keyword_routes_to_simplify(self) -> None:
        out = self._route("can you refactor this module and clean it up")
        self.assertIn("/simplify", out["hookSpecificOutput"]["additionalContext"])

    def test_planning_keyword_routes_to_makeplan(self) -> None:
        out = self._route("we need a plan for the new feature")
        self.assertIn("/claude-mem:make-plan", out["hookSpecificOutput"]["additionalContext"])

    def test_performance_keyword_routes_to_benchmark(self) -> None:
        out = self._route("the page feels slow, can we benchmark it")
        self.assertIn("/benchmark", out["hookSpecificOutput"]["additionalContext"])

    def test_no_match_emits_no_suggestion(self) -> None:
        out = self._route("summarize today's commits in three sentences")
        self.assertEqual(out, {})

    def test_halt_file_emits_halt_message(self) -> None:
        (self.project_dir / ".claude" / "HALT").touch()
        out = self._route("bug in the importer that would normally route to /investigate")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("HALT signal present", ctx)
        self.assertNotIn("/investigate", ctx)

    def test_routing_log_written_with_suggestion(self) -> None:
        self._route("bug in the importer")
        log_file = self.project_dir / ".claude" / "logs" / "routing.jsonl"
        self.assertTrue(log_file.exists(), "routing.jsonl was not written")
        entries = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["suggestion"], "/investigate")
        self.assertIn("prompt_snippet", entries[0])
        self.assertEqual(entries[0]["session"], "test-session")

    def test_routing_log_written_on_no_match(self) -> None:
        # A non-matching prompt still produces a log entry (suggestion="")
        # so we have a complete trace of every prompt routed through the
        # hook, not just the ones that matched.
        self._route("summarize today's commits in three sentences")
        log_file = self.project_dir / ".claude" / "logs" / "routing.jsonl"
        self.assertTrue(log_file.exists())
        entries = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["suggestion"], "")

    def test_disabled_when_autonomous_unset(self) -> None:
        # Without CARREL_AUTONOMOUS=true the hook must exit silently so
        # ad-hoc Claude Code sessions don't see autonomous routing hints.
        proc = subprocess.run(
            [str(HOOKS_DIR / "route-task.py")],
            input=json.dumps({"prompt": "there is a bug here"}).encode("utf-8"),
            capture_output=True,
            env={
                "CLAUDE_PROJECT_DIR": str(self.project_dir),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            },
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode("utf-8").strip(), "")

    def test_first_matching_rule_wins(self) -> None:
        # A prompt that matches multiple rules takes the first one in the
        # ordered list. Pinning this prevents a rule reorder from silently
        # changing routing decisions.
        out = self._route("there is a security bug in this module")
        # "bug" comes first in the rules list, so /investigate wins over /cso.
        self.assertIn("/investigate", out["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("/cso", out["hookSpecificOutput"]["additionalContext"])

    def test_remaining_rules_route_correctly(self) -> None:
        # Parameterized coverage for the seven rules not exercised individually
        # above. The order-pin test catches list reorders; this test catches
        # in-rule regex tightening that would silently drop a previously-routed
        # phrase (e.g. narrowing the a11y pattern to drop "screen reader").
        cases = [
            ("run an adversarial review on this change", "/codex challenge"),
            ("can we do an a11y review of the new modal", "design:accessibility-review"),
            ("do some visual polish on the reader", "/design-review"),
            ("QA the import flow end-to-end", "/qa"),
            ("review this PR before I merge", "/review"),
            ("write a weekly retrospective for the team", "/retro"),
            ("update CLAUDE.md with the new conventions", "engineering:documentation"),
        ]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                out = self._route(prompt)
                self.assertIn(
                    expected,
                    out["hookSpecificOutput"]["additionalContext"],
                    f"expected {expected!r} suggestion for prompt {prompt!r}",
                )


class AuditGateTimeoutTests(unittest.TestCase):
    """Verify the T68 Phase 1 verdict-timeout behavior.

    The audit-gate auto-REJECTs a pending action whose pending file is
    older than AUDIT_TIMEOUT_SECONDS with no matching approved/rejected
    sibling. This prevents the wedge class diagnosed 2026-05-26 where
    an auditor subagent silently exited without writing a verdict.
    """

    def _setup_project_dir(self) -> str:
        tmp = tempfile.mkdtemp(prefix="carrel-timeout-test-")
        for sub in ("audits/pending", "audits/approved", "audits/rejected"):
            (Path(tmp) / ".claude" / "logs" / sub).mkdir(parents=True, exist_ok=True)
        return tmp

    def test_stale_pending_triggers_auto_reject(self) -> None:
        """A pending file older than AUDIT_TIMEOUT_SECONDS with no matching
        verdict triggers an auto-REJECTED file + denial on the next gate hit."""
        tmp = self._setup_project_dir()
        try:
            project = Path(tmp)
            payload = {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "git commit -m 'timeout-test synthetic action'",
                    "description": "synthetic timeout test",
                },
            }

            # First invocation: writes pending, denies with major-action gate.
            rc1, out1, _err1 = run_hook(
                "audit-gate.py",
                payload,
                env_extra={"CARREL_AUTONOMOUS": "true"},
                project_dir=tmp,
            )
            self.assertEqual(rc1, 0, "first invocation should exit 0")
            self.assertTrue(out1.strip(), "first invocation must emit a JSON envelope")

            pending_files = list((project / ".claude/logs/audits/pending").glob("*.json"))
            self.assertEqual(len(pending_files), 1, f"expected 1 pending file, got {pending_files}")
            pending_path = pending_files[0]
            stale_hash = pending_path.stem

            # Backdate the pending file's mtime to AUDIT_TIMEOUT_SECONDS + 60s ago.
            stale_mtime = time.time() - (300 + 60)
            os.utime(pending_path, (stale_mtime, stale_mtime))

            # Second invocation with the SAME payload (same hash). Should detect
            # the stale pending and auto-REJECT.
            rc2, out2, _err2 = run_hook(
                "audit-gate.py",
                payload,
                env_extra={"CARREL_AUTONOMOUS": "true"},
                project_dir=tmp,
            )
            self.assertEqual(rc2, 0, "second invocation should exit 0")
            out2_json = json.loads(out2) if out2.strip() else {}
            reason2 = out2_json.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            self.assertIn(
                "AUDIT-GATE TIMEOUT",
                reason2,
                f"second denial should be a timeout, got: {reason2!r}",
            )
            self.assertIn(stale_hash, reason2, "timeout denial should cite the same hash")

            # Rejected file written with auto_timeout=true.
            rejected_path = project / ".claude/logs/audits/rejected" / f"{stale_hash}.json"
            self.assertTrue(rejected_path.exists(), "rejected file should be written")
            rejected = json.loads(rejected_path.read_text())
            self.assertEqual(rejected.get("verdict"), "REJECTED")
            self.assertTrue(rejected.get("auto_timeout"), "auto_timeout flag must be true")
            self.assertGreaterEqual(rejected.get("age_seconds", 0), 300)

            # Wedge-postmortem appended.
            postmortem_path = project / ".claude/logs/wedge-postmortems.jsonl"
            self.assertTrue(
                postmortem_path.exists(),
                "wedge-postmortems.jsonl should be created when auto-timeout fires",
            )
            lines = [
                json.loads(line)
                for line in postmortem_path.read_text().splitlines()
                if line.strip()
            ]
            self.assertTrue(
                any(line.get("hash") == stale_hash for line in lines),
                "postmortem entry for stale_hash should be present",
            )
            self.assertTrue(
                any(line.get("wedge_class") == "timeout" for line in lines),
                "postmortem should classify the wedge as 'timeout'",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fresh_pending_does_not_trigger_timeout(self) -> None:
        """A pending file younger than AUDIT_TIMEOUT_SECONDS does not trigger
        the auto-REJECT path. The normal major-action gate fires instead."""
        tmp = self._setup_project_dir()
        try:
            project = Path(tmp)
            payload = {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "git commit -m 'fresh-pending synthetic'",
                    "description": "synthetic fresh test",
                },
            }

            rc1, _out1, _err1 = run_hook(
                "audit-gate.py",
                payload,
                env_extra={"CARREL_AUTONOMOUS": "true"},
                project_dir=tmp,
            )
            self.assertEqual(rc1, 0)

            rc2, out2, _err2 = run_hook(
                "audit-gate.py",
                payload,
                env_extra={"CARREL_AUTONOMOUS": "true"},
                project_dir=tmp,
            )
            self.assertEqual(rc2, 0)
            out2_json = json.loads(out2) if out2.strip() else {}
            reason2 = out2_json.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            self.assertNotIn(
                "AUDIT-GATE TIMEOUT",
                reason2,
                "fresh pending must not trigger the timeout path",
            )

            rejected_files = list((project / ".claude/logs/audits/rejected").glob("*.json"))
            self.assertEqual(
                rejected_files,
                [],
                f"no rejected file should be written for fresh pending; got {rejected_files}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
