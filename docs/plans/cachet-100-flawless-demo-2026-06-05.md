# Cachet 100/100 flawless sequenced-demo plan

Date: 2026-06-05
Goal: ship one coherent macOS app that runs the flawless sequenced Cachet demo (litigator citation
catch + refuse as the offline sub-second opener, then in-house contract-claim verification as the
business close) for validation lawyers and investors, with zero overclaim.
Definition of done: the 100-point acceptance rubric at the end. Every phase maps to rubric items and
keeps the `CLAUDE.md` verify chain green.
Source design notes (read before executing any phase):
- `docs/notes/2026-06-05-cachet-local-architecture.md` (offline architecture, honesty map, airplane proof)
- `docs/notes/2026-06-05-cachet-deterministic-extraction.md` (anchor engine, honesty tiers, the eyecite fix)
Honesty tiers used throughout: T0 = pure deterministic / no AI; T1 = local classical ML / no LLM /
no cloud; T2 = local LLM. Never label a T1/T2 step deterministic or "no AI."

---

## Phase 0: Documentation discovery (DONE 2026-06-05, first-hand verified)

### Allowed APIs (verified by reading installed source)

eyecite 2.7.6 (BSD-2, installed, T0, no model files):
- `from eyecite.find import get_citations` -> `get_citations(plain_text="...") -> list[CitationBase]`
  (find.py:40). Default tokenizer is Aho-Corasick (tokenizers.py:611).
- Citation classes: `FullCaseCitation` (models.py:482), `FullLawCitation` (366), `ShortCaseCitation`
  (569), `SupraCitation` (599), `IdCitation` (637).
- Offsets into the SOURCE string: `citation.span() -> (start, end)` (models.py:177); `citation.full_span()`
  includes case name + parenthetical (models.py:220).
- `citation.matched_text()` (models.py:173); `citation.groups` dict with `volume`/`reporter`/`page`
  (models.py:75); `citation.metadata.parenthetical` / `.pin_cite` / `.plaintiff` / `.defendant` /
  `.court` / `.year` (models.py:144-151, 511-521); `citation.corrected_citation()`.
- `reporters_db`: `REPORTERS`, `EDITIONS`, `NAMES_TO_EDITIONS` (reporters_db/__init__.py:21-55) for local
  reporter validation if needed.
- python-dateutil 2.9.0 installed: `dateutil.parser.parse(s, fuzzy=False)` for a narrow T0 date fallback.
- spaCy and NLTK are NOT installed (keep it that way for T0).

The envelope contract (`services/verify.py::_verify_result_from_envelope`, verify.py:282-378). A new
`build_deterministic_envelope` must emit a dict with exactly these keys:
- top level: `claims: list[dict]`, `unsupported_spans: list[str]`, `model: str` (or `answer_model`),
  `error: str|None`, `provider: str` (read at verify.py:292-295, 375).
- per claim: `text: str`, `citations: list[dict]`, `case_verdicts: list[dict]` (verify.py:306-310).
- per citation: `content: str`, `document_id` (or `doc_id`), `char_start: int|None`, `char_end: int|None`,
  `chunk_index: int|None` (verify.py:465-510).
- per case verdict: `verdicts: list[dict]`, each with `opinion_text: str|None` (verify.py:518-534).
The entry is `verify_draft(conn, draft, *, doc_ids, subject_name, log_study_event, fetch_recent_events)
-> VerifyResult` (verify.py:220); the envelope call to swap is at verify.py:251-256.

Reusable functions (copy/wrap, do not reinvent):
- `services/legal/quote_check.py`: `extract_draft_quotes` (106), `extract_draft_quote_spans` (122) ->
  `(inner, start, end)`, `split_runs` (144), `check_quote_against_sources` (175); `_QUOTED_SPAN` (46),
  `_EDIT_MARK` (53).
- `services/retrieval/validators.py`: `verbatim_run_present` (310), `enforce_verbatim_substring` (349),
  `validated_citation_quote` (235), `normalize_for_verbatim` (265).
- `services/legal/case_verification.py`: `verify_claims_for_cases(claim_texts, *, client=None,
  ai_provider=None, enable_holding_match=True)` (500); `verify_claims_for_cases_steps` (449);
  `_CITATION_SHAPE` (59, to be deprecated); `_looks_like_legal_text` (331).
