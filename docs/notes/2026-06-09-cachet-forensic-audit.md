# Cachet deterministic verify engine: forensic audit (2026-06-09)

Full-engine reconstruction, claims-vs-reality ledger, defect register, and the
build plan that follows from them. Every assertion below is grounded in a file
and line on this branch's parent commit (dde839bba) or in a runtime repro run
against that code. Where something is inferred rather than confirmed, it says
so. The companion code commits on `cachet/verify-hardening-2026-06-09` close
the confirmed defects test-first.

## 1. Engine map

The deterministic verify path, end to end:

1. Entry. `POST /api/verify` and `POST /api/verify/stream`
   (`routes/verify.py:36`, `routes/verify.py:51`). The surface default is
   deterministic: `_deterministic_surface_default()` (`routes/verify.py:25-33`)
   returns True unless `CACHET_DETERMINISTIC_VERIFY` is explicitly
   `0/false/no`. The LLM grounding path is an explicit opt-out, not a fallback.
2. Orchestration. `services/verify.py::verify_draft` (:388) and
   `verify_draft_stream` (:790) resolve the path via `_resolve_deterministic`
   (:373-385; direct callers without the flag stay on the legacy LLM default)
   and call `build_deterministic_envelope`
   (`services/legal/deterministic_envelope.py:578`). The stream variant has its
   own deterministic branch (:837-854) because the demo UI calls only the
   stream; without it the stream would fall through to the LLM path.
3. Sentence split. `services/legal/sentences.py::split_sentences` (:73),
   legal-abbreviation aware, never splits inside an eyecite citation span
   (:108-113), absorbs one trailing court-year parenthetical (:86-106), and
   deliberately does not split at a closing-quote boundary (:63-69, the pinned
   unit-of-grounding limitation).
