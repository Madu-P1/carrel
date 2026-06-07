# Cachet local-verification architecture and sequenced-demo plan

Date: 2026-06-05
Method: 30-agent fan-out research workflow (code inventory + 2026 ecosystem research +
adversarial verification of every load-bearing technical claim) plus first-party code grounding.
Companion to `docs/notes/2026-06-05-cachet-market-analysis.md` (market verdict) and ADR-0008/0009.
Every external claim below is marked CONFIRMED / UNCERTAIN / UNKNOWN from the verification ledger
at the end. Do not restate an UNCERTAIN claim as fact.

## Headline decision

Make the deterministic core the product and the local guarantee. Make the LLM an optional,
clearly-labeled assistive tier that is OFF in the demo.

- Litigator opener: 100% deterministic catch. Case-existence lookup against a bundled local
  SQLite, plus verbatim quote check. No model and no network in the live path. The drama is the
  deterministic refusal.
- Contract close: 100% deterministic. Local hybrid retrieval over the user's own contract, plus
  verbatim quote check. Zero external corpus, zero LLM, airplane-safe with today's code.
- Holding-match (proposition support) is the only LLM call. It is roadmap, routed to Apple
  Foundation Models or MLX when present, always rendered as "proposition not confirmed," never a
  hard true/false verdict.
- Prove offline behaviorally (airplane mode + live network monitor + no outbound code in the
  verify path). Do NOT prove it by stripping the network entitlement, because WKWebView
  structurally requires that entitlement just to render the UI (CONFIRMED). Structural proof
  (a split GUI shell with no network client) is roadmap.

Why this is correct: it makes the "no cloud asterisk" guarantee true today for the demo, because
the catch needs neither a model nor a network call. That is exactly the company-ending risk the
market analysis named.

## The strongest counter-argument, tested

Counter: do not go truly local. Use a zero-data-retention / no-training enterprise API tier and
call that "private." It is a fraction of the work and the quality is far higher. Most regulated
counsel's real requirement is contractual (no-retention, SOC2, BAA), not literally air-gapped.

Test: it sharpens the answer but does not overturn it.

1. Structural beats contractual for this buyer. "The document never leaves the machine" is a
   categorically simpler and stronger story to a GC than "trust our vendor's retention clause."
   The Heppner ruling (SDNY, Feb 2026; case basics CONFIRMED) denied privilege for outputs run
   through public consumer Claude, citing data retention among its grounds. The confidentiality
   concern that bites regulated counsel is real even though "local cures it" is an overclaim.
2. Moat. An $11B incumbent already offers enterprise zero-retention and can match "private"
   trivially. It cannot easily match "runs on your laptop, provably offline" without abandoning
   its architecture. If the wedge is "private," the incumbent wins on quality. If the wedge is
   "local," it structurally cannot follow.

The discipline the counter imposes: the local guarantee must be REAL and PROVABLE, because the
moment it is "local with a cloud asterisk," the enterprise-cloud incumbent wins on quality and the
only structural advantage is gone. The verified asterisks (trustd OCSP at launch, the WKWebView
entitlement, the Apple FM Private-Cloud-Compute ambiguity, the embedder first-run download) are
precisely what would sink the pitch, so the build sequence closes or discloses them FIRST.

## 1. Recommended local architecture

Deterministic core (reused verbatim from Carrel, all on-device, all CONFIRMED present in code):

- Storage and retrieval: SQLite + FTS5 + sqlite-vec, RRF hybrid via
  `services/retrieval/typed_hybrid.py::search_typed_hybrid` (already default,
  `RETRIEVAL_USE_NODES=true`).
- Embedder: `BAAI/bge-small-en-v1.5` via fastembed ONNX, in-process, zero network at query time
  (`services/retrieval/embeddings.py:21`).
- Quote validation: `services/legal/quote_check.py` plus
  `services/retrieval/validators.py::verbatim_run_present` / `enforce_verbatim_substring`. Pure
  Python: NFKC, smart-quote fold, dash fold, whitespace collapse, exact substring, no fuzzy
  fallback. Degrades to "unplaceable," never to a false alteration.
- Case-existence: `services/legal/courtlistener.py`, driven through its existing injected
  `client=` seam against a bundled local SQLite of the demo's pre-vetted cases.

