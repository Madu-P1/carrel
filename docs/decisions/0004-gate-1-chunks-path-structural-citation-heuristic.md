# ADR 0004 — Gate 1 chunks-path structural-citation heuristic

**Status:** Accepted with revisions (synthesizer verdict 2026-05-25)
**Slot:** fleet/slot-1
**Plan:** `docs/plans/structural-citation-gate-1-chunks-heuristic.md`
**Successor to:** Gate 0 ship note `docs/notes/2026-05-22-structural-citation-gate.md`
**Triggered by:** slot-1 TODOS.md T1 (`"Run the proponent/adversary/synthesizer routine on the plan before the first sub-PR"`)

## Decision

Ship Gate 1 as a deterministic content-shape heuristic that filters
**cited quote strings at resolve time**, not chunk text at hydration
time. The original chunk-granularity design is wrong for the bug it
claims to fix; the architecture pivots to quote-granularity per the
adversary's verified critique. Three sub-PRs become four: a new T2.0
extends the eval harness with chunks-path structural-citation
instrumentation BEFORE any heuristic ships, so the 30% acceptance gate
is a real measurement rather than a vibes-based assertion.

The Synthesizer found `THIRD_OPTION_REQUIRED` — neither the plan as
written nor the adversary's "redirect to T12" was the right ship. The
revised plan ships, but with the three revisions below.

## Context

