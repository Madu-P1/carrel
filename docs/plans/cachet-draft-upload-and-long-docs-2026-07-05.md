# Plan — Verify uploaded documents, and make long documents first-class (2026-07-05)

**Goal (operator ask):** users can upload a DOCUMENT as the draft under
verification (not just paste text), and both drafts and sources can be very
long — end to end, engine to UI — with no honesty regression.

**Relationship to existing plans (compose, never duplicate):**
- `docs/plans/cachet-large-source-retrieval-2026-07-04.md` (task **L1**,
  `[REVIEW]` in `.claude/forge.engine.tasks.md`) already designs the kernel's
  large-SOURCE math: a provably-superset candidate index replacing the
  O(draft×source) scan, gated on property tests P1–P4. This plan ADOPTS L1 as
  its kernel leg and does not redesign it.
- `docs/plans/cachetverify-frontend-adoption-and-backend-2026-07-03.md` is the
  website; untouched here. This plan is the APP (frontend/src/cachet + routes/
  services + cachet_verify), where real verification runs.

**The invariant that outranks everything:** no false green, no false
accusation. A `could_not_check` is always preferred. Every step below lands
green on the full verify chain or it does not land.

---

## 0. Grounded current state (verified in repo, 2026-07-05)

1. **Sources** upload via `POST /api/documents/upload` → the ingestion
   orchestrator (`services/ingestion/`): extension-routed extraction (PDF via
   the PDFKit+Vision bridge with OCR, DOCX/MD/TXT via the docling/parser
   path), stored + retrievable. Mature, tested.
2. **Drafts** have NO upload path anywhere. The Lectern is a textarea; the
   engine APIs (`/api/verify`, `/api/verify/stream`, `/api/attest`) accept
   `draft: string` only.
3. **App verify path** (`services/verify.py` deterministic envelope): claim
   extraction per sentence, per-claim checks against retrieval-scoped
   clauses, SSE streaming per claim. No draft-length ceiling of its own; cost
   is linear in claims. Smoke-proven at 7 claims / 246ms.
4. **Kernel attest path** (`cachet_verify.adapter`): `_too_large(draft_sents ×
   source_sents) > 4_000` → honest refusal. A 1,000-sentence draft against a
   100-sentence source refuses TODAY (100k pairs). L1's candidate index turns
   this into candidates-per-claim, which fixes the long-DRAFT dimension of
   attest as a corollary — but only the source dimension is in L1's test plan.
5. **Frontend at scale:** the read-back renders one node per sentence run
   (a 10k-sentence draft is a DOM explosion); the composer textarea holds the
   whole paste; the findings rail renders every noted claim.

---

## 1. The honesty law for uploaded drafts (decide first, everything follows)

A PDF/DOCX draft is not text; extraction is lossy (OCR, tables, headers,
hyphenation). The trap is verifying bytes the user never sees, or showing a
read-back that differs from what was checked. The law:

> **Cachet verifies exactly the extracted text, shows exactly the extracted
> text, and says exactly that.** The certificate names BOTH artifacts: the
> original file's SHA-256 and the extracted text's SHA-256, plus the
> extractor identity/version. The claim is never "we verified your PDF"; it
> is "we verified this extraction of your PDF, here is the hash of each."

Consequences (each becomes a test):
- The read-back IS the extracted text. What you see marked is what was
  checked, byte for byte (the existing draft-echo/stale-draft logic already
  compares trimmed text; it keeps working because the extracted text IS the
  draft).
- Empty/failed/low-yield extraction → an explicit refusal register on the
  Lectern ("The document could not be read as text..."), never a silent empty
  verify. Threshold: extraction yielding < 1 sentence refuses outright.
- Scanned-PDF OCR is allowed (the bridge already OCRs) but the certificate's
  extractor field says so (`pdfkit+vision-ocr`), because OCR fidelity is a
  materially different trust statement than embedded text.
- The wire/certificate change is ADDITIVE ONLY (ADR-0015): new optional
  fields `draft_file_sha256`, `draft_extractor`; existing `draft_sha256`
  stays the extracted-text hash (unchanged meaning).

---

## 2. Track D — the draft is a document (5 steps, each shippable)