LLM surface (minimized, not demo-critical): exactly one optional call, holding-match
(`services/legal/case_verification.py:258` -> `request_tool_call`). Local provider is Apple
Foundation Models where available, MLX/Qwen3-4B-4bit as the macOS 14/15/Intel/locale fallback
(roadmap). Positioned as an assistive proposition-support signal, never the verdict.

Deterministic / LLM boundary per path:

Litigator path (offline opener):
1. `_CITATION_SHAPE` pre-filter [deterministic]
2. case-existence lookup vs bundled SQLite [deterministic]
3. verbatim quote check of any quoted run vs bundled opinion text [deterministic] -> THE CATCH
   (fabricated cite is a 404-equivalent; altered quote is an absent run). 100% deterministic.
4. holding-match LLM [optional, assistive, OFF in the demo]

A passed verbatim check must NEVER render as "supported." The verification REFUTED the claim that
verbatim presence implies proposition support (ellipsis can drop contradictory language and still
pass). Only a FAILED check is load-bearing.

Contract path (in-house wedge, business close):
1. retrieve clause spans for each AI claim via `search_typed_hybrid` over the user's own uploaded
   contract [deterministic, on-device]
2. verbatim quote check the claim language vs the retrieved clause [deterministic] -> attest
   "this language appears in Section X" or "does not appear / was altered." Zero LLM, zero
   external corpus, airplane-safe today. The tool attests grounding, never legal soundness.

Tradeoffs named:
1. Dropping holding-match from the live demo trades a richer "the source contradicts you" verdict
   for a provably-offline guarantee. Correct given cite-check is commoditized and the
   company-ending risk is the cloud asterisk.
2. Keeping bge-small (not upgrading to nomic-embed-text) trades MTEB points for zero re-index and
   zero schema migration. Correct for a small pre-vetted corpus.
3. Bundling only the demo's cases (not a full CourtListener mirror, whose metadata size is
   UNCERTAIN) trades general coverage for a demo that ships now and is honestly scoped.
4. Apple FM default trades universal availability (it needs macOS 26 + Apple Intelligence + a
   supported locale + a completed ~7 GB download, all CONFIRMED gates) for true zero egress.
   Mitigated by making the demo depend on no LLM at all.

## 2. Local-today vs roadmap honesty map (keyed to call sites)

| # | Call site | Status today | Minimal change to make it local |
|---|---|---|---|
| 1 | `courtlistener.py:350` POST citation-lookup | CLOUD (HTTPS + Bearer token) | Local lookup module with the same `CitationHit`/`CitationLookupResult` shape over a bundled SQLite, injected via the existing `client=` seam at `lookup_citations_in_text:299`. Relax the `courtlistener_no_api_token` guard for a sentinel token. No caller changes. |
| 2 | `courtlistener.py:555` GET opinion text | CLOUD | Serve opinion text from the same bundled SQLite via the same `client=` injection. Only needed if quote-vs-opinion or holding-match runs. |
| 3 | `case_verification.py:258` holding-match `request_tool_call` | CLOUD only if provider auto-resolves to Claude (`providers.py:392` picks Claude when `ANTHROPIC_API_KEY` is set; this kind is NOT high-stakes, so it is free to route to AFM/Ollama) | Pass `ai_provider=AFMClient()` to `verify_claims_for_cases` (seam at `:453/:504`), or set `CARREL_AI_PROVIDER=afm` and unset the key. For the demo, `enable_holding_match=False`. |
| 4 | `services/verify.py:251` `grounded_tutor_envelope` (`tutor.grounded_answer`) | CLOUD, HARD. `providers.py:99 ensure_provider_allowed` raises for any provider != claude on this kind | THE REAL BLOCKER for the existing draft flow. The contract path must NOT route through `grounded_tutor_envelope`. Add a new deterministic contract-verify route calling `search_typed_hybrid` + `check_quote_against_sources` directly. New request_kind `contract.clause_attest`, kept OUT of high-stakes (no LLM). |
| 5 | `embeddings.py:21` fastembed bge-small | LOCAL at query time, CLOUD on first-run download only | Add `cache_dir=<bundled>` + `local_files_only=True` (or pre-cache at build) and pin the version. One line. Until then a fresh machine in airplane mode fails at first embed. |
| 6 | `quote_check.py` + `validators.py` verbatim checks | LOCAL, fully. Pure Python, no I/O, no model | No change. Cleanest reusable asset. For contracts prefer `enforce_verbatim_substring` (case-preserved, no fuzzy fallback) over `validated_citation_quote` (lowercases, 0.95 fuzzy floor tuned on study notes). |
| 7 | `services/retrieval/*` hybrid stack | LOCAL, fully. Zero HTTP anywhere | No change beyond the embedder cache (item 5) and guarding sqlite-vec presence: `db.py:152` degrades SILENTLY to BM25-only if sqlite-vec is missing. Make that fail loud in demo mode. |
| 8 | `ProvenanceBadge.tsx:10-15` + `certification.ts` | LOCAL for the artifact, but no local-vs-cloud axis and no source-document hash | Add `local_execution:bool` to `VerifyResponse`, a "local" badge variant, per-source SHA-256 (`source_hash` already on `DocumentListItem`), and a "no data left this device" attestation line. Do NOT flatten "claude" to "local" (that is the overclaim the audit research flags). |
| 9 | `providers.py:336 _afm_available` | GAP. Only checks the binary EXISTS, not that it was built with `-DCARREL_AFM` | A binary without the flag passes the check yet returns `foundation_models_unavailable` on every call (`main.swift:416`). Harden to a real availability probe. AFM is "local when present and capable," a roadmap guarantee, not a demo guarantee. |

