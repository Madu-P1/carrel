# Plan: Cachet verify-hero full port ("warm chambers around a cold record")

- Status: APPROVED for autonomous execution (operator-directed, 2026-05-29)
- Author: /plan-eng-review (interactive), founder-approved scope
- Relates: PR #90 (verify-as-hero slice 1, on main), [ADR-0008](../adr/ADR-0008-v2-pivot-validation-first-sequencing.md), [ADR-0006](../adr/ADR-0006-typed-node-defaults-on.md), `docs/plans/cachet-verify-hero-2026-05-29.md`, prototype at `prototypes/cachet-shell.html`
- Design source of truth: `DESIGN.md` (2026-05-29 scoped verify-mode entry) + the prototype

## 0. Read this first (for the autonomous routine)

This plan is **decision-locked**. The architecture choices in Section 3 were made in an
interactive review with the operator. Do NOT reopen them in proponent/adversary debate;
debate only the *implementation* of each PR, not whether to do it or which approach.

**Strategic-context flag (operator override of ADR-0008).** ADR-0008 sequenced V2
validation-first: run the T66 pilot on the EXISTING build, "build nothing new," keep the
polish queue paused. This plan deliberately builds the full verification surface *ahead of*
that validation gate. That is an operator decision made 2026-05-29. It is recorded here so a
fresh-context iteration does not treat the ADR-0008 pause as still binding for this work.
**Action item for the operator:** amend ADR-0008 (or write a short superseding ADR) so the
written record matches the decision. Until then, this plan is the authority for the verify
port; ADR-0008 still governs everything else.

## 1. What we are building

Port the `prototypes/cachet-shell.html` synthesis into the shipped Preact verify surface as a
real, full app shell. The synthesis is **one world, two registers, assigned by trust-zone**:

- COLD record (Exhibit) wherever the tool judges: the document body, the margin verdicts, the
  four checks, the register. Warm paper `#f6f2ea`, near-black ink, a single proofreader-oxblood
  `#7a2230` accent reserved for flags, neutral reading serif, mono citations.
- WARM chambers (Chambers) wherever the human acts and returns: the Shelf/home, the act of
  certifying, the wax seal, the export cover. Cream, a characterful Fraunces ceremonial voice,
  a brass note used ONLY on cert/seal.

The hero is the refusal ("cannot verify"), never a success celebration.

## 2. Invariants the routine must NEVER violate

These are product-defining. A PR that breaks any of these must be rejected by the audit gate,
no matter how clean the diff.

1. **Verify, never generate. The bright line.** Cachet never writes argument, never drafts a
   corrected cite, never auto-replaces flagged content, never has an "apply fix" / "accept
   correction" button (not even for mechanical typos). It shows the source of record and lets
   the human make every change in their own tool. Be the red pen, never the pen.
2. **No confidence percentages anywhere.** Enforced by `claimDisposition.test.ts`. A verdict is
   a finding, not a score. `api_models.py` has internal `confidence` floats; they must never
   surface on the UI.
3. **Supported is unmarked.** The absence of a flag is the pass. No green VERIFIED badge, ever.
4. **Warmth never touches a verdict.** Fraunces voice + brass are for the Shelf, the cert cover,
   and the seal only. The document body, the margin verdicts, and the register stay cold ink +
   oxblood. The single oxblood accent is for flags/attention; brass is for ceremony only.
5. **Holding-match and good-law are assistive, never the confident deterministic color.** A
   false-confident holding ends careers. `proposition_unsupported` and holding sub-lines render
   in the assistive treatment (pencil / "for your review"), distinct from the oxblood
   deterministic flags (`citation_not_found`, `claim_unsupported`, `quote_altered`).
6. **An unfinished verification must never read as a pass.** A dropped stream, a rate-limited
   cite, or any uncomputed check defaults to `could_not_check`, never `supported`.
7. **Migrations are the schema source of truth.** Never `ALTER TABLE` at startup.
8. **The Anthropic key never enters web storage, an HTTP body, or a log.** It flows web field →
   `WKScriptMessageHandler` → Swift → Keychain only.