4. Anchor extraction. `services/legal/anchors.py::extract_anchors` (:252)
   detects citation (eyecite), slip_op, quote, money (digit and word form),
   duration, date, section (suppressed inside citation spans, :292-299), party
   (alias and entity-suffix forms), and defined_term (table-driven from the
   source's own definitions, :238-249).
5. Routing, per sentence (`deterministic_envelope.py:651-753`):
   - a case citation present (`find_citations`, kind == "case", :658) routes to
     offline case-existence: `verify_claims_for_cases` with
     `enable_holding_match=False` and the in-process `local_caselaw_client()`
     MockTransport (:603, `services/legal/local_caselaw.py:135-146`).
     `_annotate_litigator_verdicts` (:70-96) stamps `holding_skipped`,
     `bounded_corpus=True`, and `caption_mismatch` via `caption_matches`
     (`services/legal/citations_eyecite.py:193-211`).
   - otherwise, in contract mode (a conn plus doc_ids; empty doc_ids falls back
     to every ready document, :605-617) an anchor-bearing sentence goes to
     `_contract_claim` (:445-535): top-3 typed-hybrid retrieval, clause check
     via `verify_claim_against_clause`
     (`services/legal/contract_verify.py:65-165`), the C3 topic gate
     (:185-199), the C2 quote-laundering guard (:512-519), and the
     grounding overlay (party/section/defined-term, :343-442).
   - an anchor-bearing sentence with no source becomes a could-not-check card
     (:738-753); an anchor-free sentence is `untreated` (:705-737), no card,
     unless the dark T1 tier promotes it (gated by `t1_permitted()`,
     `services/legal/t1_gate.py:75-109`, fail-closed on a gate-pass artifact
     that does not exist on main).
6. Quote pass. Same-sentence attribution only: each sentence's quoted phrases
   are checked against the bundled opinion text of the cases cited in that
   sentence (:762-765, `_quote_unverified_reason` :202-228, with
   `_quoted_subphrases` :127-139 and `_first_letter_variants` :231-247).
   Absence is a could-not-check, never an "altered" accusation.
7. Verdict assembly. `services/verify.py::_verify_result_from_envelope`
   (:460-581) maps each claim dict to a card via `_claim_dict_to_verdict`
   (:205-306). Precedence: in-corpus citations, then section_absent, then
   quote could-not-check, then anchor-free could-not-check, then contract
   verdict, then case verdicts, else unsupported. Case verdicts fold three-state
   in `_verdict_from_case_verdicts` (:135-170): missing beats failed beats
   outside-coverage beats exists. T1 assessments attach only to could-not-check
   cards and never change the verdict (:283-294).
8. Brief-level quote panel. `extract_draft_quotes` over the whole draft,
   checked against a pool of loaded-doc joins (`_join_adjacent` :619-690),
   contract clauses (complete=False, :724-743), and bundled opinion text
   (:746-762), via `check_quote_against_sources`
   (`services/legal/quote_check.py:181-218`). Altered fires only against
   complete, untruncated sources with no uncertain source in the pool.
9. Placement. `services/legal/align.py::align_claims_to_draft` (:164-217)
   pins each card to a draft range only when exactly one unambiguous match
   exists; everything else trays.
10. Wire. `verify_result_to_payload` (:439-457); opinion text stripped at the
    single serialization boundary (:584-603). The stream emits quote_batch then
    result; the LLM path streams skeleton claims and per-cite verdicts with
    invariant #6 enforced client-side
    (`frontend/src/features/verify/streamProgress.ts:51-114`: a claim is
    "checking" until its cite_verdict lands; a dropped stream becomes a loud
    error, `useVerify.ts:122-126`).
11. Render. `dispositionForClaim`
    (`frontend/src/features/verify/claimDisposition.ts:147-296`) collapses each
    card into supported / citation_not_found / proposition_unsupported /
    claim_unsupported / assessed / could_not_check, with the bounded-corpus
    404 routed to could-not-check (:153-194) and verified downgraded on any
    uncheckable dimension (:252-274). The summary counts dispositions, not the
    backend summary (`VerifyResults.tsx:288-341`). The certification artifact
    (`certification.ts:203-248`) fingerprints the draft (local SHA-256) and
    attests locality by provider label (:116-136).

Both wedges share 1, 2, 3, 4, 7, 9, 10, 11. The litigator wedge is 5a + 6 + 8;
the contract wedge is 5b + 8.

## 2. Claims-vs-reality ledger

1. "Zero egress": CONFIRMED for the deterministic path, with one test debt.
   The socket ban (`tests/test_zero_egress.py:35-41`) patches `socket.socket`
   and the suite covers both wedges, stream and non-stream, flag set and unset,
   plus the T1-enabled model-load path (:67-339). All pass in a clean Linux
   sandbox after the embedder cache is provisioned. Debt: the stream-contract
   case (:241-271) stubs `nodes_vector.default_embedder`, which is no longer on
   the path since ed3aea1de; it passes only on a warm fastembed cache and fails
   on a cold one (reproduced). The offline floor itself held: the cold-cache
   run degraded to per-sentence could-not-check, no socket. Fixed on this
   branch (commit "make the stream-contract zero-egress test hermetic").
   Route-level: an outbound-connect ban held across a full
   `POST /api/verify` in-process run (reproduced; the blunt socket-class ban
   cannot wrap an ASGI client because asyncio's self-pipe is a socketpair).
2. "No cloud" / CACHET_ONLY: CONFIRMED as believed, and worth saying plainly.
   `CACHET_ONLY` is a frontend render swap only (`frontend/src/main.tsx:85`).
   The backend ships `anthropic` and the full study app either way, and the
   LLM grounding path exists as a live opt-out branch:
   `CACHET_DETERMINISTIC_VERIFY=0` routes verify through
   `grounded_tutor_envelope` (`services/verify.py:427-434`), which reaches
   Claude and live CourtListener (`services/tutor.py:1416`,
   `case_verification.py:527`, `courtlistener.py:352`). "No cloud" is a
   default and a posture, not a build-time property. `script/serve-cachet.py:38`
   hard-pins the flag for the demo.
3. "Local / offline": CONFIRMED with teeth. `_enforce_offline_env` forces
   `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` by assignment, not setdefault
   (`services/retrieval/embeddings.py:20-37`), the offline embedder is a
   separate singleton that cannot be satisfied by an online-built one
   (:87-106), and a cold cache raises RuntimeError which the envelope degrades
   to per-sentence could-not-check cards naming the cause
   (`deterministic_envelope.py:627-637`, :674-692). Loud, not silent.
   T1 mirrors this (`services/legal/_offline_model.py:27-68`). Caveat: the env
   forcing is process-global and permanent, which can surprise the co-resident
   study app (defect D12).
4. "Deterministic": CONFIRMED for T0, and the T1 labeling is honest. T0 is
   regex, table lookup, string compare, arithmetic; the model name on the wire
   is `deterministic-v1` and provider `deterministic`
   (`deterministic_envelope.py:52`, :772). T1 is never labeled deterministic:
   it renders as "Assessed (local model) ... Not a deterministic verification"
   in the assistive register (`claimDisposition.ts:222-243`), never changes a
   verdict (`services/verify.py:283-294`), and is physically dark: the gate
   requires a gate-pass artifact whose `best_of_k_enforced` is True, the gate
   stamps False today, and `data/calibration/thresholds.json` ships nulls that
   hard-fail `load_runtime_thresholds` (verified on disk).
5. Holding-match: CONFIRMED off on the deterministic path
   (`enable_holding_match=False`, `deterministic_envelope.py:659-661`), and
   the UI renders the skip as "exists, not evaluated", a pass with an honest
   hedge (`claimDisposition.ts:278-287`). On the legacy LLM path holding-match
   is on by default (`case_verification.py:504`), LLM-backed
   (`check_holding_match` :211-314), and renders in the assistive register,
   never oxblood (`claimDisposition.ts:83`, `VerifyResults.tsx:44-57`). No
   verdict-affecting model call exists on the deterministic path.
6. False-positive / false-negative paths: BROKEN in five concrete places.
   See the defect register: a wrong caption with one shared token reads
   "Citation verified" (D3); the quote panel false-flags clean quotes in two
   ways (D1, D2); a near-miss duration reads "present" with a false detail
   string (D4); an off-topic value coincidence reads "present" past the topic
   gate (D5). All five reproduced against the live engine. The deeper
   architecture (three-state folds, refuse-over-accuse, stream invariant #6)
   held up under hostile reading everywhere else it was probed.
7. Coverage honesty: OVERCLAIMED at the surface. The engine's internal
   untreated/could-not-check split is real and correct, but untreated
   sentences are dropped server-side and never counted anywhere the user can
   see. The scope note says "Each statement is checked against the sources you
   provide" (`VerifyResults.tsx:335-338`), the summary says "All N statements
   are supported" where N counts only carded statements, and the certification
   says "Statements checked: N" and "Complete record of all statements
   checked" with no unchecked count (`certification.ts:242`,
   `CertificationExhibit.tsx`). In the read-back, a supported span and
   never-checked prose are visually identical (both unmarked,
   `WorkspaceMargin.tsx:38-49`); only the aria-label differs. Anchor coverage
   of contract clause content is structurally thin (the 25-35% figure in the
   design notes is consistent with the anchor set; not independently measured
   here). Closed end-to-end on this branch for the counting and copy; the
   extraction work that raises real coverage is in the build plan.

## 3. Defect register

Severity reflects the product's own bar: a confident wrong verdict is worst, a
false accusation second, a silent honesty gap third.

- D1 HIGH (false accusation, reproduced). Two straight-quoted spans in one
  paragraph merge into one span (`quote_check.py:52` greedy-to-last by
  design); the envelope path splits the merged run back into its quoted
  phrases (`deterministic_envelope.py:127-139`, applied :221) but the
  brief-level panel does not (`services/verify.py:481-493` calls
  `check_quote_against_sources` directly), so the lawyer's own connecting
  prose is treated as quoted text. Repro: two verbatim Brown quotes in one
  paragraph; panel renders "Not found verbatim" (oxblood) while the claim card
  says "Citation verified". Fix: share the subphrase split and the
  leading-letter variants inside `check_quote_against_sources`.
- D2 HIGH (false accusation, reproduced). A quote whose leading capital was
  lowercased to embed mid-sentence (universally accepted edit) passes the
  sentence-level check (`_first_letter_variants`,
  `deterministic_envelope.py:231-247`) but false-flags at the panel, which
  matches case-sensitively with no variant (`quote_check.py:205-216`).
  Same fix as D1.
- D3 HIGH (false verified, reproduced end-to-end). `caption_matches` passes
  when ANY draft token is compatible with ANY resolved token
  (`citations_eyecite.py:211`). "Smith v. Board, 347 U.S. 483" shares the
  generic token "board" with Brown's caption and reads verified; the API
  returns verdict "verified" and the UI badge says "Citation verified". A
  caption swap is a common hallucination shape, so the flagship catch has a
  one-token-wide hole. Fix: per-side compatibility. When a populated caption
  side (plaintiff or defendant) has no compatible token while another side
  matches, the verdict downgrades to could-not-check (refuse, never accuse);
  only a caption with no compatible token anywhere keeps the hard mismatch
  flag (unchanged). Initialism support (NLRB for National Labor Relations
  Board) is added so the stricter rule does not false-flag initialism
  captions.
- D4 MEDIUM-HIGH (false verified plus false detail string, reproduced). The
  duration tolerance (`contract_verify.py:34`, :46-50, :60-62) applies 5%
  across the board, so "23 months" vs a clause's "24 months" (4.2%) reads
  "present" and the detail asserts "23 months appears in Section 9.1", which
  is false. Same for 360 vs 365 days. The tolerance exists to make "12
  months" match "1 year" across the day-count approximation; it must apply
  only across units. Fix: compare same-unit durations exactly; keep the
  tolerance for cross-unit pairs; when a tolerant cross-unit match fires, the
  detail says "consistent with", never "appears in".
- D5 MEDIUM (false verified, reproduced at the gate). The C3 topic gate
  passes on one shared content word (`deterministic_envelope.py:185-199`).
  An off-topic clause that shares the contract's own name ("Services") plus a
  coincidental value reads "present": a signing-bonus clause supports a
  liability-cap claim. Amplified by the full-library fallback (:605-617): the
  lectern sends no doc_ids when no record is picked (`LecternView.tsx:49`), so
  the pool is every ready document. Fix: require two shared content words
  (with singular/plural fold); recall loss degrades to could-not-check, the
  safe direction.
- D6 MEDIUM (false attestation, confirmed statically). The certification
  treats afm and ollama as "No data left this device. All verification ran
  locally" (`certification.ts:116-136`), but those providers ride the LLM
  grounding path, which POSTs claim text to live CourtListener when a token is
  configured (`tutor.py:1416`, `case_verification.py:527`,
  `courtlistener.py:348-352`) and fetches opinion text. The artifact would
  attest no-egress on a run that egressed. Fix: only `deterministic` earns the
  no-egress attestation; afm/ollama get "the language model ran on this
  device; citation lookups may have used the network".
- D7 MEDIUM (coverage overclaim, confirmed statically). Untreated sentences
  are invisible: dropped at card-build (`services/verify.py:506-514`), no
  count on the wire, cert counts cards as "Statements checked"
  (`certification.ts:242`), scope note claims every statement is checked
  (`VerifyResults.tsx:335-338`), and unmarked-supported vs untreated prose are
  visually identical in the read-back. Fix: count sentences/treated/untreated
  in the envelope, carry a `coverage` block on the wire, render it in the
  summary, scope note, and certification.
- D8 MEDIUM (test hermeticity, reproduced). The stream-contract zero-egress
  test stubs `nodes_vector.default_embedder`
  (`tests/test_zero_egress.py:247-255`), dead on the path since ed3aea1de;
  green on a warm cache, red on a cold one. The test no longer pins the
  behavior it names. Fix: stub `FastembedEmbedder` and reset
  `_offline_default`, as the env-unset test already does.
- D9 LOW (attribution overclaim, by design but under-disclosed). The panel
  satisfies a run present in ANY pooled source (`quote_check.py:205-210`), so
  a quote attributed in the draft to case A but verbatim in pooled case B
  reads "Verbatim", and the panel's scope note says the words "appear in the
  cited source" (`VerifyResults.tsx:386-389`). Sentence-level attribution is
  same-sentence only and unaffected. Candidate fix is per-claim quote
  attribution (build plan); near-term the scope note should say "in the
  sources checked".
- D10 LOW (theoretical false flag). `_join_adjacent`
  (`services/verify.py:670-689`) treats overlapping pieces as adjacent and
  joins with a newline, duplicating the overlap; a quote straddling the
  overlap boundary would not be found in the join, and a multi-piece join is
  complete=True so it can ground altered. Nodes should not overlap; kept on
  the register because the join is in the altered-grounding path.
- D11 LOW (doc/code mismatch, safe direction). `align.py` documents in-order
  consumption of repeated keys (:128-140, :177-179) but the code trays every
  claim whose key has two or more remaining occurrences (:134-140); repeated
  keys never place. Strictly safer than documented; the docstring is wrong.
- D12 LOW (process side effect). The first deterministic verify permanently
  forces HF offline for the whole process (`embeddings.py:36-37`), so a
  co-resident Carrel study session can no longer download embedding or
  reranker models until restart. Acceptable for Cachet-only; undocumented.
- D13 DESIGN. `bounded_corpus` is hard-coded True for every deterministic
  verdict (`deterministic_envelope.py:90`), so a fabricated cite always reads
  could-not-check, never "citation not found". Correct for the 3-case demo
  corpus; wrong the day a complete national corpus ships. The corpus needs a
  completeness attestation the engine reads, not a constant.

What the existing tests do not assert (gaps the new tests close or the plan
covers): multi-quote paragraphs and case-variant quotes at the panel level
(D1/D2); any caption where one side matches and the other does not (D3);
same-unit near-miss durations (D4); a single-shared-word off-topic present
(D5); any attestation text for afm/ollama (D6); any coverage accounting
(D7); cold-cache behavior of the stream-contract egress test (D8).

## 4. Forward build plan

Sequenced, test-gated, additive, smallest first. Commits 1-7 land on this
branch; each is independently shippable as its own PR.

1. Quote-check parity (D1, D2). Move the quoted-subphrase split and the
   leading-letter variant into `quote_check.py`, apply them in
   `check_quote_against_sources`, import them in the envelope (one source of
   truth). Failing tests first: merged two-quote paragraph reads verbatim;
   case-variant quote reads verbatim; a true alteration still flags; envelope
   behavior unchanged.
2. Caption three-state (D3). `caption_match_state` returning
   match/unconfirmed/mismatch with per-side compatibility plus initialisms;
   `caption_unconfirmed` annotation on the verdict; envelope reason text;
   `_verdict_from_case_verdicts` maps unconfirmed to unknown. The wire shape
   is additive; the frontend already renders unknown+reason as the refusal.
3. Duration unit honesty (D4). Same-unit exact compare, cross-unit
   tolerance, "consistent with" detail wording on tolerant matches.
4. Topic-gate tightening (D5). Direction-split floors with singular/plural
   fold: a present needs two shared content words (support by coincidence
   otherwise), a contradiction needs one (previously zero; the demo corpus's
   own gold catches share exactly one topic word with their clauses, which the
   full-chain run surfaced when a uniform two-word floor regressed them).
   Failing tests are the signing-bonus/liability-cap present and the
   off-topic contradiction; the demo-corpus suite locks the gold catches.
5. Coverage on the wire (D7). Envelope counts sentences/treated/untreated;
   `coverage` block on the payload and stream result; summary line, scope
   note, and certification render checked-of-total and the unchecked count.
6. Attestation honesty (D6). Provider-conditional attestation text in
   `certification.ts`; only `deterministic` claims no-egress.
7. Hermetic egress test (D8). Repoint the stream-contract test stubs at the
   offline embedder seam.

Next PRs (designed, not built here):

8. Corpus completeness attestation (D13). The bundled corpus carries a
   manifest (scope: demo-N-cases vs full-mirror-as-of-date); the envelope
   reads it to decide bounded_corpus per run; the disposition copy names the
   corpus scope and date. Same PR, same metadata: check the cite's court-year
   parenthetical against the corpus date_filed and court, so "Brown v. Board
   of Education, 347 U.S. 483 (1990)" stops reading verified with a wrong
   year. A risk pass over the hardened branch (severity by likelihood, the
   lawyer-buyer lens) ranks the remaining orange items as exactly these two:
   the could-not-check fatigue a 3-case corpus produces, and the undisclosed
   parenthetical gap; everything else on the register lands yellow or green
   after this branch.
9. Per-claim quote attribution (D9). Attribute each panel quote to the claim
   span that contains it (the PR5a placement machinery already locates spans);
   check it only against that claim's sources; the panel groups by claim.
10. Contract anchor coverage expansion (the real 25-35% problem): percent
    anchors (interest rates, equity), enumerated-list membership (permitted
    assigns, exclusions), cross-reference resolution ("as defined in Section
    2.1"), and defined-term equivalence in values ("the Cap"). Each is a pure
    T0 detector plus a comparator, each lands dark behind its own tests, each
    moves real clause content out of untreated.
11. Docstring truth pass (D11) and the join-overlap guard (D10): exclude
    overlapping pieces from complete=True joins.
12. Single-process offline scoping (D12): scope the HF env forcing to the
    embedder load rather than the process, or document the side effect in
    CLAUDE.md.

## 5. What would make this truly special

The question a litigator actually asks before staking a Rule 11 signature is
not "did the tool check my brief" but "what exactly did it check, against
what, and what did it decline to check". Three changes move Cachet from a
careful demo to a tool a lawyer could defend relying on:

1. A coverage-complete certification. Today the artifact lists findings; it
   must also state the denominator: N statements, K checked (each against a
   named, fingerprinted source), M untreated and why, with the corpus scope
   and date for citation checks. Commit 5 starts this; PR 8 finishes it. A
   certificate that says "checked 9 of 40 statements; 31 carried nothing
   checkable; citations checked against a 3-case demo corpus" is one a lawyer
   can sign AROUND. A certificate that implies everything was checked is one
   that ends up attached to a sanctions motion.
2. A fabrication catch that can actually say "fabricated". Bounded-corpus
   honesty currently forces every miss to could-not-check, which is correct
   and also means the flagship catch cannot fire on the flagship problem.
   Ship the full offline citation corpus (CourtListener's citation index is
   redistributable; volume-reporter-page plus caption is a few GB, not the
   opinions), attest its completeness and as-of date in the manifest, and a
   404 against a complete index becomes the loud, defensible "no such case as
   of <date>" with the national-database caveat scoped to post-cutoff
   filings. That single data artifact converts the engine's most honest
   refusal into its most valuable verdict.
3. Verdict semantics stable enough to cite. The three-state fold plus the
   caption, duration, and topic rules are now load-bearing legal semantics.
   Pin them in a versioned VERDICT-SEMANTICS document (what "verified",
   "present", "could not check" each attest, with the exact comparator rules
   and their known blind spots), stamp the semantics version into the
   certification JSON, and treat any semantics change like a migration. A
   lawyer can then answer the only cross-examination question that matters:
   "what did the tool mean by verified, on the day you ran it".

## 6. Verify-chain results for this branch (Linux sandbox, 2026-06-09)

This branch was built and verified in a Linux arm64 sandbox (Python 3.10,
node 22). The repo targets Python 3.11+ and macOS; the differences below are
environmental and called out as such. Anything not runnable here is listed as
NOT RUN, never assumed green. Run the full chain on the Mac before merging.

Ran and green:

- ruff check + ruff format --check over ai, services, evals, tests, main.py,
  db.py, routes, api_models.py, benchmarks (ruff 0.15.16; the sandbox ruff is
  newer than the venv's and additionally surfaced a pre-existing duplicate
  test name, removed in the caption commit).
- python -m unittest over the documented verify-path list that imports
  cleanly on 3.10: 409 tests across test_ai_router, test_tutor_grounded,
  test_retrieval_hybrid/vector/fts, test_db_migrations, test_verify,
  test_verify_stream, test_quote_check, test_t1_selector,
  test_citations_eyecite, test_anchors, test_legal_sentences,
  test_offline_foundation, test_local_caselaw, test_deterministic_envelope,
  test_contract_verify, test_contract_verify_integration, test_zero_egress,
  test_demo_corpus, test_align, test_t1_calibration, test_t1_wiring,
  test_t1_dark_path: OK (1 unrelated skip). Plus test_phase0_foundation,
  test_phase0_batch_b, test_einstein_tutor, test_learning_os,
  test_memory_pressure, test_briefs, test_briefs_routes,
  test_retrieval_quote_heuristics, test_anchors_service,
  test_citation_quote_validation: OK.
- python -m benchmarks.t1_calibration: "DARK (not required)", exit 0.
- bash tests/test_watchdog_kill.sh: exit 0.
- script/generate-api-types.sh replicated (app.openapi() dump +
  openapi-typescript 7.13.0 from the repo's own node_modules): regenerating
  twice produces no diff. The regen also picks up the /api/vaults routes that
  landed on main without a regen.
- frontend typecheck (tsc --noEmit): clean.
- frontend lint (eslint src): clean.
- frontend vitest: src/features/verify, src/cachet, src/app, src/lib all
  green (188 tests). src/design-system passes test-by-test but exceeds the
  sandbox's 45-second per-command wall clock before printing its summary; it
  is untouched by this branch.

Environmental failures (not code defects, verified by reading the errors):

- tests.test_evals_runner: 2 errors from TestCase.enterContext, a Python
  3.11+ API; the sandbox runs 3.10.
- tests.test_t1_offline_model.test_uncached_model_fails_loud_without_a_socket:
  expects the offline-cache RuntimeError; the sandbox has no `transformers`
  installed (2+ GB with torch), so the import-guard RuntimeError fires
  instead. Same fail-loud contract, different message.

NOT RUN (requires the macOS toolchain or committed baselines):

- corepack pnpm build:macos (writes the bundled app.new.html).
- ./script/build_and_run.sh --verify.
- python -m benchmarks.phase0 --compare data/benchmarks/baseline.json.
- swift test --package-path macos-app.
- The pre-commit hook itself (it shells into ./.venv, a macOS virtualenv);
  every commit on this branch ran the hook's checks manually (ruff format
  --check, ruff check, eslint on staged files) and says so in its message.

Security review of the branch diff (manual, the built-in skill's embedded
shell is unavailable in the sandbox): no new imports beyond internal modules
and re; no new network, subprocess, eval, or deserialization surface; new
detail strings render through JSX text nodes (no innerHTML); the zero-egress
suite re-run green on the changed code; probes confirm the caption-mismatch
catch is not weakened by the unconfirmed state and the coverage block cannot
appear for a non-deterministic provider.
