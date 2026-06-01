# Cachet cross-professional discovery (16-persona fleet) — 2026-05-29

Provenance: a `Workflow` run (`wf_051c222c-9f9`) ran one rich discovery interview against
16 simulated high-stakes-confidential professional personas in parallel, then three synthesis
lenses (universal need, design language, wedge order), then a merged founder brief. The roster:
litigation attorney, corporate/M&A attorney, in-house GC, hospitalist, clinical psychologist,
auditor/CPA, M&A banker, buy-side analyst, tax attorney, management consultant, clinical
researcher, investigative journalist, HR lead, pharma regulatory affairs, licensed PE, enterprise
privacy officer/CISO.

DATA-QUALITY CAVEAT (do not skip): only 11 of 16 transcripts were substantive. Five broke
character or refused the roleplay (litigation attorney, M&A attorney, in-house GC, hospitalist,
buy-side analyst). The buy-side analyst, though out of character, produced the single most useful
strategic warning in the set (faithfulness-to-source is not soundness-of-inference). The
convergence across the 11 is "suspiciously clean" and likely reflects the model echoing the
founder's own priors. Weight the one real anchor interview (the hand-run litigator, Marcus, see
[[cachet-form-discovery]]) above the synthetic 11, and treat all stated willingness-to-pay as
near-zero signal until a real card is behind it. These are design hypotheses for the T66
validation test, not validated findings.

Lens sizes: need 28k chars, design 24k chars, wedge 20k chars. Raw lenses + transcripts live in
the workflow subagent dir for this session; this note preserves the merged brief.

---

# CACHET — Founder Brief: The Cross-Professional Verification Layer

## 1. The cross-professional thesis (three sentences)

Cachet is the independent check a professional runs on AI-touched work before their name goes on
it: it takes a finished document, tests every claim against sources the user controls and keeps
local, shows the receipt for each verdict, and is loudest about what it could not confirm. It is
for every credentialed professional who carries personal liability for a fluent, confident,
plausible falsehood, because that failure mode is identical across law, audit, medicine, finance,
research, and compliance. Lawyers are first not because they are the easiest door but because they
are the only profession where the engine that exists today is the entire job rather than half of
it: case law is an external, authoritative, public corpus already wired through CourtListener and
holding-match, and the fabricated-citation nightmare (Mata v. Avianca) is cleanly, fully
checkable.

## 2. The universal engine vs. what flexes per profession

**The universal core (build once, small on purpose):**

1. Corpus-in, local, user-controlled, date-stamped. Files never leave the machine. The corpus is
   user-supplied for everyone except lawyers; CourtListener is a litigation-specific adapter, not
   a template. Do not host or bundle "the authority" for any other profession; two compliance
   personas said a tool shipping its own copy of the law is a liability, not a feature.
2. Decompose into discrete claims, each carrying its attached citation.
3. Four verdicts, each with a one-click receipt: supported, quote-mismatch, supports-mismatch
   (real source, wrong proposition), could-not-confirm. The fourth state must split into "checked,
   found no support" vs "could not check, no source loaded." Collapsing those two is the exact
   lulling failure every persona feared.
4. The refusal is first-class and loud. Strongest cross-professional finding in the corpus. A
   silent pass on an unchecked claim is the one disqualifying behavior. No-backstop professions
   (tax, HR, research, regulatory) need it most; the litigator needs it least (a judge is a
   backstop).
5. No generation, ever. No confidence percentages, ever. Both are survival requirements. "94%
   verified" is named as instant-dismissal across the board.
6. One-click-to-source, where "source" is a span, not a page. Universally demanded, zero dissent.

**Certification artifact (universal skeleton):** a date, a document-version fingerprint, the
source set checked with provenance and date per source, and a prominent "could not confirm"
section. The not-confirmed list is the saleable object and the part that transfers liability. The
wall of green checks is not.

**What flexes per profession (do NOT build now; sequence each, gated on validation):**

