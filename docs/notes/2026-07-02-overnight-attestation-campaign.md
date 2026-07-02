# Overnight attestation campaign — 30 upgrades toward ADR-0015 (2026-07-02)

Operator order: set the attestation-layer verdict as the north star, execute
30 upgrades toward it with a Mythos review every 5, fix what survives, deliver
a PR. This log is the audit trail. Every upgrade is test-locked; every Mythos
ledger is under `.mythos/`; every fix cites its finding.

## The scoreboard

- **30/30 upgrades delivered**, in six batches of five.
- **6 Mythos reviews** (5 batch-scoped + 1 full-campaign sweep), each with
  fresh-context finder + independent refuter per candidate.
- **Findings: 8 confirmed and fixed, 5 refuted (no fix needed, reasons
  recorded), 2 additional floor defects found by the campaign's own tests
  mid-build and fixed.**
- Conformance floors at close: **15/15 altered caught, 5/5 faithful
  confirmed, 5/5 honest refusals, 0 false greens, 0 false accusations** on
  the 25-case shared corpus; the same corpus gates the companion repo.
- Latency: verify_claim p50 **0.42 ms**; attest_draft **147 ms** for a
  25-claim draft against a whole-corpus source (was 271 ms before the
  relevance prefilter).

## The batches

**A (1-5) — blind spots closed.** Kernel residue detectors: dosages
(metric mass/volume/IU with exact in-family conversion), physical-unit
quantities (regionally ambiguous units isolated so ton/tonne can never
mis-accuse), grouped counts (year-shaped integers refused). Near-copy
accusation gate, exact-restatement confirmation, span precedence. Parity
went 12/12 with 3 documented blind spots -> 15/15 with the blind spots as
catches. *Mythos #1: bare single-letter units ('Question 4 g', '5G', '10m')
were a confirmed false-accusation class -> removed; refuted: glued '5gram'.*

**B (6-10) — the adjudicator swallowed.** Every source sentence becomes a
ClauseCandidate under the app's own cross-clause adjudicator (on_topic=False
so value coincidences never green). attest_draft for whole drafts;
truncation-honest source records; combine() property tests; daemon /health +
stable error taxonomy. Two false greens caught by the batch's own tests
mid-build (restatement overriding a same-fact conflict; doc-wide candidate
fan-out manufacturing conflicts) and fixed. *Mythos #2 (critical): a REWORDED
amendment slipped the skeleton-equality veto so a restatement greened a
contradicted value -> topical-overlap veto (over-refusal is the residual
error direction, never a green).*

**C (11-15) — the demandable certificate.** Canonical JSON + SHA-256 seal;
tamper-evidence (a flipped verdict breaks the seal); full OFFLINE
revalidation; daemon /attest with injected clock (byte-identical certs);
filing-grade exhibit with a banned-vocabulary register test; the CLI gate
(exit codes 0/1/2 = verdicts). *Mythos #3 (critical): an unwritable
--certificate path crashed to exit 1 == 'altered' for a $?-keyed CI gate ->
guarded write + last-resort exit 4; argparse usage errors exited 2 ==
could_not_check -> _GateParser exits 3. Refuted: exhibit off-taxonomy
miscount (unreachable), canonical NaN (unreachable).*

**D (16-20) — conformance is the spec.** The honesty floors as a runnable
suite + shared JSONL corpus; a dishonest implementation provably fails it.
Companion parity RUN and recorded: honesty-conformant, 8/15 catch vs our
15/15 — ADR-0014's drift, now a number; a standing floor test committed into
the companion repo. Kernel-boundary zero-egress (socket ban over the whole
public surface). In-batch floor fix: cross-fact contradictions filtered
before adjudication ('break fee $3M' can no longer be accused because a
marketing budget is $7M; true accusations now cite the same-fact clause).
*Mythos #4: finder's synonym-subject miss REFUTED decisively (fixing it
reopens the break-fee false accusation); tradeoff made visible as corpus
case G4.*

**E (21-25) — surface value.** POST /api/attest (wire byte-equal to local
issuance; inherits the local-API token gate); the embedder guide
(docs/kernel/EMBEDDING.md); latency benchmark + pathology ceiling; CLI
--conformance (a distribution proves itself in one command); Sequence-typed
sources. *Mythos #5: vacuous conformance pass (empty corpus certified a
distribution) -> per-truth-class exercise required; unbounded route +
superlinear fan-out -> caps AND a relevance prefilter (271->147 ms);
exit-taxonomy gap -> 3. Refuted: issued_at backdating (documented
affordance; no timestamp-authority guarantee is claimed).*

**F (26-30) — adversarial hardening + delivery.** The battery: locale
attacks (two live cracks found and fixed — '1.000 mg' false accusation,
'1,5 mg' tail-anchor), verdict gaming (quote-padding, self-sourcing,
confusable digits — all bounced off the algebra), daemon fuzz,
cross-instance determinism, mixed concurrent load. This log, the ADR
addendum, the full chain, Mythos #6 (full-campaign sweep), the draft PR.

## What this means against the north star

The kernel now IS the thing ADR-0015 names: one deterministic attestation
core with a frozen 3-state contract, provable zero-egress at the package
boundary, a sealed offline-revalidatable certificate, four ways in (Python
API, loopback daemon, CLI gate, app route) that return byte-compatible
artifacts, an executable conformance spec that both repos answer to, and an
adversarial record showing the floors hold under attack. The strangler-fig
has its trunk; the companion migration (step 2->3) is the next campaign.

## Standing debts (honest)

- The engine's sentence-pair fan-out is still superlinear on digit-dense
  documents; the prefilter and route caps bound it, a per-request sentence
  cache removes it (next campaign).
- Synonym-subject alterations (G4) and ratios/frequencies/temperatures
  (G1-G3) refuse honestly; each needs its own unambiguous detector.
- The kernel wraps services.legal via the adapter seam; physical extraction
  into a pip-installable package is ADR-0014 step 2, gated per ADR-0015 on
  the wedge.
- Frontend surfaces do not yet render certificates; craft-gated work.
