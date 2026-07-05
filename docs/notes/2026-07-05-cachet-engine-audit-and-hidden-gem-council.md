# Cachet engine: full teardown, build-decision audit, and hidden-gem council (2026-07-05)

Status: VERDICT (registered same-day per the trigger-3 process lesson).
Method: 3 parallel code readers over `cachet_verify/` + `services/legal/` + routes/tests/docs;
Vulcan-grounded architecture audit; five-seat council (Harvey, Bellwether, adversary,
synthesizer) on the hidden-gem question. Briefs archived in the session scratchpad.

---

## Part 1 — The engine, in pieces

One sentence: **a deterministic three-state grounding oracle whose failure mode is
engineered to be silence, never a confident wrong answer.**

Layers (verified by full reads, citations in the session briefs):

- **The frozen contract** (`cachet_verify/contract.py`): `verified | altered |
  could_not_check`, no fourth state, no confidence numbers. `combine()` is ~20 lines:
  any `altered` wins outright; any abstention floors the verdict; `verified` requires
  unanimity; an empty check set is a refusal ("silence is never a pass"). Provenance is
  mandatory on every check *by constructor*, so every green is scoped and attributable.
- **The orchestrator** (`adapter.py`): four legs per claim — verbatim quote check,
  anchor-free near-copy (negation/proper-noun flips), clause adjudication, residue
  (quantity/count) comparison — with a disagreement veto that outranks confirmation.
  The `SourceIndex` candidate index is a *filter, never a ranker*: union of
  token/value/norm inverted indices, no top-K, no scores, so a candidate cannot be
  silently dropped. Superset + byte-identical-differential properties are locked by
  ~350 randomized-corpus tests.
- **The anchor substrate** (`services/legal/anchors.py`, 13 anchor types): money to
  integer cents, percent to basis points via Decimal, dates refuse ambiguous locales,
  polarity carries its noun class so "exclusive license" never compares to "exclusive
  remedy". The recurring pattern: **refuse rather than mint a wrong canonical.**
- **Honesty by construction, not by testing**: SI-1/SI-3 are could-not-check-only (a
  false loud flag is impossible, not unlikely); figures are never affirmed post-ADR-0013;
  `on_topic=False` by construction means a value coincidence can never earn a green;
  the T1 NLI tier is dark behind a fail-closed hash interlock and even when live can
  only promote to an assessed refusal, never a verdict.
- **The notary** (`certificate.py`): canonical JSON, SHA-256 sealed, offline
  re-derivable verdict-for-verdict; exhibit vocabulary bans "passed/green/100%".
- **The isolation shell** (`daemon.py`): loopback-only stdlib server, constant-time
  token compare, no request-content logging; zero-egress proven by two independent
  socket-ban suites plus route/daemon byte-parity.
- **The portable spec** (`conformance.py` + corpus): executable honesty floors with a
  vacuous-pass refusal; any port must pass or it is not Cachet.

Test posture: ~150 kernel-core test functions plus the large legacy suites; classes
locked include false-green gaming, false-accusation (locale/synonym/cross-family),
buried-clause long-doc attacks, daemon fuzz, cross-instance determinism, anti-wedge
ceilings, tamper-evidence, CLI exit-code discipline. This is genuinely strong.

## Part 2 — Build-decision audit (Vulcan-grounded)

| # | Decision | Verdict | The steelman against, and why it holds anyway |
|---|---|---|---|
| 1 | No LLM in the verdict path | **Right** | Counter: coverage ceiling (~60% OOD catch, ~0 on prose) bores buyers vs LLM-judge demos. That is a GTM cost, not an architecture flaw; the T1 pattern already shows how to add gated semantic tiers that are structurally green-incapable. Deterministic-gates-over-LLM-judges is the verified rule. |
| 2 | Three-state frozen contract, ~20-line algebra | **Right — exemplary** | Counter: freezing a wire contract at n=0 customers risks freezing the wrong one. But the contract IS the product promise; it is additive-only and tiny. Deep module in the Ousterhout sense: trivial interface, enormous hidden functionality. |
| 3 | Could-not-check-only checks by construction | **Right — the durable invention** | Counter: over-refusal degrades UX. But a refusal is not a false positive; the "sort the failure first" rule (semantic ambiguity → refuse-only; morphological gap → fixable flag) is the transferable engineering law this project produced. |
| 4 | Zero-egress as a *process property* (loopback daemon + socket-ban tests, no egress env var) | **Right** | Counter: macOS + local daemon complicates enterprise/VDI deploys. Distribution problem, not architecture; the stdlib-only daemon is maximally portable. |
| 5 | Candidate index as filter-never-ranker | **Right** | Cost consciously accepted and documented in code: degenerate multi-value claims flip altered→refusal (safe direction). |
| 6 | Hash-sealed certificate | **Right for now — #1 engineering gap** | The fingerprint is SHA-256, not a signature. No issuer identity, no key, no timestamping authority. ADR-0015 says "signed daemon"; the code seals, it does not sign. For a demanded-mark strategy the *issuer* is the point. Ed25519 + key management is the missing brick before any third party relies on a certificate. |
| 7 | Conformance corpus as executable spec | **Right — under-invested** | 32 cases, English-only, one source per case (multi-source disagreement unexercised in conformance). Cheapest moat to grow. |
| 8 | Deterministic COUNT ceilings (anti-wedge) | **Right** | Hardware-drift of the ceiling's meaning is known and consciously deferred (ADR-0014 step 2). |
| 9 | Strangler-fig kernel extraction | **Right method, live risk** | `nearcopy.py` + corpus are byte-duplicated across repos with manual sync. Finish the extraction before a drift bug embarrasses a certificate. |
| 10 | English-only tokenization (`[a-z]+`, English unit tables, US-only citations) | **Right-for-now — #2 gap, and it collides with the GTM** | Non-Latin text degrades to refusal (safe direction), but coverage on Arabic/French documents is near zero while the ratified GTM channel is Lebanon→GCC. The engine's honesty holds; its usefulness on the target market's own documents is untested. Probe with one real bilingual contract before interview #1 demos. |
| 11 | Sentence-level unit of grounding | **Acceptable** | Under-claims, never over-claims; documented; citation-aware splitter fix scoped but unbuilt. |
| 12 | `contract_verify.py` (1,299 lines of accreted precedence logic) | **The one complexity hotspot** | High change-amplification risk; the red-team patches accreted tactically. The extraction rewrite should use the conformance corpus as its safety net. |