### D1 — Backend: draft extraction endpoint (reuse, don't rebuild)
`POST /api/verify/extract-draft` (multipart file, same accept set as sources:
.pdf/.docx/.txt/.md): runs the SAME ingestion extraction path as sources but
does NOT store a document — returns `{draft_text, draft_file_sha256,
extractor, chars, sentences}` (hash computed server-side over the raw bytes).
Stateless: nothing persisted, nothing leaves the machine (loopback-only like
every route). Refusal shape for unreadable/empty files with a concrete
reason.
- *Why a separate endpoint, not documents/upload:* a draft is not a source;
  it must not enter the retrieval corpus (a draft that becomes a source can
  verify against itself — a structural false green).
- **Gate:** unit tests with fixture PDF (embedded text), fixture scanned PDF
  (OCR), DOCX, MD; empty-file refusal; the self-verification trap test
  (extracted draft never lands in `documents`/retrieval); zero-egress suite
  still green.

### D2 — Wire contract: provenance rides the run (additive)
`/api/verify` + `/api/verify/stream` accept optional `draft_provenance:
{file_sha256, extractor}` and echo it in the response;
`buildCertification`/kernel certificate carry the two new optional fields.
Seal Bench + standalone verifier display them when present (additive render;
absent = today's behavior byte-identical).
- **Gate:** certificate round-trip tests (issue → seal → verify intact with
  the new fields; tamper the file hash → seal breaks);
  `verifierStandalone.test.ts` extended fixtures; conformance corpus
  UNCHANGED for the no-provenance case (proves additivity).

### D3 — Lectern: "Verify a document" affordance
The composer's pill row gains the draft-side counterpart of the record pill:
drop/choose a file → D1 extracts → the sheet fills with the extracted text
(read-only "document mode" with filename + both hashes in a mono caption +
"Edit as text" to unlock into the normal paste flow, which drops the file
provenance since the bytes changed — honesty rule §1). ⌘K verb "Verify a
document…". Same guard as the specimen: verify is gated while extraction is
in flight.
- **Gate:** component tests (document mode fills + locks the sheet, edit
  unlocks + drops provenance, failed extraction shows the refusal register,
  verify gated during extraction); the four-beat demo unchanged.

### D4 — Attest/exhibit parity
Sealing a document-draft run produces the exhibit with the file line
("Draft · report.pdf · sha256 … · extracted by …"). Shelf reopen re-hydrates
document mode read-only.
- **Gate:** exhibit fixture test + shelf round-trip test.

### D5 — Demo ammo (cheap, after D3)
A document-mode specimen: bundle the demo MSA-summary DOCX
(`demo/AI-Summary-Memo.docx` already exists) so the one-click demo can also
show "upload the AI's memo, watch it get checked". Reuses the specimen
pairing machinery + sync locks.

---

## 3. Track L — long documents end-to-end (6 steps)

### L1 — Kernel candidate index (EXISTS, adopt as-is)
The 2026-07-04 plan, unchanged: shingle index (quote-leg superset) + anchor/
topic index (contradiction-leg superset), union fed to the existing legs;
`_too_large` re-scoped to candidates-per-claim. Ship authority = its P1–P4
property tests (P1 verdict equivalence vs brute force, P2 direct superset
assertion, P3 100k-sentence source attests, P4 no catch weakened). Stays
`[REVIEW]`-gated; the review artifact is the P1–P4 run output.

### L2 — Extend L1's gates to the long-DRAFT dimension (small, critical)
L1's P3 tests a big SOURCE + small draft. Add the mirror properties:
- **P5:** 5,000-sentence draft × normal source attests every claim (no
  oversize refusal from draft size alone); per-claim candidate bound still
  refuses degenerate claims only.
- **P6:** parity corpus + the adversarial rotation (26 attacks) re-run
  through the INDEXED path — zero false greens, zero false accusations,
  catch-rate not below the 2026-07-04 baseline (15/15 in-distribution, 9/15
  OOD). This makes the session's own red-team battery the regression floor.

### L3 — App path at draft scale (measure, then bound honestly)
The envelope is already linear per claim, but claim extraction, placement
(`segmentDraft`), and quote-pool build are single-pass over the full text —
profile them at 1k/5k/20k sentences and set a pre-registered budget
(proposal: p50 ≤ 60s for a 500-page draft vs 500-page source, on-device,
streamed). Where the budget fails, fix the algorithm (never the honesty):
candidate-index reuse from L1, and stream claims in document order so first
verdicts land in seconds regardless of total length. If a hard ceiling must
remain, it is an EXPLICIT one with the honest register ("N of M statements
checked; the rest were not attempted") — never a silent truncation.
- **Gate:** a `benchmarks/long_doc` benchmark checked into CI with
  fail-on-regression, mirroring `benchmarks/phase0`.

### L4 — Frontend at scale (the part users feel)
1. **Read-back virtualization:** above a threshold (~1,500 sentence nodes),
   window the read-back (render visible paragraphs ± overscan; findings rail
   and superscript anchors unaffected because placement data is already
   computed). No virtualization library — a windowed slice on scroll, same
   zero-dependency discipline as the rest.
2. **Findings rail capping, honest:** worst-first with "showing the worst 50
   of N findings — every finding is in the exhibit and the tray" when N is
   huge. Never silently truncate (the no-silent-caps rule).
3. **Composer at scale:** past ~200k chars, pasting flips the sheet into
   document mode automatically (the D3 read-only surface) — a textarea is the
   wrong editor for a 500-page brief, and document mode is already the
   answer.
4. **Streaming UX:** the docket progress line gains "claim N of M" totals from
   the claims event (already on the wire) so a 30-minute run reads as a
   procession, not a hang; Stop-the-check already exists.
- **Gate:** vitest for windowing math (edge: findings click scrolls to an
  unrendered sentence → window jumps correctly); Lighthouse/interaction smoke
  on a 5k-sentence fixture; bundle budget respected (headroom is ~1.2%,
  virtualization must be ~free — plain slice logic, no dependency).

### L5 — Attest/daemon surfaces inherit L1+L2
`/api/attest`, the daemon, and the CLI get the same candidate-index path (it
lives in the adapter, so this is verification not new code): add one
end-to-end fixture per surface (long doc → sealed certificate → Seal Bench
intact).

### L6 — Long-doc adversarial rotation (close the loop)
Extend the `.claude/adversary` rotation with a long-document family: a
planted alteration at sentence 4,900 of a 5,000-sentence draft; a
contradiction buried in page 400 of the source; a verbatim quote straddling
the old ceiling boundary. The honesty floor (0 false greens / 0 false
accusations) is the pass bar, per the standing adversary discipline.

---

## 4. Sequencing (dependency-honest, each step lands green)

```
Week 1: D1 → D2 → D3            (draft upload usable end-to-end; demo-visible)
        L2 written alongside     (property tests exist BEFORE the kernel change ships)
Week 2: L1 executes against P1–P6 (Forge task, REVIEW-gated, ship = property tests green)
        L5 fixtures              (attest/daemon inherit)
Week 3: L3 profile + budget → fixes → CI benchmark
        L4 UI virtualization + honest capping + auto document-mode
Week 4: D4, D5, L6 rotation      (polish + the standing red-team extension)
```

Parallelism: Track D never touches the kernel; Track L never touches the
upload surface. They merge only at D2/L5 (certificate fields) — sequenced D2
first so L5's fixtures include provenance.

## 5. The no-mistakes discipline (what "perfect" means operationally)

1. **Property tests precede kernel changes** (L2 before L1 ships). The ship
   authority is deterministic tests, not judgment.
2. **Every wire/certificate change is additive-only** with a proves-additivity
   test (old fixtures byte-identical).
3. **The adversarial batteries are regression floors:** parity corpus 15/15,
   rotation 26/26 floor-clean, plus the new long-doc family — run on the
   indexed path before merge.
4. **Honest ceilings only:** wherever a bound survives, its refusal names the
   bound and the recovery ("split it", "N of M checked"), and the UI carries
   the same register. No silent truncation anywhere (rail, read-back,
   benchmark).
5. **Full chain per step:** typecheck, lint, vitest (incl. phantom-class,
   drift, sync locks), ruff, the 45-suite unittest leg, zero-egress, swift,
   build:macos, benchmarks with fail-on-regression.
6. **Kill criteria:** if L1's P1 equivalence cannot be made deterministic, the
   index does not ship and the ceiling stays (honest refusal beats a fast
   maybe). If OCR extraction fidelity proves too poor for a trustworthy
   read-back on scanned PDFs, D-track ships for embedded-text documents and
   scanned PDFs refuse with "this document needs OCR review" — a scoped
   product truth, not a failure.

## 6. Open items routed elsewhere
- The Lectern `/verify`-vs-`/attest` wiring note in the L1 plan (its "L0") is
  superseded by the observed behavior (the app path segments claims
  correctly); re-verify when L5 lands and delete the stale note.
- The website plan's kernel-extraction stage (its Stage 1) would let the
  daemon/CLI ship the same long-doc capability outside the app; unaffected by
  this plan, benefits from it automatically via the adapter.
