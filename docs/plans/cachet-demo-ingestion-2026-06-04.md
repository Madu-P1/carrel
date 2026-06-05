# Cachet demo: source-upload UI + ingestion hardening (2026-06-04, overnight autonomous)

Operator asleep; full decision authority delegated. Goal: by morning the investor-demo
path is bulletproof — upload a Word doc (or PDF) as the **source** in the UI, verify a
**brief** against it, the catch fires fast and on-device. Ingestion impeccable for DOCX
(primary — investor will bring a Word doc), PDF brought to parity.

## Baseline (measured this session)
- DOCX upload -> verify: works, verbatim, ~30s. Already demo-ready.
- PDF upload -> verify: works, verbatim, but ~2.5 min when the OCR fallback
  (`services/extraction/parsers/pdf.py::_looks_like_scanned_pdf`) false-triggers RapidOCR
  on a thin-text PDF (my cupsfilter test file). Digital (Word->PDF) should stay on the fast
  PDFKit-bridge path. Speed is the gap, not accuracy.
- httpx crash in run-cachet.sh: FIXED (worktree .venv fallback to main checkout .venv).
- Demo path works at the API level; the UI has no upload affordance (Sources is an empty state).

## Plan (highest value first)
1. **UI upload affordance (demo-blocking).** Shared `loadedSource` signal + `uploadSource()`;
   upload UI in SourcesView; lectern shows the loaded source; VerifyView takes source
   `docIds` via a prop (Carrel stays default), replacing the `?doc=` hack.
   Success: live UI — pick a DOCX -> ingests -> source shows loaded -> paste brief -> verify -> catch.
2. **DOCX bulletproofing.** Stress-test parser vs tables / curly quotes / headers-footers /
   lists / hyphenation / multi-paragraph quotes / section signs. Fix any verbatim breakers.
   Success: a DOCX edge-case suite all preserve verbatim.
3. **PDF parity.** Fix the `_looks_like_scanned_pdf` false-trigger so digital PDFs stay fast;
   confirm a real Word->PDF ingests in seconds + verbatim; keep genuine-scanned OCR working
   (with progress, not a silent hang).
   Success: digital PDF fast + verbatim; OCR only on truly image-only PDFs.

## Decisions made (autonomous)
- VerifyView stays host-agnostic: source docIds passed as a prop from the Cachet shell, not
  by importing a cachet store into the shared component. (Same pattern as onResolve/headerTitle.)
- Upload field subject_name = "Sources".
- No status polling: /api/documents/upload is synchronous (returns status "ready").

## BIGGEST WIN (unplanned, demo-critical): verify 61s -> 0.3s
With a source loaded, retrieval found it (hit_count 8) so the pipeline ran the local
LLM grounding (llama3.1:8b) which TIMED OUT at 60s, and the instant deterministic catch
was bundled behind it. Root cause: `OllamaClient` had no `kind` attribute, so the T64
high-stakes gate (`tutor.py:1637`, `getattr(router, "kind", "claude")`) defaulted it to
"claude" and FAILED OPEN -> ran the withheld-anyway LLM for a full minute.
Fix: `ai/ollama.py` OllamaClient now declares `kind = "ollama"` (AFMClient already had
`kind="afm"`). Gate fires -> grounding withheld -> verify returns in **0.3s** with the
catch (measured: `error=provider_below_quality_bar`, 2 flagged + 2 clean).
Plus `VerifyView.tsx` render fix: show the catch (QuotePanel) even when the provider is
gated, instead of the gate banner taking over the whole surface.

## Log
- [x] WS1 source.ts (loadedSource signal + uploadSource + clearSource)
- [x] WS1 SourcesView dropzone upload UI (+ cachet.module.css)
- [x] WS1 VerifyView docIds prop (replaced the ?doc hack)
- [x] WS1 CachetApp wires loadedSource -> VerifyView docIds
- [x] WS1 verified live: Sources UI renders, loaded-state renders, loaded source scopes
      verify (catch fires). Screenshots taken.