## 3. Build sequence (test-gated, independently shippable, offline de-risked first)

- PR1 Embedder offline pin. Add `cache_dir` + `local_files_only` to the fastembed embedder and a
  build-time pre-cache; guard sqlite-vec presence (fail loud in demo mode). GATE: unit test that
  `embed()` succeeds with network disabled and that missing sqlite-vec raises rather than
  returning `[]`.
- PR2 Local case-existence backend. New `services/legal/local_caselaw.py` implementing the
  `lookup_citations_in_text` / `fetch_opinion_text` shape over a bundled SQLite (demo cases only);
  inject via the existing `client=` seam; accept a sentinel token. GATE: a real cite returns
  exists=True and a fabricated cite returns exists=False, both with zero httpx calls (assert via a
  forbidding transport).
- PR3 Deterministic contract-verify route. claim -> `search_typed_hybrid` over the user's
  contract doc_id -> `check_quote_against_sources` -> attest present / altered / unplaceable.
  Bypasses `grounded_tutor_envelope`; new request_kind `contract.clause_attest` (not high-stakes).
  GATE: verbatim claim attests "present," altered claim attests "altered," zero LLM and zero
  network calls.
- PR4 Litigator offline opener wired to PR2. Route `/api/verify` case-verdict path to the local
  backend when `CARREL_LOCAL_CASELAW=1`; `enable_holding_match=False`. GATE: integration test of
  the full opener (fabricated cite -> refusal) with a network-forbidding transport.
- PR5 Local provenance + audit artifact. Add `local_execution:bool` to `VerifyResponse`, a "local"
  badge variant, per-source SHA-256 + "no data left this device" attestation in
  `CertificationModel`/`CertificationExhibit`. GATE: frontend vitest on the badge variant and the
  certification builder; verify chain green.
- PR6 Airplane-mode harness + zero-egress test. A scripted test that disables the network (or
  installs a forbidding httpx transport globally) and runs both surfaces end to end, asserting
  zero external sockets. GATE: this test in CI. It is the structural proof that backs the live
  demo.
- PR7 (roadmap, not demo-blocking) AFM-default holding-match as assistive tier. Pass
  `ai_provider=AFMClient` explicitly; render a passed/failed holding-match as "proposition
  confirmed / not confirmed," never true/false; gate behind a real `-DCARREL_AFM` capability
  probe (not file-exists). GATE: holding-match routes to AFM with no Anthropic egress, and the UI
  never renders it as a hard verdict.

## 4. Demo script and reliability plan

Corpus (real, pre-vetted, refusal genuinely fires, not staged):
- Litigator opener: a one-page motion excerpt with (i) one real correctly-quoted federal cite
  present in the bundled SQLite, (ii) one fabricated cite that does not exist, (iii) one real case
  with an altered quote (a word changed or an ellipsis dropping a contradicting clause).