- `services/legal/courtlistener.py`: `lookup_citations_in_text(text, *, client=None)` (296);
  `fetch_opinion_text(opinion_uri, *, client=None, max_chars=8000)` (481); token guard returning
  `courtlistener_no_api_token` (311-321); base URL via `COURTLISTENER_BASE_URL`.
- `services/retrieval/typed_hybrid.py`: `search_typed_hybrid(conn, query, *, embedder=None, node_types=None,
  doc_ids=None, subject_name=None, limit=10, ...)` (165); `RetrievedNode` fields verbatim_text, char_start,
  char_end, node_type, heading_path, page (31-55).
- `services/retrieval/embeddings.py`: `FastembedEmbedder` -> `TextEmbedding(model_name="BAAI/bge-small-en-v1.5")`
  (14-21), NO cache_dir today.
- `db.py`: `_load_extensions` (151-174) returns False and degrades silently when sqlite-vec is missing.
- `migrations/0001_initial.sql`: `evidence_references` has `anchor_text`, `anchor_start` (187), `anchor_end`
  (188). No new migration required for anchors.
- `api_models.py`: `VerifyResponse` (343-362), `VerifyClaimVerdictItem.verdict: Literal["verified",
  "unsupported","unknown"]` (297-316), `TutorCitationItem` (145-167), `CaseVerdictItem` (170-202).
- Frontend: `claimDisposition.ts` DispositionKind has 5 states incl. `citation_not_found`,
  `proposition_unsupported`, `claim_unsupported`, `could_not_check` (31-36); DispositionTier
  pass/flag/assistive/refusal (46). `could_not_check` COLLAPSES no-data and infra-failure (169-200).
  `certification.ts`: `fingerprintDraft` SHA-256 (26), `CertificationModel` (112-122, no per-source hash),
  `buildCertification` (139). `CertificationExhibit.tsx`: `window.print()` (197), flagged-first (304-324),
  the "attests to grounding, not truth" attestation already present (207-272). `ProvenanceBadge.tsx`:
  PROVIDER_REGISTRY claude/afm/ollama/null, tone only, no local/cloud axis (10-15). `types.gen.ts`
  VerifyResponse has provider + model, NO `local_execution` (3421-3454).

### Anti-patterns to avoid (verified false or licensing traps)
- Do NOT add LexNLP (AGPL-3.0; its amounts.py/dates.py are secretly T1). Re-implement money/duration/date
  regexes clean-room as MIT in `services/legal/anchors.py`.
- Do NOT add Stanford OpenIE (T1 + GPL-3). Do NOT add spaCy/NLTK for T0 work.
- Do NOT label any step using Docling, fastembed-vector, NLI, or an LLM as "deterministic" or "no AI."
- Do NOT collapse `could_not_check_no_anchor` (honest scope exit) with `could_not_check_infra` (failure).
- Do NOT render a verbatim-present result as "supported" (the ellipsis/carve-out refutation holds).
- Do NOT strip `com.apple.security.network.client` to prove offline (WKWebView needs it; CONFIRMED).
- Open item to CONFIRM in Phase 2, not assume: the exact fastembed offline knob (`TextEmbedding(cache_dir=...)`
  vs `HF_HUB_OFFLINE=1` / `HF_HOME`); read `.venv/.../fastembed/` before coding.

---

## Phase 1: eyecite citation adapter (standalone bug-fix win)

Scope: replace the broken `_CITATION_SHAPE` pre-filter with eyecite so digit-bearing reporters
(F.3d/F.Supp.2d/Cal.4th/N.Y.2d) are detected. Independently shippable correctness win on its own.
Rubric: 1 (partial), 7. Depends on: none.
Files: new `services/legal/citations_eyecite.py` (wrap `get_citations`, yield Anchor-shaped dicts with
`matched_text`, `span()` offsets, groups, parenthetical); `services/legal/case_verification.py:59,331`
(route `_looks_like_legal_text` through the adapter; keep `_CITATION_SHAPE` as a fallback if the import
fails); add `eyecite` + `reporters-db` to `requirements.txt` as first-class pins.
Copy from: Phase 0 eyecite snippet (get_citations + citation.span()/.matched_text()/.groups).
Verification gate: `tests/test_citations_eyecite.py` asserts 410 F.3d 138 / 892 F.Supp.2d 1234 /
22 Cal.4th 100 / 123 N.Y.2d 456 are detected (currently missed) and offsets are correct; ruff green.
Anti-pattern guard: do not call get_citations positionally past `plain_text`; do not assume `groups`
keys beyond volume/reporter/page for non-case cites.