- [x] CRITICAL no-cloud verify speed fix (OllamaClient kind) + render fix. typecheck+ruff clean.
- [x] python regression check: 129 tests green (ai_router, tutor_grounded, verify, verify_stream,
      tutor_provider_fallback, ai_providers, ai_provider_parity). No regression from the gate change.
- [x] Presentation polish DONE: suppressed the synthetic engine-error card when the quote check
      produced findings (`services/verify.py:349` -> `if not verdicts and not quote_results`).
      Verified: claim_verdicts=0, catch=2, the calm withheld note shows, no "COULD NOT VERIFY".
      34 verify tests green. Clean demo screen screenshotted.
- [x] WS1 lectern inline "add the record" upload + loaded-source indicator. The lectern now
      has a quiet centered pill under the sheet: "Add the record to check against — a contract,
      PDF, or Word file" calls `uploadSource`; once loaded it shows a dot + filename + "loaded as
      the record" + a "change" affordance (clearSource). Same paper/ink language as the Sources
      tab; the loaded source flows into verify via the existing docIds wiring. A user can now
      attach the source right where they paste the draft, not only via the Sources tab.
- [x] Shelf widened + design fixed. It rendered as a thin ~50rem warm band stranded in the wide
      standalone-app canvas. Now the warm cream GROUND fills the canvas edge-to-edge (matching the
      component's own "warm cream ground" design note) with the briefs held in a steady ~60rem
      reading column via a padding-inline max() trick — robust at 1440 and 1920, rows never
      overstretch. CSS-only, cachet-scoped (ShelfView is cachet-only), host-safe. 135 vitest green.
- [x] Sources became a real library + the Vault filing (fixes "when I upload I can't see it" +
      "let me choose the file it goes in"). SourcesView now fetches `documents.list()` and renders
      every ingested record, grouped by PROJECT (the engine's existing `subject_name`), with the
      active "record to verify against" highlighted and a per-record "Use as record". Upload gained
      a "File into [project ▾ / ＋ New project…]" picker (defaults to Sources so the demo stays
      one-click); each record has a light project select to re-file via `documents.setSubject`.
      All on existing CACHET_ONLY endpoints — no backend work. Widened to 56rem so filenames are
      readable (the 64ch plainView truncated them). Verified: 5 new vitest + visual at 1440/1920
      via a scoped `?fixture=sources` flag (reads need the local token, so the dev preview can't
      hit the real backend without leaking it — fixture is the token-safe visual path).
- [ ] MINOR polish left: the OLLAMA provenance badge shows on a withheld (gated) result; the catch is
      deterministic so it should not imply Ollama produced it. Hide the badge when error=provider_below_quality_bar.
- [ ] WS2 DOCX edge-case harness + fixes (tables, curly quotes, headers/footers, lists, multi-para quotes)
- [ ] WS3 PDF OCR-trigger fix (`_looks_like_scanned_pdf`) + Word->PDF fast-path proof

## Files changed this run
- script/run-cachet.sh (httpx/venv fix, earlier)
- script/run-cachet-app.sh (new — build + launch the native Cachet.app, earlier this session)
- frontend/src/cachet/source.ts (loadedSource + records list/projects model: sourceDocs,
  refreshSources, uploadSource(project), setDocumentProject, setActiveRecord)
- frontend/src/cachet/SourcesView.tsx (rebuilt: grouped records library + project filing)
- frontend/src/cachet/SourcesView.test.tsx (new — 5 tests: empty/list/use/re-file/new-project)
- frontend/src/cachet/LecternView.tsx (inline "add the record" upload + loaded indicator)
- frontend/src/cachet/cachet.module.css (dropzone + lectern pill + Sources library styles)
- frontend/src/features/shelf/ShelfView.module.css (full-bleed warm ground + reading column)
- frontend/src/features/verify/VerifyView.tsx (docIds prop, render fix)
- frontend/src/cachet/CachetApp.tsx (wire loadedSource)
- ai/ollama.py (kind="ollama" — the gate fix)
- services/verify.py (loaded-doc source pool — earlier this session)
