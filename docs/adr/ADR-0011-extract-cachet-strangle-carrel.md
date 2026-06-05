# ADR-0011: Extract Cachet by Strangling Carrel In Place

- Status: Accepted
- Date: 2026-06-05
- References:
  [ADR-0008](ADR-0008-v2-pivot-validation-first-sequencing.md) (the V2
  pivot to an independent verification layer),
  [ADR-0010](ADR-0010-build-verify-port-ahead-of-validation.md) (verify-port
  build sequenced ahead of the validation gate),
  [ADR-0003](ADR-0003-versioned-migrations.md) (migrations are the schema
  source of truth),
  [ADR-0009](ADR-0009-fail-loud-on-high-stakes-flows.md) (fail loud, no silent
  degradation on high-stakes flows),
  `docs/plans/cachet-verify-port-2026-05-29.md` (the verify surface this
  extraction inherits),
  `docs/notes/2026-04-29-carrel-rename.md` (the deferred einstein/carrel rename
  list, executed in P5 of this plan),
  `docs/plans/cachet-extraction-2026-06-05.md` (the executable P0-P5 plan this
  ADR governs).
- Decision owner: operator. Carrel-the-product-is-dead premise confirmed by
  operator 2026-06-05.

## Context

ADR-0008 repositioned this codebase from a study tutor (Carrel) to an
independent AI verification layer (Cachet). The operator has now confirmed the
terminal state of that pivot: **Carrel-the-study-app is dead. Cachet is the sole
future product.** There is exactly one consumer of this codebase going forward.

Cachet is not a separable sidecar. A file-level coupling map of the repository
shows Cachet's verification ability is built directly on Carrel's spine:

- `routes/verify.py` and `routes/briefs.py` are wired into the single
  `main.py` FastAPI app alongside ~20 study/learning routes.
- `services/verify.py` produces per-claim verdicts by calling
  `services.tutor.grounded_tutor_envelope` (line 251) and
  `grounded_tutor_envelope_steps` (line 610). That grounding engine is shared
  by both Ask and Verify. It is what Cachet is *made of*, not baggage.
- The Cachet-exclusive deterministic engine (`services/legal/quote_check.py`,
  `align.py`, `case_verification.py`, `courtlistener.py`) is cleanly isolated
  and hardened over four adversarial review rounds (demo_ready, 2026-06-05).
- `migrations/` is monolithic: `0001_initial.sql` creates study tables
  (`srs_cards`, `concepts`, `dialogue_sessions`) in the same schema as the
  document/chunk/node tables verify depends on; `briefs` (`0024`) is a
  standalone table with no foreign keys.
- The frontend is one Vite bundle with one `AppShell`; `verify` and `shelf`
  are clean feature directories but ship inside the full study app.
- The macOS WKWebView host bakes the local-API token gate and CORS allowlist
  into `main.py`. That trust boundary is correct and cannot be stripped.

Per-layer entanglement: backend routes TIGHT, backend services MEDIUM (verify
rides the shared grounding engine; the legal engine is clean), frontend
LOOSE-to-MEDIUM, data MEDIUM (briefs standalone, but verify needs an ingested
`chunks`/`nodes` corpus), host TIGHT.

The operator asked how to permanently separate Cachet from Carrel while
preserving, or improving, the hardened verification abilities, without a
big-bang rewrite. This ADR records the decision; the cited plan records the
steps. The analysis was run through the `vulcan` engineering-judgment skill
(rewrite-vs-extract, deep-modules, branch-by-abstraction, reversibility,
DRY-of-knowledge).

## Decision

**Strangle Carrel in place. Do not extract Cachet into a fresh repository. Do
not rewrite. Do not extract a shared substrate library.**

Concretely:

1. **Keep this repository as Cachet's home.** The substrate Cachet is built on
   (grounding engine, retrieval, ingestion, AI router, db, local-API security)
   stays where it is, inline.
2. **Introduce one seam.** A narrow `grounding` interface
   (`ground(draft, sources) -> GroundingEnvelope`, plus the streamed variant)
   that `services/verify.py` calls instead of reaching into `services/tutor.py`
   internals. `grounded_tutor_envelope` becomes the implementation behind it.
   This is the only new design work.
3. **Delete the study app around the substrate**, leaf-first, one coherent
   slice per PR, verify-green after each: study/SRS, calendar/coach,
   concepts/dialogue, reader/library/ask, dashboard/onboarding/exports/studio/
   synthesis/evidence, their frontend feature directories, and their tables.
4. **Collapse the schema** with a new forward migration that drops the
   now-unused study tables (never rewrite `0001`).