Overall: the architecture is unusually coherent — the honesty invariant is enforced at
every layer (algebra, checks-by-construction, conformance floors, exhibit vocabulary).
The build decisions were right. The two real debts are the unsigned certificate and the
English-only/GCC collision; the one structural risk is the unfinished extraction.

## Part 3 — The hidden-gem council (five seats, verdict + dissent)

Question: is there a higher-value application of this exact engine outside the ratified
legal-first path? Candidates: AI-builder groundedness gate; defense/intel air-gapped;
healthcare ambient-scribe verification; financial audit tie-out; plus seat-surfaced.

**Verdict (synthesizer, all seats concurring on the head question): STAY THE COURSE.
Nothing beats legal-first. No pivot, no parallel build track.** The correct "alongside"
work is already in the billions plan: ship the free public certificate verifier +
publish the schema/conformance corpus (~1 week, zero sales cycle) — the surface that
converts every candidate market into *inbound* signal.

Ranked survivors (cost in founder-hours ≈ 0; ride existing conversations):

1. **Issuer-side financial tie-out (MNPI/Reg FD)** — the genuinely new insight of the
   round (Bellwether). Pre-release earnings/10-K numbers are MNPI: piping them to a
   cloud LLM judge is an insider-information exposure, so zero-egress is *legally
   decisive*, not nice-to-have. Mechanism fit is clean (numbers, dates, versions —
   all mechanical, English). Escalation signal: a controller says "I am legally
   forbidden from letting pre-release numbers touch a cloud tool, and nobody gives me
   an independent reproducible attestation."
2. **CSRD/ESRS sustainability assurance** (Harvey) — EU-mandated *third-party*
   assurance of largely numeric data, no entrenched incumbent. Watch-item: one
   conversation with a sustainability-assurance lead, opportunistically.
3. **Audit tie-out** — best literal capability fit, but incumbent-held (DataSnipper
   across all Big Four; Suralink FS Tie-Out since 2026-04) and already rung 3 of the
   ratified ladder. Not new; do not resequence. The one probe question: "You have
   DataSnipper — why would you need an *independent* attestation your own tool can't
   give you?"
4. **Defense/intel** — purest moat fit (zero-egress is the entry ticket), wrong clock:
   ATO/clearance-gated 18–36 months, SBIR authority lapsed 2025-09-30, feasibility
   already scored 2/10, certificates unsigned. Pure watch-item; escalates only if a
   cleared sponsor self-identifies or the requirement lands at CUI/IL4.

Killed: **healthcare ambient scribes** (no revealed demand for independent post-hoc
verification — physician sign-off IS the ratified assurer; the dangerous error class is
inventive/semantic, which the engine refuses by design; Windows/Epic wall) and the
**broad AI-builder eval market** (anti-fit: the buyer optimizes for throughput and
pays you to shrink the refusal rate — i.e., to erode the only defensible property).

Dissent recorded (Bellwether, verbatim): "That, not healthcare or the broad AI-builder
market, is your highest-value adjacency where all four properties are simultaneously
load-bearing" — issuer-side tie-out could reorder the plan if a single buyer confirms
it, which is why it is probe #1 rather than dismissed.

Revisit triggers: (a) a legal-wedge costly-yes lands → ratified ladder proceeds;
(b) an *independence* mandate lands first elsewhere (PCAOB/SEC "independently attest",
or CSRD numeric tie-out confirmed open); (c) the issuer-side probe returns a
moat-driven yes; (d) a cleared defense sponsor appears / CUI-level requirement.

The engineering corollary of the council: whichever door opens, the same two bricks are
load-bearing first — **sign the certificate (issuer identity)** and **finish the kernel
extraction**. Both are already ADR-0014/0015 work. The strategy and the architecture
point at the same next moves.