## Phase 2: Offline foundation (embedder pin + fail-loud sqlite-vec)

Scope: make embeddings work air-gapped and make a missing sqlite-vec fail loud in demo mode.
Rubric: 3 (partial). Depends on: none (do early to de-risk offline).
Files: `services/retrieval/embeddings.py:14-21` (pin the model offline; confirm the exact knob first);
a build-time pre-cache step; `db.py:151-174` (a demo-mode fail-loud guard when sqlite-vec is absent
instead of silent BM25-only).
Verification gate: a test that `embed()` succeeds with networking disabled, and that a missing sqlite-vec
raises in demo mode rather than returning `[]`.
Anti-pattern guard: confirm the fastembed knob by reading the installed package; do not hard-code a path
that breaks notarized bundling.

## Phase 3: Anchor engine core (anchors.py + legal sentence splitter)

Scope: the T0 extraction primitives. `extract_anchors(span) -> list[Anchor]` with the 8 detectors;
clean-room money/duration/section/defined-term regexes; date via narrow regex + dateutil; a legal-aware
sentence splitter (the existing splitters fragment "U.S.", "F.3d", "v.", "Fed. R. Civ. P.").
Rubric: 1, 2 (extraction core). Depends on: Phase 1 (citation anchor reuses the eyecite adapter).
Files: new `services/legal/anchors.py`, new `services/legal/sentences.py`. Reuse `_QUOTED_SPAN` /
`extract_draft_quote_spans` for the quoted-run anchor; add the slip-op regex
`\bNo\.\s+\d{1,4}-\d{1,6}\b` + `\bslip\s+op\.`.
Verification gate: `tests/test_anchors.py` (9 reporter formats + 3 false positives + word-form amounts like
"five (5) years" and "one million dollars ($1,000,000)"); `tests/test_legal_sentences.py` (abbreviation
allow-list). ruff green.
Anti-pattern guard: clean-room regexes only, no LexNLP import; populate `canonical_value` only for parametric
types (money to cents, duration to days, date to ISO).

## Phase 4: Local case-existence SQLite backend

Scope: an offline adapter behind the `courtlistener.py` `client=` seam, backed by a bundled SQLite of the
demo's pre-vetted cases, so existence checks need no network.
Rubric: 1, 3. Depends on: Phase 1.
Files: new `services/legal/local_caselaw.py` (same `CitationHit`/`CourtListenerResult` shape as
`lookup_citations_in_text`/`fetch_opinion_text`); accept a sentinel token to pass the guard at
courtlistener.py:311-321; a small bundled `.sqlite` of demo cases + opinion text.
Verification gate: `tests/test_local_caselaw.py` asserts a real cite returns exists=True and a fabricated
cite exists=False, both with zero httpx (forbidding transport).
Anti-pattern guard: keep the bundled corpus demo-only and disclose it; do not present it as the full corpus.

## Phase 5: Deterministic envelope (litigator path wired)

Scope: the new orchestration seam that produces the exact envelope dict and routes the litigator path
L1-L6, behind a flag.
Rubric: 1, 5. Depends on: Phases 1, 3, 4.
Files: new `services/legal/deterministic_envelope.py::build_deterministic_envelope(cleaned, conn) -> dict`
(anchors -> quote<->cite association within a 120-char window -> existence via Phase 4 with
`enable_holding_match=False` -> verbatim via `verbatim_run_present` -> 3-state routing); swap
`services/verify.py:251-256` behind `CACHET_DETERMINISTIC_VERIFY=true` (default off). Return shape and
verify.py:282 are UNCHANGED.
Copy from: Phase 0 envelope contract (exact keys).
Verification gate: `tests/test_deterministic_envelope.py` runs the full opener (fabricated cite -> refusal,
altered quote -> quote_altered, real cite -> pass) under a network-forbidding transport; asserts zero LLM
and zero network. Verify chain green with the flag on and off.
Anti-pattern guard: emit every key `_verify_result_from_envelope` reads; never render verbatim-present as
"supported."

