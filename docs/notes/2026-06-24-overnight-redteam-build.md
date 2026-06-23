# Overnight build — the Cachet confession ledger (2026-06-24)

Sanctioned autonomous BUILD night. Validation paused for the night by operator
instruction; nights are for building. Council convened first; verdict recorded at
`docs/decisions/0008-unattended-redteam-discovery-not-fix.md` and
`.forge/debates/engine-redteam-vs-polish/decision.md`.

## The goal (one sentence)

By morning, Madu wakes to a defensible, buyer-legible **confession ledger** —
Cachet attacking its own deterministic honest-refusal engine across many
false-green attack families and thousands of generated pairs, every crack
reproduced and logged with the exact held-out test that would lock it — built as
new, fully-tested, verify-green code that touches **no** gated engine file, plus
**drafted (un-merged)** fixes and a **see-able** demo beat, all in small
reviewable commits, nothing pushed.

## Why this, not the alternatives (council)

- Three seats (Harvey, Vulcan, Bellwether) independently chose engine hardening /
  a defensible adversarial artifact as the highest-value target. The 2026
  sanctions frontier has moved off citation-existence onto misrepresented
  holdings and altered quotes — exactly the false-green surface. A regulated
  in-house buyer's security review is *built to consume* an adversarial
  findings-and-remediation artifact; a discredited "hallucination-free" claim is
  not.
- The adversary won the *mechanism* argument decisively: an unattended loop
  editing the gated truth-surface files (`contract_verify.py`,
  `deterministic_envelope.py`, `anchors.py`, `sentences.py`, `case_verification.py`,
  `local_caselaw.py`) reproduces the `mln` false-negative-laundering failure with
  Madu absent, and the repo's `human_gates.security` + missing held-out set make
  an autonomous engine ship impossible anyway.
- Resolution: **split** the red-team. The DISCOVERY half is read-only against the
  engine (no engine edits), so it is safe to run unattended AND is the artifact
  the buyer wants. The FIX half is drafted + queued for review, never merged.

## The plan (workstreams)

1. **Harness** (`evals/adversary/`): `engine_probe` (read-only adapter over the
   real `verify_claim_against_clause` + `build_deterministic_envelope` /
   `local_caselaw_client`; disposition→{supported,contradicted,could_not_verify};
   zero-egress), `families` (attack generators, each case carries its provable
   honest expectation), `mutators` (deterministic perturbation to reach scale),
   `harness` (orchestrator + classifier), `ledger` (md+json writer). PRIMARY.
2. **Tests** (`tests/test_adversary_harness.py`): harness is itself test-gated
   and green; full run holds under the socket ban.
3. **Battery → ledger** (`.claude/adversary/`): leads with surfaced cracks (the
   confession), then the held summary. Honest framing, not a trophy case.
4. **Fix drafts**: each crack → proposed fix + held-out test, queued REVIEW, not
   merged. Madu's morning reading list.
5. **S1**: additive `split_sentences` property coverage (safe, non-gated).
6. **D4**: supported-count-beside-refusal frontend draft + screenshot (craft
   review). The see-able demo beat.
7. **Mythos** cold review of the diff; fix real findings, route engine ones to
   REVIEW.
8. **Verify** subset green; small commits on the branch; nothing pushed.
9. **Jarvis night-shift wrap** + jaw-drop morning report.

## Hard constraints (inviolable)

- Honest-refusal constitution holds: no silent fallbacks, no false greens,
  structural nodes never citable, drafts-only on the moat.
- The harness touches NO gated truth-surface file (it calls the engine, never
  edits it). Engine fixes are drafted + queued, never autonomously merged.
- Every increment test-gated + verify-green; small reviewable commits on the
  worktree branch; NOTHING pushed/merged/PR'd without Madu's explicit yes.
- Zero-egress preserved (socket ban in tests).

## Engine interface (recon, so the ledger is built against the REAL engine)

- Contract core (pure, no DB, no net): `verify_claim_against_clause(claim, clause)
  -> ClauseVerdict` in `services/legal/contract_verify.py`. Dispositions:
  `present | parametric_contradiction | multi_value_unverifiable |
  conflicting_clauses | not_found`.
- Litigator (in-memory): `build_deterministic_envelope(draft,
  client=local_caselaw_client())` in `services/legal/deterministic_envelope.py`;
  read `claims[i].case_verdicts[*].verdicts[*].exists` + refusal flags
  (caption_mismatch, year_mismatch, court_mismatch, bounded_corpus...).
- State mapping mirrors `script/cachet-acceptance.py`:
  `present→supported`, `parametric_contradiction→contradicted`, refusals →
  `could_not_verify`.
- Zero-egress: `mock.patch.object(socket, "socket", _raise)` (see
  `tests/test_zero_egress.py`).