9. **No em dashes, no AI-slop vocabulary in any UI copy or prose.** See `DESIGN.md` voice notes.
10. **Evals hold at baseline.** `evals-full` keeps `groundedness@8 ≥ 0.7` and
    `quote_validity ≥ 0.95`. Any engine refactor that moves these is a regression; block.

## 3. Locked architecture decisions

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| A1 | Streaming the per-cite "labor" | **Stream from inside the shared engine**, done via an extract-generator refactor | True per-cite progress; the labor must be real, not theater |
| A2 | Quote-verbatim check | **Verify the verbatim runs between declared edits** (brackets / ellipsis / `[sic]` are the author's edits, not flagged) | Catches material misstatement without crying wolf on proper Bluebook editing |
| A3 | API key storage | **Web Settings + native bridge to Swift-owned Keychain** | Keeps the designed Settings; signed Swift app is the only thing macOS Keychain trusts without ACL prompts |
| A4 | Claim → draft span alignment | **Server-side deterministic alignment (Python).** `services/legal/align.py` maps each claim to a draft offset by matching its own draft-quote span, else its citation quote, else `claim_text`, exact then fuzzy: reuse the `extract_draft_quotes` draft spans (regex `.start()`/`.end()`) and the `services/retrieval/validators.py` round-trip (`normalize_match_text`, `slice_original_span`, `fuzzy_quote_match`). Unplaceable claims fall to an "unplaced" tray; the frontend only renders the precomputed offsets. | Deterministic, reproducible, and unit-testable in the python battery; mirrors PR4's server-side `quote_check`; placement never mis-pins. Chosen over a model-emitted `anchor` field on `SUBMIT_GROUNDED_ANSWER_TOOL` (the documented alternative), which widens shared-engine blast radius, trips the evals-hold gate, and risks cry-wolf on a weaker signal. |
| A5 | Shelf persistence | `briefs` table stores `draft + fingerprint + response_json + cert_json + seal_state`; list renders from stored summary; open shows stored verdicts + a re-verify action | Local SQLite, single user, no auth; avoids re-verify just to render the list |

### A1 — the extract-generator refactor (highest blast radius; do it this exact way)

`grounded_tutor_response` / `grounded_tutor_envelope` are shared by tutor, verify, and evals.
Preserve their public contract exactly. Extract the body into a **sync generator**; the existing
function becomes a thin drain-to-completion wrapper.

```
_grounded_tutor_steps(payload)            # NEW sync generator, holds the real logic
    yield ("progress", {"phase": "extracting"})
    ... extract claims ...
    yield ("progress", {"type": "claims", "claims": [...]})
    for cite in cites:                    # the genuinely slow, sequential CourtListener + holding work
        ... resolve ...
        yield ("progress", {"type": "cite_verdict", "claim_index": i, ...})
    ... draft-quote-verbatim per quoted span ...
        yield ("progress", {"type": "quote_verdict", ...})
    yield ("result", envelope)

grounded_tutor_envelope(payload):         # SAME signature, SAME return value (tutor + evals unaffected)
    last = None
    for kind, p in _grounded_tutor_steps(payload):
        if kind == "result": last = p
    return last

verify_draft_stream(payload):             # the only new consumer
    for kind, p in _grounded_tutor_steps(payload):
        if kind == "progress": yield sse(p)
```

`POST /api/verify/stream` wraps the generator in FastAPI `StreamingResponse` (sync generator,
no async rewrite). Wire format must match the frontend `streamSse<T>` helper
(`frontend/src/services/api/streaming.ts`). The existing `POST /api/verify` stays for tests and
non-stream callers.

**Regression net:** a new test drains `_grounded_tutor_steps` and asserts the final result is
byte-identical to the pre-refactor `grounded_tutor_envelope` on fixtures, and `evals-full` must
hold at baseline. If the evals move, the refactor changed behavior; block and investigate.

### A2 — quote_check scope limit

`services/legal/quote_check.py` extracts quoted spans from the draft, parses each into
verbatim-runs + declared-edit markers, and requires each verbatim run to match the resolved
source text exactly (reuse the CourtListener opinion text already fetched for holding-match;
for loaded docs, the chunk text). New disposition kind `quote_altered` (deterministic flag,
oxblood, ordered near `citation_not_found`). **Stated scope limit in the UI:** it confirms the
words presented as quoted appear verbatim in the source; it does not judge whether an omission
distorts meaning. Grounding, not truth.

## 4. PR sequence (small, additive, independently shippable, verify-chain green at each step)

Trust-critical first, within the full scope. Each PR lands green on the full CLAUDE.md verify
chain or it does not land. Default PRs to draft; do not `gh pr ready` without the operator.

```
Lane B (design)   PR1 ─► PR2 ───────────────────────────► PR5
Lane A (engine)   PR3 ──────────────► PR4 (consumes stream) ┘ (PR5 consumes stream)
Lane C (persist)  PR6   (independent backend)
Lane D (native)   PR7   (independent Swift) + web Settings
Shared files: AppShell.tsx (PR5/PR6/PR7), VerifyView.module.css (PR1/PR2) → serialize or coordinate
```

### PR1 — Assistive vs deterministic split  [ships today; fixes a live safety bug]
- **Goal:** `proposition_unsupported` and holding-contradicts stop wearing the confident oxblood.
- **Files:** `frontend/src/features/verify/claimDisposition.ts` (add `DispositionTier "assistive"`,
  map `proposition_unsupported` to it), `VerifyView.tsx` (`tierBadgeClass` + `CaseVerdictLine`
  holding sub-line use the assistive treatment, not `caseMissing`), `VerifyView.module.css`
  (assistive style: pencil / dotted / "for your review", NOT oxblood).
- **Tests:** `claimDisposition.test.ts` asserts `proposition_unsupported.tier === "assistive"`;
  a test that holding `match=false` renders the assistive class, not the oxblood flag class.
- **DoD:** frontend typecheck + lint + vitest green; no other invariant touched.

### PR2 — Two-register tokens + certification (warm cover + cold register + human seal + tamper-evidence)
- **Goal:** the cert becomes the warm/cold seam; the human sets the seal; the seal cracks when
  the draft changes.
- **Files:** `VerifyView.module.css` (warm-chambers tokens: Fraunces voice, brass, chambers
  surfaces; cold-record refinements), `CertificationExhibit.tsx` (warm cover with Fraunces +
  attestation + seal-set action; cold register beneath; scored-fold seam), `certification.ts`
  (**upgrade `fingerprintDraft` to SHA-256** — FNV-1a 32-bit is too weak for a tamper-evidence
  property; the file already notes this upgrade path), seal-state logic (sealed vs cracked on
  fingerprint mismatch).
- **Motion:** seal-set (press + settle) and crack (draw + loss of luster), WAAPI, transform/
  opacity only, `prefers-reduced-motion` path. No new runtime motion library.
- **Tests:** seal-state unit test (fingerprint match → sealed, mismatch → cracked); cert
  component state tests; existing `certification.ts` tests stay green after the SHA-256 change
  (update fixtures).
- **DoD:** frontend chain green; cert exports via print as today.

### PR3 — Honest streaming verify (extract-generator + SSE)  [highest regression risk]
- **Goal:** real per-cite labor via A1.
- **Files:** `services/tutor.py` (extract `_grounded_tutor_steps`; envelope becomes drain
  wrapper), `routes/verify.py` (+ `POST /api/verify/stream`), `services/verify.py`
  (`verify_draft_stream`), `VerifyView.tsx` (consume via `streamSse`; labor inks in per
  `cite_verdict`).
- **Tests:** **CRITICAL** identical-output fixture test (drained generator == old envelope);
  `evals-full` at baseline (`groundedness@8 ≥ 0.7`, `quote_validity ≥ 0.95`); SSE event-sequence
  test; **CRITICAL** dropped-stream test (truncated stream → remaining cites `could_not_check`,
  never `supported`).
- **DoD:** full python battery + evals-full + frontend chain green. This PR runs the heaviest
  gate; do not shortcut the evals.

### PR4 — Draft-quote-verbatim check  [the cry-wolf surface]
- **Goal:** the new deterministic `quote_altered` capability (A2).
- **Files:** `services/legal/quote_check.py` (NEW), `claimDisposition.ts` (+ `quote_altered`
  kind, tier, order), wire `quote_verdict` into the stream + UI.
- **Tests:** the edge-case minefield is the point — legit `[t]he` cap → NOT flagged; ellipsis
  omission → NOT flagged; `[sic]` / `[emphasis added]` → NOT flagged; smart quotes / whitespace
  → NOT flagged; a real misstatement OUTSIDE the marks → flagged. This suite gates the PR.
- **DoD:** python battery + the quote_check suite green; scope-limit copy present in the UI.

### PR5 — Claim-span alignment + Margin / Workspace / Examination

Ships in two parts. **PR5a** is the mechanical, server-side alignment (trust-critical, lands
first). **PR5b** is the Margin / Workspace / Examination visual layout (atelier-built behind an
operator craft gate, **deferred** until the design pass is scheduled).

**PR5a (deterministic alignment, server-side; ships first).**
- **Goal:** locate each claim in the draft by deterministic offset (A4), so the margin has real
  coordinates to pin to. No model or prompt change.
- **Files:** `services/legal/align.py` (NEW, sibling to `quote_check.py`). Maps each claim to a
  draft offset by reusing the `extract_draft_quotes` draft spans (regex `.start()`/`.end()`) and
  the `services/retrieval/validators.py` round-trip (`normalize_match_text`, `slice_original_span`,
  `fuzzy_quote_match`), exact then fuzzy. Add a `placement` field
  `{char_start, char_end, placed, method}` to each verify claim verdict and an `unplaced` list to
  the verify response. The field is `placement`, not `anchor`: `anchor` collides with the
  flashcard `AnchorRecord` / `source_anchor_id` / `/api/anchors` surface.
- **Matching order:** each claim is placed by its own verbatim draft-quote span, else its citation
  quote, else `claim_text`. Ambiguous or no-match claims go to `unplaced`, never mis-pinned.
- **Tests:** `align` unit tests (exact, fuzzy, ambiguous → unplaced, no-match → unplaced); a test
  that each `placement` offset slices back to the claim's own text.
- **DoD:** python battery + frontend typecheck green; no shared-engine tool-schema or prompt
  change, so no `evals-full` gate fires.

**PR5b (Margin / Workspace / Examination layout; deferred).**
- **Goal:** the document-with-margin layout that renders the PR5a placements (no frontend
  alignment; it only paints the precomputed offsets).
- **Files:** new Workspace / Margin + Examination components, `AppShell.tsx` route.
- **Build:** atelier-led, with an operator craft gate before merge.
- **Tests:** component tests for margin placement + examination drill-in + scroll-to-source.
- **DoD:** frontend chain green; unplaced claims visibly fall to the tray, never mis-pinned;
  operator craft gate passed.

### PR6 — Shelf persistence + the Shelf/home
- **Goal:** the warm home + saved briefs (A5).
- **Files:** `migrations/NNNN_briefs.sql` (NEW, additive), routes (list/get/save/delete briefs),
  Shelf component + app-shell nav.
- **Tests:** migration test (`test_db_migrations` pattern); endpoint tests; Shelf component test.
- **DoD:** `test_db_migrations` + python battery + frontend chain green.

### PR7 — Settings + native Keychain key entry
- **Goal:** in-app key entry (A3); unblocks solo use beyond the supervised pilot.
- **Files:** web Settings component (warm chambers; key field), `macos-app` Swift
  `WKScriptMessageHandler` → Keychain write/read, feed key to backend at spawn; `AppShell.tsx`
  nav.
- **Tests:** Swift XCTest (the `EinsteinDesktopTests` scaffold) for the Keychain bridge; web
  Settings component test; a test asserting the key is never written to `localStorage` and never
  logged.
- **DoD:** `swift test` + frontend chain green; key-never-leaks test passes.

## 5. Failure modes (and where each is handled)

| Codepath | Realistic failure | Test? | Error handling? | User sees? |
|---|---|---|---|---|
| SSE stream | drops after k cites | CRITICAL test (PR3) | remaining → `could_not_check` | "verification interrupted, re-run" |
| CourtListener | 429 rate-limit mid-stream | PR3/PR4 | that cite → `could_not_check` (already in `claimDisposition.ts`) | "could not check, retry" |
| quote_check | false positive on legit `[...]` | PR4 suite | runs-between-edits logic | nothing (correctly not flagged) |
| engine refactor | subtle output drift | identical-output + evals | block on eval regression | n/a |
| seal | fingerprint collision | weak hash | **SHA-256 in PR2** | n/a |
| Keychain | ACL prompt | Swift owns it (signed) | feed backend at spawn | nothing |

**Critical gaps that MUST have a test before merge:** the dropped-stream-reads-as-pass case
(PR3) and the fingerprint strength (PR2). A silent unfinished-verification-as-pass is the one
disqualifying behavior.

## 6. Performance

CourtListener free tier is 5 req/min. A 40-cite brief, rate-limited, is 8+ minutes (existence +
a holding-match LLM call per cite), past the discovery's "under 2 min, or background + notify"
bar. The real streaming UX makes the wait honest. Two mitigations:
- **Citations cache** (table keyed by normalized citation; case existence does not change, so
  the same cite is checked once and reused across briefs). Additive, big win. Build alongside PR3
  or PR4.
- **Paid CourtListener tier** decision before the pilot scales. Operator cost call → TODO, not a
  blocker.

## 7. NOT in scope (deferred, explicit)

- Auto-replace / fix-suggestion / any generation (the bright line; never).
- Real digital signing / identity / auth on the cert (pilot uses name + date).
- Multi-user / cloud sync (local-first, single user).
- Notarization + solo distribution beyond the Keychain bridge (Phase 4).
- Embeddings-based semantic claim alignment (PR5 is anchor + fuzzy only).
- Corpus-search-for-replacement-authority (retrieval is allowed, but not pilot-critical).

## 8. What already exists (reused, not rebuilt)

The engine (`grounded_tutor_response`), the CourtListener client
(`services/legal/courtlistener.py`), holding-match, the engine's own quote validation, the
disposition taxonomy (`claimDisposition.ts`), the cert model + `fingerprintDraft`
(`certification.ts`), the verify route + service, `SourceInspector`, the `streamSse` /
`stream_claude_text` patterns, and the Swift `EinsteinDesktopTests` XCTest scaffold. This is a
re-skin plus three additive engine capabilities (streaming, quote-verbatim, alignment) plus
persistence and key entry. Not a rewrite.

## 9. Verify chain (every PR)

Run the full chain from `CLAUDE.md` before any merge. PR-specific heavy gates: PR3 must run
`evals-full` + the identical-output test; PR6 must run `test_db_migrations`; PR7 must run
`swift test`. The fast pre-commit hook is not a substitute for the full CI chain.

## 10. Arming the autonomous routine

1. Add the 7 PRs to the active queue (`AUTONOMOUS_WORK_PLAN.md` / `TODOS.md`) so `/carrel-build`
   picks them up in order, trust-critical first.
2. `rm .claude/HALT` (worktree and main-repo copies) — a HALT file is currently present from an
   interactive session and will stop the routine immediately if left in place.
3. Launch per `CLAUDE.md`: `./script/start-autonomous.sh /carrel-build` (and the watchdog).

The routine reads this plan + `TODOS.md` at the top of every iteration; this plan is the
authority for the verify port. Halt anytime with `touch .claude/HALT`.