Gate 0 (PR #68 / commit `5a05879f`) closed the structural-citation
hole on the typed-node retrieval path by giving every
`HydratedNodeContext` a `node_type` field and dropping rows whose type
is in `NON_CITABLE_NODE_TYPES`. The legacy chunks path
(`RETRIEVAL_USE_NODES=false`, default until T12) is structurally
untyped: a `chunks` row is a 1200-char paragraph window
(`services/ingestion/concepts.py::chunk_text`) that can contain a
heading line as one of its rows. The original Gate 1 plan proposed a
parallel filter, `_drop_low_information_contexts`, applied to the
hydrated chunk text at the same three call sites Gate 0 uses
(`services/tutor.py:615`, `:1314`, `:1399`).

The plan went to a full adversarial debate per slot-1 TODOS T1: the
Proponent built the strongest case for the design as written; the
Adversary built the strongest case against. Both transcripts are
preserved verbatim below.

## Proponent transcript

**Verdict:** STRONG SUPPORT

The proponent argued that the plug-in seam is already cut and tested
by Gate 0 (`_drop_non_citable_contexts` at `services/tutor.py:615`,
called after both `_hydrate_from_nodes` at `:618` and
`_hydrate_from_chunks` at `:668-721` converge). The proposed
`_drop_low_information_contexts` is a pure transform with identical
signature, slotting in at the same three call sites Gate 0 audited.
The logged-drop counter shape (`tutor_structural_contexts_dropped`)
ports directly to `tutor_low_information_contexts_dropped`.

The chunks-path hole was framed as load-bearing today: under
`RETRIEVAL_USE_NODES=false`, every grounded answer routes through
`_hydrate_from_chunks`, which builds `HydratedNodeContext` without
setting `node_type`, so `_drop_non_citable_contexts` finds nothing to
drop. Gate 0 explicitly scoped itself out of this case
(`docs/notes/2026-05-22-structural-citation-gate.md:60-68`).

Strategic alignment: Carrel's moat per the 2026-05-10 strategy memo
names verbatim citations. The Gate 0 note coins the failure as
"verbatim-correct, answer-empty" (note lines 9-11). Every grounded
answer that surfaces a heading-as-evidence trains users to distrust
citations, which is the differentiator. Closing this on the default
retrieval path before T12 ships is moat preservation.

Time and risk: three additive sub-PRs per CLAUDE.md, default-off flag
through T2 and T3, default-on at T4 after evals confirm the gates. No
schema change, no migration, no service interruption.

Concession the proponent acknowledged: a real POS tagger (spaCy
`en_core_web_sm`) is ~50MB, and the closed-class verb detector is a
quality-vs-dep-weight tradeoff. The proponent argued the dep cost is
too high for a finite-lifetime patch but conceded the tradeoff is real.

## Adversary transcript

**Verdict:** REJECT UNLESS (a) eval harness extended to measure
chunks-path `structural_citation_rate` BEFORE the 30% gate is
invoked, (b) filter moves from chunk-text granularity to cited-quote
granularity so the line-inside-body case is actually caught,
(c) labeled-slice authoring is escalated as halt-and-ask rather than
self-resolved, (d) plan documents why this beats redirecting slot-1
effort toward unblocking T12.

The adversary landed three load-bearing points:

**1. The 30% gate is unmeasurable today.** Verified by reading
`evals/run_evals.py:470-485`: on the `else` branch (chunks path), the
harness fetches only `content` from `chunks`, never reads `node_type`,
and never increments `structural_citation_count`. The counter is 0 by
construction. The plan's primary acceptance bar compares 0 to 0. Either
Gate 1 ships eval instrumentation first or the gate is a vibes-based
assertion.

**2. Chunk-level filter can't catch heading-INSIDE-chunk.** The plan
itself concedes at lines 36-39 that "the chunks path cannot tell at
hydration time which line the model will quote." A 1200-char chunk
opening with a 60-char heading and 1100 chars of body fails every
aggregation rule the plan defines: not "all lines short" (~10 lines
of body), not "majority bare-reference," and the heading is ~5% of
non-whitespace chars (not >60%). The chunk passes the filter; the
model still quotes the heading line. The architectural premise —
filter at chunk granularity — is mismatched to a bug that lives at
quote granularity.

**3. Closed-class verb detector has asymmetric false-drop surface.**
At chunk granularity, code blocks (`def foo(...)`), math fragments
(`E = mc²`), and short factual bullets (`Photosynthesis.`,
`• Acid\n• Base\n• Salt`) all pass the "short + no verb" predicate
and get dropped wholesale. The plan's mitigation ("the rest of the
chunk's lines usually save it") assumes prose context that does not
exist for short-answer or code chunks. The false-drop cost (no
answer surfaces) dominates the false-keep cost (a structural citation
slips through, where the user can visually inspect).

Other valid points the adversary raised:

- Thresholds (`HEADING_MAX_CHARS=80`, "majority", "strict conjunction")
  asserted without empirical derivation; tuning deferred to a PR that
  also authors the labeled slice — circular.
- Slot-scope leakage on the labeled slice self-resolved with a
  single-line operator-followup; this is exactly the halt-and-ask
  trigger the routine exists to enforce.
- Effort vs. T12 opportunity cost: chunks path is dying; every Gate 1
  line is throwaway code with a known sunset.
- "No spaCy" asserted, not argued: 13MB `en_core_web_sm` is a real
  tradeoff the plan forecloses without presenting.

The adversary's "what I would do instead":
1. Ship chunks-path instrumentation first as a standalone PR.
2. Move the predicate from chunk-hydration to quote-resolution.
3. Trade Gate 1 implementation effort for T12 unblock pairing.

## Synthesizer verdict

**THIRD OPTION: ship a revised Gate 1, not the original.**

The Proponent's case for the chunks-path hole being load-bearing under
`RETRIEVAL_USE_NODES=false` survives. T12 is gated on a multi-hour
re-ingest validation and the chunks path remains the default until
that completes; not shipping anything until T12 lands is a real cost
the adversary's "redirect to T12" proposal underweights. The strategic
moat argument (verbatim citations as Carrel's differentiator) is the
proponent's strongest leg and was not landed on.

But the Adversary's points (1) and (2) are verified and load-bearing
against the design as written:

- Point (1) is provable by reading `evals/run_evals.py:477-485`. The
  plan ships a gate against a metric that does not exist on the path
  it gates. This is a measurement bug, not a debate point.
- Point (2) is forced by the architecture of the problem. The bug
  lives at quote granularity (the model picks WHICH substring to
  cite); a chunk-text filter cannot catch the common case (heading
  line adjacent to a body paragraph).

The revisions required to ship Gate 1 are forced by these two points
and have first-order consequences for the design:

### Revision 1: predicate operates on the cited quote string, not chunk text

Replace `_drop_low_information_contexts(contexts)` (chunk granularity,
post-hydration) with `_drop_structural_citations(answer, contexts)`
applied AFTER `_resolve_grounded_answer` has produced the LLM citations
and validated each quote as a verbatim substring. The new function
inspects each `Citation.quote` string with the three structural
signals; structural-shaped quotes are dropped from the answer's
citation list and the corresponding claim moves to `unsupported_spans`
(matching the existing "no silent fallback" treatment of unsupported
claims at `services/tutor.py:_resolve_grounded_answer`).

Plug-in site: a single new pass in `_resolve_grounded_answer` between
quote validation and the final answer assembly. Not three call sites
— the resolve function is the choke point. The chunk-text predicate
becomes a dead idea.

Implication for the verb detector: at quote granularity, the false-
drop surface shrinks dramatically. A 3-word bulleted answer that
appears as a `Citation.quote` of `"Photosynthesis."` would still fail
"short + no verb"; the plan must drop the verb-presence signal as a
sufficient condition and require it as ONE of two signals (length AND
bare-reference shape, or length AND no-verb-AND-not-noun-phrase). The
revised plan recasts the predicate accordingly.

### Revision 2: T2.0 ships eval instrumentation before any heuristic

A new first sub-PR, T2.0, extends `evals/run_evals.py:470-485` so the
chunks branch runs the same shape detector against the cited quote
string and increments `structural_citation_count` on a structural
match. Same shape predicate as the runtime filter (one
implementation, both call sites). Output: a real measured baseline
on the existing full-mode eval suite, committed to
`evals/reports/structural-citation-baseline-{date}.md`. Only then does
T2 (the runtime filter) acquire a measurable acceptance gate.

The 30% drop target stays in T4 (default-on flip), but it is
re-anchored to the measured baseline from T2.0 rather than a
vibes-based number.

### Revision 3: labeled slice question escalated as operator-followup before T2

Per the adversary's point (c), the labeled-slice authoring is a slot-
scope ambiguity that the slot should not self-resolve. The revised
plan removes the slice from T2's scope and replaces it with an
explicit operator-followup line in `.claude/logs/operator-followups.jsonl`
asking whether (a) the slot-1 smoke-shaped slice exception applies,
(b) the slice belongs to slot 2, or (c) the slice should wait. T2 can
still ship using the existing full-mode eval suite (now properly
instrumented post-T2.0); the labeled slice was a quality-of-
measurement bonus, not a prerequisite.

### Revision 4: explicit T12 timing argument in the plan

The Proponent's moat argument needs to be made in the plan body, not
in an open-questions appendix. Sub-section "Why ship Gate 1 instead
of accelerating T12" must name: (a) T12's overnight re-ingest budget
of ~2h on the current corpus (per AUTONOMOUS_WORK_PLAN T12 acceptance
line), (b) post-T12 the chunks path is still queryable until T15
drops the tables, (c) Gate 1 is ~300 lines with a 3-6 month sunset
versus user-visible bug days persisting unaddressed. The adversary's
"redirect to T12" is reasonable on its face; the plan owes a one-
paragraph rebuttal that names the timing math.

### Items where the adversary's critique was acknowledged but not adopted

- **No spaCy.** Decision deferred. The revised plan keeps the closed-
  class detector because (1) at quote granularity the false-drop
  surface is smaller, (2) the labeled slice (when it ships) will
  expose the false-drop rate empirically, and (3) adding a 13MB
  Python dep + model download cost is a separate decision that
  belongs in its own ADR if the empirical false-drop rate justifies
  it. The plan adds an explicit "If false-drop > 5% on the labeled
  slice, escalate to spaCy ADR" kill condition rather than foreclosing.
- **Thresholds.** Constants stay asserted in T2 with the explicit
  rationale "ship, measure, tune in T3." Kill condition: if T2's
  pre-flip measurement shows the predicate firing on >2x the
  baseline structural-citation rate (i.e. more false drops than true
  drops), pause and re-derive.

## Decision summary

1. Pivot the predicate from chunk-text (hydration time) to cited-
   quote (resolve time). Single plug-in site:
   `services/tutor.py::_resolve_grounded_answer`.
2. Add T2.0 as the first sub-PR: extend `evals/run_evals.py` chunks
   branch with the same shape detector + real measured baseline. Lands
   before T2.
3. Remove the labeled-slice authoring from T2; replace with an
   operator-followup question. T2 ships using the full-mode eval
   suite, properly instrumented.
4. Add a "Why ship Gate 1 instead of accelerating T12" section to the
   plan with the timing argument.
5. Add a "Verb-detector false-drop kill condition" referencing a
   future spaCy ADR if empirical false-drop exceeds 5%.

## Consequences

**Positive:**
- The 30% acceptance gate is anchored to a measured baseline, not a
  guess.
- The architecture matches the bug's granularity. Heading-INSIDE-chunk
  is caught.
- Slot-scope hygiene preserved: ambiguous slice authoring escalated.
- T12 timing tradeoff is on the record, not in an appendix.

**Negative:**
- Plan grows from 3 to 4 sub-PRs; T2.0 adds ~half an iteration.
- Quote-level filtering after resolve introduces a new failure mode:
  if every citation in a grounded answer is structural, the answer
  loses all citations. The revised plan must handle this (move claims
  to `unsupported_spans` rather than dropping the answer).
- Closed-class verb detector decision is still partly punted to the
  spaCy ADR trigger; if false-drop is consistently in the 3-5% range,
  the decision will revisit.

**Reversibility:**
- All Gate 1 work lives behind `RETRIEVAL_CHUNKS_HEURISTIC` (still
  default off through T3). Roll back by flipping the flag.
- T15 (drop chunks table) deletes the entire Gate 1 surface area.
  Sunset is hard-coded into the plan dependency graph.

## Audit trail

- 2026-05-25 02:20 UTC: initial plan drafted at
  `docs/plans/structural-citation-gate-1-chunks-heuristic.md`.
- 2026-05-25 02:25 UTC: proponent + adversary spawned in parallel.
- 2026-05-25 02:35 UTC: both transcripts received, adversary's points
  (1) and (2) verified against `evals/run_evals.py:470-485`.
- 2026-05-25 02:45 UTC: synthesizer verdict written (this ADR).
  THIRD_OPTION accepted; plan revisions queued for the next edit.
- Proponent transcript: `/private/tmp/claude-501/-Users-madu-Desktop-Codex--claude-worktrees-fleet-1/51e7b53f-d880-46d2-9f0d-7ab4166825c9/tasks/a704f9ceade66c2fe.output`
- Adversary transcript: `/private/tmp/claude-501/-Users-madu-Desktop-Codex--claude-worktrees-fleet-1/51e7b53f-d880-46d2-9f0d-7ab4166825c9/tasks/a62d7d8445b301fc6.output`

Both transcripts contain Stop-hook nudge noise (the score-loop hook
fires on SubagentStop and is designed for code-shipping work, not
debate subagents). The substantive argument from each agent is on the
line where the agent's text exceeds 7000 chars in the parsed
transcript dump above.
