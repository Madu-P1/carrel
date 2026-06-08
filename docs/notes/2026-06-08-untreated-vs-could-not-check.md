# Untreated vs. could-not-check (2026-06-08)

The deterministic verify engine used to route **every** anchor-free sentence (no
citation, no quote, no money / date / duration) to a `could_not_check_reason`,
which became a per-claim card reading "Could not verify." On a normal prose
draft that produced a wall of could-not-verify cards: alert fatigue, the root of
the "everything needs review" complaint.

Decision (office-hours + the `harvey` lawyer agent): anchor-free prose should not
get a per-sentence verdict at all. Two states that were conflated are now split:

- **UNTREATED** — a sentence with NO checkable anchor. Not a finding. It produces
  no claim card and no tray entry; it renders as plain draft text. This is the
  bulk of clean prose. "There was nothing to check here" is not a finding.
- **COULD-NOT-CHECK** — a sentence that HAD a checkable anchor (citation / quote /
  money / date / duration / party / section / defined term) but the check could
  not complete (ambiguous cite, rate-limit, lookup error, no source loaded,
  opinion text missing for a quote). This stays a neutral card. "I started a
  check and couldn't finish it" IS worth surfacing.

## Where it lives

- `services/legal/deterministic_envelope.py` — `build_deterministic_envelope`'s
  per-sentence loop. The `elif not anchors:` branch marks the claim `untreated`
  (no `could_not_check_reason`). The final `else:` (a checkable anchor with no
  source) keeps `could_not_check_reason`. Grounding/clause checks
  (`_contract_claim`) are unchanged: a party/section/defined-term sentence still
  gets its could-not-check, and a contradiction/section-absent still gets a hard
  verdict.
- `services/verify.py` — `_verify_result_from_envelope` skips any claim flagged
  `untreated` (no `VerifyClaimVerdict`), so it never becomes a card or a tray
  entry. The streaming claims loop carries the same guard for symmetry.
- `frontend/.../VerifyView.tsx` + `documentSegments.ts` — the document is
  card-driven, so a sentence with no card already renders as plain text. The only
  UI change: a draft with zero cards renders the draft via `WorkspaceMargin`
  (plain text, no marks, no summary) instead of the old, now-misleading "No
  statements came back from the engine" message.

## Two non-obvious interactions

1. **T1 recall tier (ADR-0012, dark on main).** An untreated anchor-free sentence
   is *promoted* out of untreated into an assessed could-not-check card when the
   T1 gate is honestly open and a local model returns an above-threshold
   assessment (coverage-by-assessment surfaces for the lawyer's review). The
   verdict stays `unknown`; the assessment only rides as assistive provenance.
   With T1 dark this never fires, so an anchor-free sentence stays untreated and
   the envelope is byte-identical to flag-off.
2. **Engine-failure fallback.** `_verify_result_from_envelope` appends a single
   engine-failure card when it produced zero cards — but zero cards is now a
   *successful* outcome for a clean prose draft (every sentence untreated). The
   fallback is gated on `engine_error is not None or not claims`, so a clean
   prose draft yields zero cards while a genuine failure (errored, or no claims
   at all) still gets its card.

## Deliberately deferred

No document-level coverage line ("N of M checkable claims grounded" / "No
checkable claims found here") and no "verified" word or green check at the
document level. That wording is deferred until live-lawyer validation
(mid-June–July 2026 interviews). This change is only the engine/UI split so a
clean prose draft stops screaming.