5. **Cut the identity** last: execute the deferred einstein/carrel rename, make
   Cachet the default app, drop any `CACHET_ONLY` flag.

The full sequence, with per-phase characterization-test gates and rollback
gates, is `docs/plans/cachet-extraction-2026-06-05.md` (phases P0-P5).

**The two one-way doors are P4 (drop study tables, data-destructive on dead
tables) and P5 (rename + identity cut).** Everything in P0-P3 is a two-way door
and ships behind nothing irreversible. P4 and P5 do not begin until P0-P3 have
proven a standalone Cachet runs green.

## Why This Path

- **Rewrite-vs-extract: extract wins on the conditions present.** A fresh-repo
  port would re-implement a verification engine hardened over four adversarial
  rounds (CourtListener status handling, quote-validation edge cases,
  deterministic extraction, the stream-not-engine lesson). Re-porting it runs
  blind for weeks with no shipped value and silently loses embedded knowledge.
  The rewrite condition (the architecture genuinely cannot express the
  requirement) is not met: the architecture already runs Cachet.
- **The strangler reaches the identical clean-room end state without the risk.**
  After P3-P5 the repository is a purpose-built, verification-first Cachet with
  no study cruft, the same destination a fresh repo promised, reached
  incrementally and reversibly. Strangle-in-place therefore strictly dominates
  fresh-repo-plus-port here.
- **One consumer, so no shared library.** With Carrel dead there is a single
  consumer of the substrate. Extracting retrieval/ingestion/grounding into a
  published package "in case Carrel needs it" is speculative generality and the
  wrong abstraction. Keep it inline.
- **The counter-argument is real but loses.** "Build a clean Cachet repo, no
  legacy einstein/carrel identifiers, a verification-first schema, easier to
  audit and pitch" is genuinely attractive. It loses because every benefit it
  names is delivered by P3-P5 (delete baggage, collapse schema, rename) without
  the re-port risk. The only thing the fresh repo buys over the strangler is a
  psychological clean break, which does not justify re-porting a hardened
  engine blind.
- **Reversibility is honored.** Deliberation is spent only on the two one-way
  doors (P4, P5). The bulk of the work (P0-P3) is cheap to reverse and moves
  fast.

## Consequences

- **Preserved by construction:** the legal engine is never touched; the
  grounding engine is kept behind the seam, not rewritten; characterization
  tests pin verify's observable behavior through every deletion.
- **Improved:** with Ask/study gone, the grounding engine can be specialized
  for verification (drop prose-synthesis paths verify never uses), CI shrinks to
  what Cachet ships, the OpenAPI surface and `types.gen.ts` collapse to
  verify+briefs, and the seam lets the holding-match provider move from
  Claude-gated to local (AFM) later without touching the verify surface. The
  no-silent-fallback `ClaudeCallResult` provenance (ADR-0009) is carried through
  the seam unchanged.
- **The macOS host trust boundary stays.** The local-API token gate and CORS
  are factored into a small middleware the Cachet app composes; they are not
  removed.
- **History is preserved.** `migrations/0001` is not rewritten; the study
  tables are dropped by a new forward migration after P3 orphans them.

## Non-Goals

- **A fresh Cachet repository.** Explicitly rejected above.
- **A shared substrate package.** Explicitly rejected above.
- **Rewriting the grounding engine.** It is kept behind the seam and specialized
  opportunistically, never rewritten wholesale.
- **Touching the legal engine or the deterministic verify core during the
  move.** The extraction moves around them, not through them.
- **Building Electron now.** The loopback-served frontend
  (`cachet-localhost-browser-delivery`) is the working simple system. Electron
  waits for a real packaging requirement.
- **Rewriting `migrations/0001`.** Drop-by-forward-migration only.

## Open Questions

- **Per-route keep/delete confirmation.** A few backend routes are judgment
  calls because verify needs an ingested corpus: `routes/documents.py` and
  `services/ingestion/*` are KEEP (verify needs a source pool); `routes/search.py`
  and `routes/ask_cards.py` are likely DELETE. The plan resolves each by a
  grep-for-inbound-imports gate per slice rather than guessing up front.
- **`tutor_exchanges` table fate.** Determine in P3 whether the verify path
  reads it; if not, it joins the P4 drop set.
- **Whether to wire P0-P5 into `AUTONOMOUS_WORK_PLAN.md` / `TODOS.md`** as
  tracked tasks, or run them as an operator-led sequence. Deferred to operator.
- **Branch reconciliation.** The standalone Cachet frontend (Option A) and
  `serve-cachet.py` were built on another branch and are not on trunk; P2 brings
  them onto the line of development this plan runs on.
