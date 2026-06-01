# Plan: Cachet — verify-as-hero, Build Slice 1

- **Date:** 2026-05-29
- **Status:** DRAFT. Blocked on one founder approval (see "Design gate" below) before PR 3 starts; PRs 1, 2, 4 can begin on go.
- **Input:** 16-persona cross-professional discovery brief (`docs/notes/2026-05-29-cachet-cross-professional-discovery.md`) + the anchor litigator interview. Weight the one real anchor above the synthetic 11; treat stated willingness-to-pay as near-zero signal until a real card is behind it.
- **Strategic frame:** ADR-0008 validation-first. This slice IS T65 prep: it is the surface litigators (and the T66 recruits) actually touch. It re-points an engine that already exists into a trust-grade form. It is NOT a new engine and NOT a whole-app rebrand.

## Goal

Turn the existing Carrel V2 verification path into a macOS "verify as hero" experience for the litigation pre-flight wedge, built to a bar a skeptical senior professional trusts on sight, with the refusal as the headline and a defensible certification artifact as the paid object.

## Non-negotiables (hard product constraints, every PR, no exceptions)

1. **No generation.** The tool never writes argument, never drafts a corrected citation, never fills a gap. Red pen, never the pen.
2. **No confidence percentages anywhere,** in any slice. Discrete states only. (Note: `api_models.py` carries internal `confidence` floats; they must never render as a number on the verify surface.)
3. **The refusal is first-class and loud.** "Cannot verify, not in the record" is a full-weight state, never a grayed-out error. The "could not confirm" set is the headline of every output and the exported artifact.
4. **Honest scope boundary.** The tool attests to grounding ("this matches the source you gave me"), never to truth, never to soundness of reasoning.
5. **Asymmetric tuning toward over-flagging,** stated in the UI. A dismissed false-positive costs two seconds; a false-negative costs a career and the product.

## Substrate (reuse, do not rebuild)

- `routes/verify.py` (`/api/verify`), `frontend/src/features/verify/VerifyView.tsx` (361 LOC) + `VerifyView.module.css`
- `services/tutor.py`: verbatim-quote validator + auto-correct; `unsupported_spans` (currently a side-output, promote it)
- `services/legal/case_verification.py` + CourtListener case-existence (exists / ambiguous / not-found / malformed)
- holding-match verifier (supports / ambiguous / contradicts / unavailable)
- `api_models.py`: `VerifyResponse`, `VerifyClaimVerdictItem` (verified / unsupported / unknown), `CaseVerdictItem`, `Citation.node_type`
- T64 fail-loud provider gate (ADR-0009) is the refusal posture already enforced at the engine layer

## Design gate (REQUIRES FOUNDER APPROVAL: this is a DESIGN.md deviation)

CLAUDE.md forbids deviating from `DESIGN.md` without explicit approval. PR 3 proposes a scoped
`verify` token layer that departs from the documented dark, consumer-study, green/amber/red system:

- warm paper-white surface, near-black ink, a single grave accent (proofreader's oxblood, not stoplight red), serif body, mono/tabular numerals for citations and figures
- kill the green checkmark and any pass-rate hero; "supported" becomes the neutral, unmarked default
- chromatic energy reserved only for flags and for the "could not confirm" state
- motion stripped to two sanctioned uses: an honest working-indicator and scroll-to-source
- scoped to the verify route ONLY via workflow isolation (enter/live/exit verification as a self-contained, full-bleed environment). Existing tokens unchanged, so the study surface and the full verify chain stay green. Whole-app rebrand deferred to post-T66.

Founder decision required: approve this scoped deviation, or hold PR 3 and keep the current visual system on the verify surface.

## Slice 1: four PRs (test-gated, additive, independently shippable)

### PR 1 — Four-verdict claim list, refusal as headline
Decompose a submitted document into discrete claims, each with its attached citation. Render four verdicts: supported, quote-mismatch, supports-mismatch (real source, wrong proposition), could-not-confirm. Split could-not-confirm into "checked, found no support" vs "could not check, no source loaded." Promote `unsupported_spans` from side-output to the top of the surface.
- Tests: claim-decomposition unit tests; verdict-mapping tests including both could-not-confirm sub-states; a test asserting no code path renders a confidence number; VerifyView render test for the refusal-as-headline ordering.
- This is the spine and the credibility engine. Nothing else ships before it.

### PR 2 — One-click-to-source span, side by side
Click any flagged claim to land on the exact source span (PDF page region for the litigation corpus to start), claim on the left, source on the right, nothing resembling a score between them.
- Tests: span-resolution tests (claim -> source region); navigation/flight test; render test for the side-by-side layout.
- Co-equal in importance with PR 1; ordered second only because it depends on PR 1's claim objects.

### PR 3 — Scoped `verify` visual mode (the design-gate PR)
Implement the scoped `verify` token layer and re-render the verdict states per "Design gate" above. Sealed, document-grade, full-bleed verify environment. Folds in the paused T59 (VerifyView render tests) and T60 (typed boundary normalizer replacing the `as unknown as CitationRecord[]` cast), now re-aimed by this discovery.
- Tests: token-layer scoping test (study surface unaffected); verdict-state render tests for all four states + the refusal; reduced-motion test; the T60 normalizer tests.

### PR 4 — Exportable certification artifact (honest skeleton)
A dated PDF: document-version fingerprint, the source set checked with provenance and date per source, monospaced citations, and a headline section that is what could NOT be confirmed. Plain and defensible, not yet court-exhibit-polished.
- Tests: artifact-generation test (fields present, fingerprint stable for identical input, changes when the document changes); test asserting the not-confirmed section is present and prominent even when empty-of-greens; no-confidence-number assertion.
- The saleable object. Minimal in this slice but it must exist; willingness-to-pay concentrates on defensibility, not convenience.

## Out of scope (sequenced for after the T66 verdict)

Numeric reconciliation (the second engine), currency/over-inclusion reason taxonomies, non-text (audio/table) spans, court-exhibit-grade PDF polish, and any non-litigation corpus connector (tax is the Stage 2 first swap, not part of this slice).

## Adjacent track (flag, not in this slice)

Plaintext-secrets-at-rest -> macOS Keychain (currently deferred in CLAUDE.md for calendar URLs). A procurement-killer for any buyer past the solo practitioner; should land before T66 puts the tool in front of anyone with a compliance function. Its own task, not folded into the verify slice.

## Verify chain

Every PR lands green on the full chain in CLAUDE.md ("Verify chain (run before any merge)"): api-types regen, frontend typecheck + lint + test + build:macos, ruff check + format, the Python unittest battery, build_and_run --verify, phase0 benchmark no-regression, watchdog kill test, swift test.

## Validation linkage

This slice is the T66 demo surface. Recruits beyond litigators: tax attorneys (2-3, priority), a solo or small-firm auditor (1-2, to document the numeric-reconciliation gap with a real human), an investigative journalist (1). Exclude CISOs, regulatory affairs, hospital clinicians (procurement-gated or Stage 3).