- The "source" is radically heterogeneous: case law (public) for lawyers; trial balance and
  workpapers (numeric cells) for auditors; the data-room clause on page 40 for bankers; the
  patient chart plus the clinician's own notes (no external ground truth) for clinicians; audio
  timestamps and Signal messages for journalists; the adopted code edition for engineers.
  "Click to the exact page" must generalize to "click to the exact span" (PDF region, spreadsheet
  cell, audio timestamp, clause).
- Fourth-verdict reason codes swap per corpus: currency/superseded is the gem for tax and
  engineering, irrelevant to journalists/bankers. Over-inclusion (true but should not be present,
  e.g. another person's PII in a DSAR) is half the CISO's and HR's risk and is the inverse of a
  citation check.
- Numeric reconciliation is a SECOND engine, not an edge case. Five of eleven substantive personas
  (auditor, banker, regulatory, researcher, consultant) said their career-ending error is a figure
  that does not tie to source. Most-requested adapter, most likely to blow up scope. Ship it
  half-built and it is worse than not shipping it.

**The honest ceiling (from the only out-of-character voice, the buy-side analyst):** Cachet
verifies faithfulness-to-source, not soundness-of-inference. It would pass a
fabricated-but-verbatim-sounding thesis straight through. So "solve the lawyer's problem and the
rest follow" is FALSE as stated. What is true: solving the lawyer's problem proves the SPINE
(local, verify-not-generate, receipts, loud refusal), and the spine generalizes. The ENGINE
(citation-existence + holding-match against a public corpus) does NOT. The rest follow only if you
build a new corpus connector and, for the numbers professions, a reconciliation capability. That
is a roadmap, not a network effect. Kill the internal story that the others come for free.

## 3. Design language: lawyer-grade vs. DESIGN.md, resolved

Recommendation: ship a sealed, document-grade "verify" visual mode scoped to the verification
route only. Do not touch DESIGN.md's defaults or the study surface. Defer any whole-app rebrand
until after the T66 validation verdict.

The split-personality risk (a serious skin bolted onto a consumer-study app reads as a costume on
a toy) is real, but a full pre-validation rebrand is the wrong remedy: it is an expensive,
hard-to-reverse bet placed before the validation it depends on, which is exactly the "spent the
budget on the wrong thing" signal these buyers distrust. The seam is neutralized by WORKFLOW
ISOLATION: the verification path is entered, lived in, and exited as a self-contained, full-bleed,
document-grade environment. A sealed room reads as intentional; a half-painted hallway reads as a
costume. This is ADR-0008 validation-first, applied to design.

Two sharpening findings:
- The aesthetic consensus is partly an echo. Eleven fields converging precisely on the founder's
  own DESIGN.md instinct is statistically suspect. Build the trust aesthetic because the one real
  human and the architecture support it, not because the synthetic vote was unanimous. Watch T66
  for users who shrug or who want the color-coding the spec rules out.
- Everyone hates the green, nobody hates a muted red. "Supported" is the unmarked default; the
  absence of a flag is the pass. Reserve all chromatic energy (one grave accent, a proofreader's
  oxblood, not stoplight red) for what needs human eyes. A green VERIFIED badge is the single most
  dangerous thing the tool could show: it invites the user to stop thinking and it overclaims (the
  tool verified grounding, not truth).

Concrete first step (one additive, reversible PR): add a scoped `verify` token layer (warm
paper-white surface, near-black ink, single oxblood accent, serif body, mono/tabular numerals for
citations and figures), applied only to the verify route. Re-render verdict states: kill the green
checkmark and any pass-rate hero, make "supported" neutral/unmarked, promote `unsupported_spans`
(already in `services/tutor.py`) from side-output to headline, render the states with a receipt
one click from each flag, strip motion to two sanctioned uses (an honest working-indicator and
scroll-to-source), and make "cannot verify — not in the record" a full-weight state, never a
grayed-out error. Existing tokens unchanged, so the study surface and the full verify chain stay
green.

## 4. Wedge order and T66 recruits

- Stage 1 (now, zero new engine work): solo and boutique litigators. The only world where
  shipping equals done. Self-serve download and trial; certification PDF as the paid artifact;
  refusal as the headline state. Win on download-and-trial, not annual-minimum + procurement.
- Stage 2 (one corpus swap): tax attorneys first (corpus same shape as case law: fixed, citable,
  public; holding-match becomes the currency/superseded check the tax persona called his gem; 26
  USC 7216 is a criminal confidentiality statute that makes local-first even more load-bearing),
  then auditors for the citation-only slice. Do not promise numeric reconciliation yet.
- Stage 3 (real new engine, two parallel tracks): Numbers track (auditors full, bankers,
  regulatory: cross-document numeric reconciliation + private-corpus ingestion + possibly Part 11
  validation of the tool). No-external-corpus track (psychologists, researchers, HR, journalists:
  verify finalized prose against the user's own private set with no public ground truth; highest
  false-negative stakes, largest TAM, hardest product).
- Not a wedge: CISO and regulatory buyers (procurement gatekeepers, not self-serve). Sell THROUGH
  the CISO in Stage 2, not TO her in Stage 1.

T66 recruits beyond litigators: tax attorneys (2-3, highest priority, de-risks Stage 2), a solo or
small-firm auditor (1-2, to document the numeric-reconciliation gap with a real human), an
investigative journalist (1, cheap, stresses verbatim-vs-altered honesty). Exclude CISOs,
regulatory affairs, hospital clinicians (procurement-gated or Stage 3).

## 5. The one biggest risk and the one thing to refuse to compromise

Biggest risk: the first confident false-negative on something load-bearing. It threatens the
category, not a vertical. Trust in a verifier is non-linear; it collapses to zero on the first
betrayal and does not recover. Tune deliberately asymmetric toward over-flagging, and say so. A
dismissed false-positive costs two seconds; a false-negative costs a career and the product.
Close runner-up, not "later": plaintext-secrets-at-rest (the deferred Keychain work flagged in
CLAUDE.md). The local guarantee must survive a security team's teardown, not just the buyer's
belief. A procurement-killer for any buyer past the solo practitioner; deserves its own track
before T66 puts the tool in front of anyone with a compliance function.

Refuse to compromise on: the loud, first-class refusal and its honest scope boundary. Never let
the tool claim more than "this matches the source you gave me." It attests to grounding, never to
truth, never to soundness of reasoning. Keep the "could not confirm" section the emotional and
visual center of every output and every exported artifact.

## 6. Build inputs: first slice for the macOS verify-as-hero app (priority order)

Against the existing substrate (`/api/verify`, `VerifyView`, `unsupported_spans`,
`Citation.node_type`, the verbatim-quote validator, CourtListener case-existence, holding-match):

1. The four-verdict claim list with the refusal as the headline. Decompose a submitted document
   into discrete claims; render supported / quote-mismatch / supports-mismatch / could-not-confirm,
   with could-not-confirm split into "checked, no support" vs "no source loaded." Promote
   `unsupported_spans` to the top. The spine; nothing ships before it.
2. One-click-to-source span, side by side. Claim left, source right, no confidence score between.
   PDF page-region span for the litigation corpus to start. Co-equal with item 1.
3. The scoped `verify` visual mode (Section 3's PR). Document-grade sealed shell, kill the green,
   neutral "supported," oxblood only on flags, two sanctioned motions, no percentages.
4. The exportable certification artifact in its honest-skeleton form. Dated, document-version
   fingerprint, source set with per-source provenance and date, monospaced citations, headline is
   what could NOT be confirmed. Minimal but it must exist; willingness-to-pay concentrates on
   defensibility, not convenience.

Out of slice one, sequenced post-T66: numeric reconciliation, currency/over-inclusion reason
taxonomies, non-text (audio/table) spans, court-exhibit-grade PDF polish, any non-litigation
corpus connector. Hard constraint across every slice: no generation and no confidence percentages
anywhere.

Two caveats for the plan author: weight the one real anchor interview above the synthetic eleven
wherever they conflict; treat stated willingness-to-pay as near-zero signal until a real card is
behind it.