## Phase 6: Contract path (defined-term table + parametric contradiction)

Scope: the contract engine C1-C5. Build the defined-term/party alias table at ingest; detect anchors on the
AI summary; retrieve the clause via `search_typed_hybrid`; decide not-found / present / parametric
contradiction; route anchor-free claims to the loud tray.
Rubric: 2. Depends on: Phases 3, 5.
Files: extend `services/ingestion/` for the C1 table (store alias->canonical, reuse `evidence_references`
or a tiny additive migration 0017); the contract branch in `build_deterministic_envelope`; reuse
`search_typed_hybrid` and the verbatim validators.
Verification gate: `tests/test_contract_verify.py` asserts present ("language appears in Section X"),
parametric_contradiction (number mismatch), cannot_verify (not found), and could_not_check_no_anchor, all
with zero LLM and zero network.
Anti-pattern guard: build the alias table BEFORE any structural drop (`is_banner_shape` would suppress
Title-Case defined terms); print "review full clause for context" on every present verdict; do not import
LexNLP.

## Phase 7: 3-state verdict + coverage summary (the honesty surface)

Scope: split `could_not_check` into `could_not_check_no_anchor` (honest scope exit) vs `could_not_check_infra`
(failure); add a coverage summary so skipped claims never read as clean.
Rubric: 1, 2, 5. Depends on: Phases 5, 6.
Files: `frontend/src/features/verify/claimDisposition.ts:31-36,169-200` (the new states + branch);
`VerifyView.tsx:299-343` (coverage summary "checked N, did not check S, here they are"); the backend
envelope + `api_models.py` verdict enum + `types.gen.ts` via `./script/generate-api-types.sh`.
Verification gate: `claimDisposition.test.ts` covers the split; vitest + typecheck green; the summary renders
the not-checked count.
Anti-pattern guard: never collapse the two could_not_check states; never let an infra failure read as a
substantive refusal.

## Phase 8: Audit artifact upgrade (filing-grade)

Scope: per-source SHA-256, a named "no data left this device" attestation, a local-vs-cloud provenance axis,
and a machine-readable JSON export beside the PDF.
Rubric: 4, 5. Depends on: Phase 7.
Files: `certification.ts:102-122,139-175` (extend CertificationItem with `sourceFingerprint`, add
`attestationLocal`, hash each source); `CertificationExhibit.tsx:197` (add a JSON export handler beside
print); `ProvenanceBadge.tsx:10-15` (add a `location: "local"|"cloud"` axis); add `local_execution: bool`
to `VerifyResponse` (api_models + regen types). Reuse the existing attestation text and flagged-first layout.
Verification gate: vitest on the badge variant, the per-source hash, and the JSON export; the exhibit shows
the attestation field and the local badge; verify chain green.
Anti-pattern guard: do not flatten "claude" to "local"; provider name and execution-location are two axes.

## Phase 9: Provable-offline harness + zero-egress CI test

Scope: the structural proof behind the live demo, plus the notarization-staple + airplane-mode runbook.
Rubric: 3. Depends on: Phases 5, 6.
Files: `tests/test_zero_egress.py` (install a forbidding httpx transport globally, run both surfaces end to
end, assert zero external sockets); a short runbook note for stapling the notarization ticket and pre-launching
once so trustd's OCSP attempt cannot dirty the monitor during the verify run.
Verification gate: the zero-egress test in CI; a manual airplane-mode pass on the dev machine.
Anti-pattern guard: present behavioral proof (airplane + monitor) honestly, never as structural proof; do not
remove the network entitlement.

## Phase 10: Demo corpus + craft + multi-width QA

Scope: assemble the real pre-vetted corpus; DESIGN.md pass with the refusal state as the hero; verify at
multiple widths.
Rubric: 6 (and exercises 1, 2, 3). Depends on: Phases 1-9.
Files: a `demo/` corpus (litigator motion with one real cite, one fabricated cite, one altered-quote case;
contract NDA + an AI summary with two verbatim-present claims and one parametric mismatch); UI polish per
`DESIGN.md`.
Verification gate: screenshots captured at 1440 and 1920 (not the 800px preview default); per-verdict render
under ~1.5s measured; every demo catch fires genuinely on real documents.
Anti-pattern guard: corpus must be real and pre-vetted, never staged; do not declare done from one viewport.

