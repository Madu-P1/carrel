# Cachet source-viewer (reader recycled for verification) — queued design

Date: 2026-06-07. Status: QUEUED (build later). Operator decision: yes, integrate; do
NOT delete the recyclable reader code during the P3 strangle.

## The ask

In Cachet, let the user open a saved brief and view its **sources** at the exact
verified span, like the Carrel reader, but with Cachet's philosophy: a proof viewer,
not a study reader.

## What already exists (grounded in code, main 3ad7dc69b)

- **Briefs viewing ~ done.** `ShelfView` opens a saved brief via
  `navigateTo('/verify?brief=<id>')`; `CachetApp` re-hydrates it as
  `<VerifyView briefId={brief}>`. The Shelf is the brief viewer.
- **Source viewing half-built + severed.** `frontend/src/features/verify/SourceInspector.tsx`
  resolves each citation to its exact span via `evidence.resolve()` (Cachet infra),
  shows the verbatim quote + page/section, and has `openInReader()` ->
  `/reader/<doc>?node=<node>`. But `CachetApp` only routes `/verify` and `/shelf`, so
  that link dead-ends in the Cachet shell.

## Decision: reuse the deep parts, rebuild a thin shell

Do NOT port `features/reader/ReaderView.tsx` — it is study-shaped (imports
`CardCreateDialog`, study `events`, `useCardFlight`/`useCitationFlight`, study-AppShell
panel toggles). Porting it drags the study deps we are deleting back into Cachet.

| Reuse (deep, study-free — KEEP, do not delete) | Rebuild thin (Cachet `SourceView`) |
|---|---|
| `routes/reader_nodes.py` (`/api/reader/node/{id}` -> page + char offsets + verbatim_text + heading_path) | Opens AT the cited node, not page 1 |
| `evidence.resolve` (already Cachet) | Read-only: no notes/cards/concepts/outline-as-study |
| `PdfViewer` / `usePdfDocument` / `useNodeDeepLink` (render + span-landing primitives) | Highlights only the verbatim run the engine validated |
| `documents` fetch | Honest could-not-check when resolve fails (mirrors the 3-state tray) |

## Cachet philosophy applied

- A proof viewer, not a reading app: a verdict sends you there; it opens on the span.
- Honest highlight: ink underline = validated verbatim; oxblood = contradiction span;
  visible "could not locate this span" instead of a fabricated highlight.
- No generation, ever (P6 holds). Paper/ink/Caslon, the verify aesthetic.

## Counter-argument (bounds the scope, does not kill it)

"Don't build a reader — Cachet's edge is the cold record + refusal; a viewer pulls it
back toward a research workspace." Resolution: inspection that ESCALATES on demand.
- Tier 1 (exists): `SourceInspector` inline span. Usually enough.
- Tier 2 (this work, minimal): "open in source" -> land on the span in its surrounding
  clause/paragraph, read-only. Reuses reader_nodes + render primitives.
- NOT: notes, cards, concept-linking, "continue reading."

## P3 extraction impact (load-bearing)

- `reader_nodes` flips from delete-candidate to **KEEP**.
- `evidence` + `documents` stay **KEEP** (already).
- `features/reader/ReaderView.tsx` may still die in the wholesale frontend slice, but
  **extract `PdfViewer`/`useNodeDeepLink`/`usePdfDocument` to a neutral home FIRST**, or
  the deletion removes the parts meant for recycling.

## Minimal first slice (when built)

1. Add a `/source` (or `/reader`) route to `CachetApp` rendering a new `SourceView` so
   `SourceInspector.openInReader()` stops dead-ending.
2. `SourceView` reuses `reader_nodes` + `useNodeDeepLink` + `PdfViewer`; strip every
   study import; honest highlight only.
3. (Done in this note) reclassify `reader_nodes` KEEP in the extraction plan/memory.
