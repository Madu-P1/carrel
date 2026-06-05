# Forge queue — Cachet extraction (safe, well-bounded phases only)

Governed by `docs/adr/ADR-0011-extract-cachet-strangle-carrel.md` and
`docs/plans/cachet-extraction-2026-06-05.md`. Only the additive, reversible,
verify-gated phases are autonomous-eligible here. P2-P5 are operator-led and
are tracked in `TODOS.md`, not in this queue, per ADR-0011: P2 is judgment-heavy
(branch reconciliation + new entrypoints), P3 is feature deletion (Chesterton's
Fence: only the operator confirms which features are truly dead), and P4/P5 are
irreversible one-way doors.

Activate this queue only by switching the active contract (see the header of
`.claude/forge.cachet-extraction.contract.yaml`). Arming the loop is an operator
decision.

## T-CX0 — Pin verify behavior with a characterization net (plan P0)
- Status: pending
- Deps: none
- Acceptance: add a characterization test over the verify path that pins the
  grounding envelope contract `services/verify.py` consumes (`claims`,
  `unsupported_spans`, `citations`, `provider`) and the per-claim verdict
  mapping, for a fixed draft and a fixed source pool, including these cases:
  empty draft, no sources, a seeded-wrong citation, and a verbatim-quote miss.
  The new test passes under the verify suite; no non-test file is modified;
  the existing verify and legal suites stay green.

## T-CX1 — Introduce the grounding seam (plan P1)
- Status: blocked-by T-CX0
- Deps: T-CX0
- Acceptance: add `services/grounding.py` exposing `ground()` and
  `ground_stream()` that wrap `services.tutor.grounded_tutor_envelope`
  (`services/verify.py:251`) and `grounded_tutor_envelope_steps`
  (`services/verify.py:610`). Change `services/verify.py` to call
  `services.grounding` instead of importing `services.tutor` directly, so that
  `grep -n "tutor" services/verify.py` shows no direct tutor import. Verify
  output is byte-identical to pre-change (the T-CX0 net stays green).
  `services/tutor.py` is unchanged. `services/legal/*` and the deterministic
  verify core are untouched.

## P2-P5 — OPERATOR-LED (deliberately excluded from this autonomous queue)
- **P2 (Cachet-only skeleton):** branch reconciliation (bring the Option A
  frontend + `serve-cachet.py` onto trunk), a `CACHET_ONLY` backend
  composition, a verify-only `AppShell`. Judgment-heavy; operator-led.
- **P3 (strangle the baggage):** deletes whole features. Only the operator
  confirms which are truly dead (Chesterton's Fence). May be added here later,
  slice-by-slice and drafts-only, after the dead-feature list is confirmed.
- **P4 (drop study tables):** irreversible data loss. Operator-gated one-way
  door (ADR-0011).
- **P5 (identity rename):** irreversible. Operator-gated one-way door
  (ADR-0011).

See `TODOS.md` and `docs/plans/cachet-extraction-2026-06-05.md` for the full
P2-P5 detail.