- Contract close: a real executed NDA/MSA (the user's own document) plus a short AI-drafted
  summary with three claims. Two whose language appears verbatim in a clause, one whose language
  does not appear (for example a fabricated "survives termination for 5 years" where the contract
  says 2).

Run of show:
1. Pre-stage, before the audience: machine in airplane mode (Wi-Fi and Ethernet off), a live
   network monitor (Little Snitch Network Monitor or macOS-native tooling) projected beside the
   app. Say: "Watch this monitor. If anything leaves this machine, you will see it."
2. Litigator opener: paste the motion. The real cite passes (deterministic existence + verbatim
   quote). The fabricated cite is refused ("could not confirm this case exists"). The altered
   quote is refused ("the quoted language does not appear verbatim in the source"). Emphasize:
   offline, the monitor is flat, the catch is a deterministic lookup, not an AI guess.
3. Pivot line: "Cite-checking is table stakes. Here is the part a cloud tool structurally cannot
   do."
4. Contract close: load the executed contract (their own confidential document). Paste the
   AI-drafted summary. Two claims attest "present in Section X," the third is refused. Emphasize:
   the confidential contract never left the machine. That is the Heppner-confidentiality point for
   regulated in-house counsel.
5. Audit artifact: open the Certification Exhibit (draft SHA-256, per-source hash, "no data left
   this device" attestation, flagged-items-first layout, attorney-attestation line). Print to PDF
   live.

Per-step latency budget: embed query ~50-150ms (bge-small, in-process); FTS5 + vec retrieval
<50ms; verbatim check <5ms; local SQLite case lookup <1ms; full litigator verdict render target
<1.5s; contract attestation render <1.5s. No LLM in the live path, so no 4-7s grounded-answer
envelope. If holding-match is ever shown, budget +1-3s and label it assistive.

Failure-mode handling:
- sqlite-vec not loaded: PR1 makes this fail loud pre-demo, never silent BM25-only.
- Embedder first-run download: PR1 pre-caches; rehearse on the exact demo machine in airplane mode
  the night before.
- A claim straddles two chunks: validators have no span-merge today; pre-vet the corpus so demo
  claims sit within one node. Multi-clause merge is roadmap.
- Distinguish "refusal" (honest scope) from "could not check" (infra failure): render different
  copy. `claimDisposition.ts:180-199` collapses both to one "Could not verify" label today; the
  demo corpus must avoid the ambiguous path, and PR5 should split the labels.

Live airplane-mode proof: airplane mode toggled ON visibly + the network monitor showing zero
egress for the whole run. State the honest caveat to sophisticated reviewers: this is BEHAVIORAL
proof today (the app still holds `network.client` because WKWebView structurally requires it,
CONFIRMED), and STRUCTURAL proof (a split GUI shell with no network client + an XPC-isolated
backend) is roadmap. Do not present behavioral proof as structural proof. Note also that a
notarized binary's trustd may emit an OCSP check to ocsp.apple.com at launch (CONFIRMED): staple
the notarization ticket and pre-launch once so the monitor is clean during the verify run, and
keep the machine in airplane mode so even that attempt cannot connect.

## 5. The decisions most likely to be wrong

1. Bundle a local CourtListener SQLite snapshot for the offline opener.
   Why it may be wrong: the metadata-only corpus size is UNCERTAIN (the 2-4 GB and 5-10 GB
   figures have no primary source; only 324 GB opinions and "over 400 GB" total are confirmed).
   A "demo-cases-only" SQLite risks reading as a staged fake to a skeptical lawyer, the exact
   "honest, not curated-fake" bar. There is also a trust-boundary edit (relaxing the API-token
   guard).
   De-risk: scope the bundled SQLite to the demo's cases and SAY SO on stage ("this offline index
   holds the cases in this brief; the production index is the full public-domain CourtListener
   corpus"). Separately, pre-build and time a metadata-only import from one real quarterly S3 dump
   to replace the UNKNOWN size with a measured number before committing to general coverage. Until
   measured, full-corpus offline is roadmap, not demo. Confirm CourtListener's bulk-data terms
   before relying on redistribution (the underlying US opinions are public domain; the compilation
   terms are UNVERIFIED here).

2. Make holding-match non-load-bearing and drop it from the live demo.
   Why it may be wrong: the "the source contradicts your claim" moment is what holding-match
   provides; a purely deterministic existence + verbatim demo may feel like a spell-checker to
   lawyers who paraphrase holdings rather than quote them. The verification REFUTED
   "verbatim + retrieval is sufficient," so paraphrased-but-wrong propositions slip through a
   deterministic-only check.
   De-risk: pre-vet the corpus so the catches are the kind deterministic checks nail (fabricated
   cite, altered/ellipsis quote), which are visceral and unarguable. Keep holding-match behind a
   flag as an assistive "proposition not confirmed" signal for Q&A, routed to AFM when present,
   never a hard verdict. Validate with the Harvey persona and the mid-June lawyer interviews
   whether paraphrase-catch is demanded enough to pull holding-match into v1.

3. Default the local LLM to Apple Foundation Models for the roadmap holding-match.
   Why it may be wrong: AFM's availability gates are severe and CONFIRMED (macOS 26 + Apple
   Intelligence + supported locale + a completed ~7 GB download that is NOT pre-bundled with the
   OS), and `_afm_available` only checks binary presence, not the `-DCARREL_AFM` build flag. On a
   fresh or wrong-locale machine AFM is simply unavailable, and the binary may pass the check yet
   fail every call. Apple FM may also have a Private Cloud Compute path the developer API does not
   expose (UNCERTAIN), which would itself be a cloud asterisk.
   De-risk: keep AFM off the demo's critical path entirely (the demo is deterministic). For the
   roadmap path, harden `_afm_available` to a real capability probe at startup, ship
   MLX/Qwen3-4B-4bit as the bundled fallback for non-AFM machines, and benchmark the chosen model
   on the actual demo hardware before relying on its latency (the tokens/sec figure is UNKNOWN).
   Confirm whether `SystemLanguageModel.default` can ever route to Private Cloud Compute before
   calling the AFM path "zero egress."

## Verification ledger (assert only the CONFIRMED column)

CONFIRMED:
- Apple FM on-device model is ~3B params, 2-bit QAT mixed precision.
- CourtListener bulk data: bzip2 CSV, quarterly (last day of Mar/Jun/Sep/Dec), public S3.
- Quote-verbatim checking is 100% deterministic; Carrel already implements it in `quote_check.py`
  and `validators.py::verbatim_run_present`.
- WKWebView in a sandboxed macOS app requires `network.client` even to load `file://` assets;
  removing it breaks rendering. (This kills the naive "strip the entitlement" offline proof.)
- No current court rule requires a machine-readable audit artifact or a cryptographic hash; the
  artifact's value is defensive, not a mandated exhibit.
- Heppner (SDNY) case name, court, date, docket, and the Claude/Anthropic naming.
- NLI benchmark numbers: nli-deberta-v3-xsmall 91.64 SNLI / 87.77 MNLI-mm; base 92.38 / 90.04.

UNCERTAIN or REFUTED (do not assert without re-verification):
- "Apple FM is zero-download / always offline." Weights are a separate ~7 GB Apple Intelligence
  download, locale/region-gated; a Private Cloud Compute path may exist and is not surfaced by the
  API.
- "Removing network.client blocks all egress." System daemons (trustd OCSP at launch) egress
  outside the app sandbox regardless.
- "Verbatim + retrieval is sufficient for proposition support." Verbatim attests words appear, not
  that the surrounding claim is supported.
- Citation detection is done by CourtListener server-side via Eyecite + reporters-db, NOT by the
  local `_CITATION_SHAPE` regex (which is only a pre-filter). Offline detection needs Eyecite
  locally plus a local citation DB.
- Metadata-only CourtListener snapshot size (the 2-4 GB / 5-10 GB figures have no primary source).
- DeBERTa NLI latency on Apple Silicon (no primary source exists; no MLX port). Must be benchmarked
  on the demo machine.
- "30+ federal district courts require AI certification" conflates individual judge standing orders
  (~35-57) with district-wide rules (~4-6). Model-version disclosure is rare.
- Heppner "waived privilege" framing is wrong (privilege never attached), it was one of three
  independent grounds, and the court did NOT say local tools cure the defect.

UNKNOWN (open, must be measured or confirmed before relying on it):
- Exact bundled citation+metadata index size.
- Whether `SystemLanguageModel.default` can route to Private Cloud Compute.
- On-device NLI single-pair latency on the target Mac.
- CourtListener bulk-data redistribution terms (underlying opinions are public domain; compilation
  terms unverified).
