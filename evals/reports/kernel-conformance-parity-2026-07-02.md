# Kernel conformance parity: Codex kernel vs companion engine (2026-07-02)

Shared executable spec: `cachet_verify/conformance_corpus/nonlegal-v1.jsonl`
(24 cases), run through `cachet_verify.conformance.run_conformance` on both
implementations. Floors: no false green, no false accusation, honest refusal,
three-state vocabulary.

| Implementation | Conformant | Catch | Faithful confirmed | Refusals |
|---|---|---|---|---|
| Codex kernel (`cachet_verify.adapter`) | YES | **15/15** | **5/5** | 4/4 |
| Companion (`cachet_companion.verify`) | YES | 8/15 | 1/5 | 4/4 |

Both engines hold every honesty floor. The drift is in COVERAGE, exactly the
class ADR-0014 predicted for a vendored fork:

Companion misses (all honest refusals, never wrong verdicts):
- F5, C1 (magnitude alterations: 60-vs-20 billion, million-to-billion)
- M4 (textual date drift)
- T1 (order-of-magnitude money threshold)
- M1, C4, P2 (dosage / tons / grouped counts: the batch-A residue detectors
  do not exist in the fork)
- F2, C2, M3, T2 (faithful confirmations: no restatement rule in the fork)

Standing guard: `tests/test_kernel_conformance.py` now lives in the companion
repo (committed) and gates its honesty floors in that repo's own suite. The
catch-rate gap closes when the strangler-fig replaces the fork with the
packaged kernel (ADR-0014 step 2->3).