## Phase 11: Final verification + dress rehearsal (hard gate)

Scope: the full verify chain, eval non-regression, and the pre-demo rehearsal.
Rubric: 7 (hard gate). Depends on: all.
Verification gate: run the entire `CLAUDE.md` verify chain green with the new tests wired into the unittest
line; `evals --mode full` keeps `groundedness@8 >= 0.7` and `quote_validity >= 0.95`.

### Pre-demo dress-rehearsal checklist (run on the EXACT demo machine, the night before)
- Apple Intelligence state irrelevant (the demo is deterministic; AFM/NLI/holding-match all OFF).
- Embedder weights pre-cached; sqlite-vec installed and loading (no silent BM25 fallback).
- Bundled case-law SQLite present; the fabricated cite genuinely returns no hit.
- Notarization ticket stapled; launch once online, then go to airplane mode.
- Airplane mode ON (Wi-Fi + Ethernet off); network monitor (Little Snitch Network Monitor or macOS-native)
  open and projected; run both surfaces; confirm the monitor stays flat.
- Run the full litigator opener and contract close end to end twice; time each verdict render.
- Export the Certification Exhibit (PDF + JSON); confirm the per-source hash and the "no data left this
  device" attestation appear.
- Screenshots captured at 1440 and 1920.

### Open risks to watch
- Contract anchor recall on word-form values ("five (5) years", "one million dollars ($1,000,000)") is
  unmeasured; test the normalizer on real NDA language before relying on the parametric-contradiction catch.
- The bundled citation-index size is still UNKNOWN beyond "demo cases only"; measure a metadata-only import
  before claiming any general litigator coverage.
- On-device NLI latency is unmeasured (roadmap only; off in the demo).
- fastembed offline knob must be confirmed in Phase 2, not assumed.

---

## The 100-point acceptance rubric (definition of done)

1. Litigator catch (20): eyecite replaces _CITATION_SHAPE and detects F.3d/F.Supp.2d/Cal.4th/N.Y.2d;
   fabricated cite -> cite_not_found; altered quote -> quote_altered; real cite passes; inline quote<->cite
   association works; 3-state verdict never collapses refusal vs could-not-check; zero false positives on
   the pre-vetted corpus.
2. Contract catch (15): parametric contradiction fires on a number mismatch; verbatim-present attests
   "language appears in Section X" not "true"; not-found -> cannot_verify; defined-term table built at
   ingest; anchor-free claims -> loud could_not_check_no_anchor tray.
3. Offline guarantee provable (20): both surfaces run network-disabled; live monitor flat; embedder
   pre-cached; sqlite-vec fails loud; zero-egress CI test; trustd OCSP handled (staple + airplane mode);
   behavioral-vs-structural framing honest.
4. Audit artifact filing-grade (15): timestamp + draft SHA-256 + per-source SHA-256; "no data left this
   device" named field; flagged-items-first; provider provenance local-vs-cloud axis not flattened;
   print-to-PDF + machine-readable JSON; attorney-attestation line.
5. Honesty/no-overclaim (15): no T1/T2 step labeled deterministic/no-AI; Heppner framed correctly; Apple FM
   off critical path and not "always offline"; verbatim-present never rendered "supported"; coverage summary
   present so skipped never reads as clean; contract anchor coverage caveated ~25-35%; snapshot-date +
   demo-only corpus disclosed.
6. Craft/demo reliability (10): per-verdict render <1.5s (no LLM live); DESIGN.md adherence with the refusal
   state as hero; screenshots verified at 1440 and 1920; failure modes rehearsed on the exact demo machine
   in airplane mode; corpus real/pre-vetted.
7. Verify chain green (5, hard gate): full CLAUDE.md chain passes with new tests for
   anchors/eyecite-adapter/deterministic-envelope/legal-sentence-splitter; no eval regression
   (groundedness@8 >= 0.7, quote_validity >= 0.95).
