
## Mythos review — D-track + L1 (base cf355e603, run 2026-07-05)

Source: mythos run over the draft-upload (D1-D3) + long-doc (L1) work. 8 surfaced, 1 suppressed (refuted). REFUTER LEG DEGRADED: 7/9 LLM refuters died on a session limit; those candidates were verified DETERMINISTICALLY (measurement/grep/read) rather than fail-safe-suppressed, so the ledger is an honest degraded run, not a clean pass. Ledger: .mythos/findings-mythos-D-track_L1-session.md

### [REVIEW] c4-attest-draft-unbounded-fanout (high security) - cachet_verify/adapter.py
- Status: todo
- Deps: none
- Source: mythos D-track+L1
- Grounding: cite:cachet_verify/adapter.py:643+CWE-400. attest_draft removed the whole-draft _too_large(len(sentences), sentence_count) bound; verify_claim only self-bounds per-claim at ~4000 candidates. A crafted in-caps /api/attest (draft ~2500 sentences x source ~3999 digit-bearing sentences, each just under the per-claim refusal) drives ~2500x3999 ~= 10M sentence-pair comparisons with no aggregate ceiling, wedging the sync worker for minutes-to-hours; the old product bound refused instantly. Confirmed by two independent finders.
- Goal: Restore a deterministic AGGREGATE ceiling (sum of per-claim candidate work, or a draft-sentence-count cap) so a crafted in-caps request refuses honestly; confirm no caller depends on the single-claim oversize shape.

### [REVIEW] c1-specimen-keeps-provenance (high correctness) - frontend/src/cachet/LecternView.tsx
- Status: todo
- Deps: none
- Source: mythos D-track+L1
- Grounding: repro: upload a document (doc mode, caption names file+sha256), then ?K > 'Load the specimen draft' -> loadSpecimen sets liveDraft.value = SPECIMEN_DRAFT but never clears liveDraftProvenance; the sheet shows specimen text while provenance still names the uploaded file; verify passes draftProvenance and the certificate/exhibit attach the uploaded file's sha256+extractor to text that never came from that file. cite:frontend/src/cachet/LecternView.tsx:143+provenance-drop-honesty-rule
- Goal: loadSpecimen must set liveDraftProvenance.value = null (the specimen text is not the extracted file's bytes), like onDraftInput does.

### [AUTO] c7-l1-no-differential-test (high test-coverage) - tests/test_kernel_candidate_index.py
- Status: todo
- Deps: none
- Source: mythos D-track+L1
- Grounding: cite:tests/test_kernel_candidate_index.py:22+untested-behavior. Byte-identical-verdict equivalence (the whole L1 safety case) is asserted in the docstring but locked only by (a) fixture suites that run the indexed path ALONE (no brute-force reference remains to diverge from) and (b) a superset property whose oracle (_effective_ids) is re-derived, not the real old scan; a future leg reading candidate_ids without the oracle modelling it would pass superset while verdicts drift.
- Goal: Add a randomized DIFFERENTIAL test: run verify_claim on the indexed path vs a brute-force full-scan reference (iterate index.sentences) over the same random corpora and assert identical (state, detail).

### [REVIEW] c2-doc-refusal-raw-http (medium correctness) - frontend/src/cachet/LecternView.tsx
- Status: todo
- Deps: none
- Source: mythos D-track+L1
- Grounding: repro: upload an unreadable/scanned PDF; extractDraft rejects with ApiError whose .message is 'API 422 Unprocessable Entity' while the honesty-law detail is in e.body.detail; loadDocument's catch reads e.message, so the user sees the raw HTTP line, not the backend refusal copy. apiErrorMessage() exists for exactly this. cite:frontend/src/cachet/LecternView.tsx:174+apiErrorMessage-convention
- Goal: Route the caught error through apiErrorMessage(e, fallback) so the backend detail (not the HTTP status line) is shown.

### [AUTO] c6-extract-draft-zero-egress-uncovered (medium test-coverage) - routes/verify.py
- Status: todo
- Deps: none
- Source: mythos D-track+L1
- Grounding: cite:routes/verify.py:135+untested-zero-egress. /api/verify/extract-draft calls extraction_pipeline.extract_asset in the zero-egress-critical path, but tests/test_zero_egress.py wraps only build_deterministic_envelope and verify_draft_stream in _forbid_sockets; extract_asset is never exercised under the socket ban. The endpoint's docstring names OCR backends (pdf:docling-rapidocr) that could lazy-download models and egress on first use with no test catching it.
- Goal: Extend test_zero_egress to run extract_asset on a fixture under _forbid_sockets so the document-draft surface is proven offline-by-construction.

### [AUTO] c8-self-verification-trap-happy-path-only (medium test-coverage) - tests/test_verify_extract_draft.py
- Status: todo
- Deps: none
- Source: mythos D-track+L1
- Grounding: cite:tests/test_verify_extract_draft.py:131+untested-behavior. The 'persists nothing / never enters the retrieval corpus' invariant (the structural false-green guard) is asserted only on the 200 path; the empty/unsupported/extraction-failure paths ? where an early save-before-validate is the most likely leak ? assert only the status code, not _document_count()==0 and an unchanged upload dir.
- Goal: In the refusal/failure tests, also assert _document_count()==0 and the upload dir is unchanged.

### [AUTO] c9-standalone-provenance-grep-not-render (low test-coverage) - frontend/src/features/attest/verifierStandalone.test.ts
- Status: todo
- Deps: none
- Source: mythos D-track+L1
- Grounding: cite:frontend/src/features/attest/verifierStandalone.test.ts:150+vacuous-assertion. The standalone verifier's 'additive render, present-only' provenance line is verified by grepping the page's inlined source for 'cert.draft_file_sha256'/'cert.draft_extractor' (proving only that the code mentions the fields, not that it renders them present-only). The fingerprint assertion is the real lock; the render claim is a source-grep, not an output assertion.
- Goal: Render the page with a doc-provenance cert and a plain cert and assert the 'Draft file' line appears for the former and is absent for the latter.

### [REVIEW] c3-certmodel-memo-thrash (low perf) - frontend/src/features/verify/VerifyResults.tsx
- Status: todo
- Deps: none
- Source: mythos D-track+L1
- Grounding: cite:frontend/src/features/verify/VerifyResults.tsx:559+unstable-memo-dep. LecternView passes draftProvenance as a fresh object literal every render; the certModel useMemo dep now includes it, so buildCertification (incl. the draft SHA-256) recomputes on every engine-signal tick in document mode, defeating the documented streaming optimization. Pasted-text drafts (stable undefined) unaffected.
- Goal: Stabilize the object (useMemo the {fileSha256,extractor} in LecternView on the two primitives, or destructure the two primitives into the dep array).
