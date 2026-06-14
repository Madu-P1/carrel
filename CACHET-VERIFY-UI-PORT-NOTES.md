# Verify-UI capabilities to port into the vault UI

Written 2026-06-08. Context: a demo was stood up on the WRONG UI (the plain
Cachet shell built off `main`: Verify + Shelf, no vault). That setup was torn
down. The PROPER demo UI is THIS branch (`claude/zealous-taussig-60b96a`, the
vault UI). These are the things the wrong UI's Verify surface does that this
vault UI's `VerifyResults`/`useVerify` does NOT do yet, and likely needs before
the demo. None of this is lost work; it all lives on `main` and just needs
porting into the new structure.

## Verify behaviors present on main, MISSING in this vault UI

1. **Untreated vs could-not-check taxonomy (#155).** An anchor-free sentence
   renders as PLAIN draft text (no card, no tray entry), distinct from
   could-not-check. This vault UI's `VerifyResults` has the old
   could-not-check-only handling (`untreated` count = 0), which produced the
   "everything needs review" alert fatigue on clean prose.
   - Verified live on the wrong UI: the sentence "The parties shall use best
     efforts to cooperate in good faith." rendered as plain text, no mark.
   - Source of truth: `main` `frontend/src/features/verify/VerifyView.tsx` +
     `docs/notes/2026-06-08-untreated-vs-could-not-check.md`.

2. **Neutral headline (#154).** `verdictSummaryHeadline` folds could-not-check
   OUT of the oxblood "needs review" alarm; only a real flag (citation-not-found
   / unsupported) turns the headline to the problem color.
   - Verified live: summary read "1 of 2 statements need your review" with
     CITATIONS NOT FOUND 1 / SUPPORTED 1 (the untreated sentence is not counted).
   - This vault UI's `VerifyResults` does not carry it (and the test for it was
     dropped from `VerifyView.test.tsx` during the merge; re-add with the logic).

3. **Source overlay (#158).** `SourceInspector` "open in source" overlay (the
   in-place cited-passage viewer). Present on main, orphaned/absent here. Decide
   whether it belongs in the standalone vault structure; if yes, wire it into
   `VerifyResults` and raise the bundle budget 126 -> 128 in
   `frontend/tests/bundle-size.test.ts`.

4. **empty-ok case batch -> unknown, not unsupported (#156).** Backend only
   (`services/verify.py`), already on `main`, so this vault UI inherits it via
   the backend. No frontend port needed.

## Defects found on the wrong UI to AVOID/fix in the vault UI

- **Green provenance pill.** "DETERMINISTIC . ON DEVICE" renders GREEN
  (confirmed computed style: `oklch(0.34 0.14 155)`, `--color-success` =
  `oklch(.48 .14 155)`, hue 155 = green). Brand requires ink, not green. The fix
  ("rebind `--color-success` to ink in `.shell`") is on the unmerged
  `upbeat-chebyshev` branch among 5 visual-QA fixes.
- **Tab `<title>` says "Einstein"**, not "Cachet". Also fixed on
  `upbeat-chebyshev`.

## Demo facts that carry over (verified deterministic + offline)

- Real cites that RESOLVE from the bundled corpus: `347 U.S. 483` (Brown),
  `576 U.S. 644`, `410 U.S. 113`. Any other "real" cite reads not-found.
- Litigator cite-check needs no embedder (no cold-cache risk). Contract wedge
  needs the offline embedder cached.
- Serve path that injects the token + forces deterministic/offline:
  `script/serve-cachet.py` (port 8000). Build with `vite build --mode cachet`.
  Engine + `/api/verify` + the three states verified correct on `main`.
