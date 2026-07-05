# Cachet product-upgrade program (2026-07-05)

Status: PLAN, operator-directed ("forget the Lebanon gate; upgrade the product").
Inputs: a cold-eyes legibility audit of cachetverify.com + the demo runbook + the
companion pitch, and a full product-upgrade mine across app, companion, and site.
Both reports archived in the session scratchpad; key findings registered here.

## The diagnosis: why people don't understand or aren't impressed

1. **The hero says nothing.** The site opens with a wordmark and "Verify before
   you publish" — no noun, no villain. The meta description ("The independent
   check on AI-drafted work. Cachet verifies every citation, quote, and figure
   against your sources, and says plainly what it cannot confirm") is better
   than anything visible on the page, and it never appears on screen.
2. **Biography before product.** The founder story is the first content section;
   a stranger holds it in suspense about an unnamed product.
3. **The best line is buried.** "AI invents citations. You sign them." is the
   sharpest sentence in the company and sits third, behind a scroll animation.
4. **The demo's climax is a shrug.** The fabricated case in Beat 1 renders
   "COULD NOT VERIFY" — the *same label* as the honest refusal. The audience
   cannot tell a catch from a shrug. The jaw-drop beat (four CONTRADICTED
   verdicts with receipts) runs third, after opinions have formed.
5. **The one-click specimen anticlimaxes.** It verifies against no record, so it
   returns a wall of could_not_check (craft-pass item 3, already known).
6. **The identity split.** The site's primary CTA is "Start writing" → /journal
   (a publishing platform); the north star is an attestation engine. A stranger
   who is confused is reading correctly.
7. **The stakes are missing.** Sanctions-despite-vendor-tools (Lacey, Farris,
   Stanford 17–33%) appear on no stranger-facing surface, so "doesn't ChatGPT
   already check itself?" is never answered.
8. **The moat is invisible.** Zero-egress, determinism, and the reproducible
   certificate are told, never shown.

## The 10-second pitch (candidates that pass the dinner-party test)

- "Spell-check catches typos. Cachet catches AI fabrications — it reads the
  AI's draft against your actual documents and flags every changed number,
  fake quote, and invented court case before your name goes on it."
- "Lawyers keep getting fined for filing AI briefs citing cases that don't
  exist. Cachet is the pre-flight check: it verifies every citation and figure
  against the real record, on your machine, and hands you a sealed certificate."
- "When AI writes something important, someone has to check it — and it can't
  be the AI grading its own homework. Cachet is the independent checker."

## The program, ranked by impressiveness-per-week

**Week 1 — the demo stops underselling itself (all display work, no kernel):**
1. Specimen→record pairing: one click now produces verified quote + struck
   figure + caught fake cite + one honest refusal (craft-pass item 3). 1–3 d.
2. The reveal package: verdict hierarchy (stamped-judgment headline), docket
   streaming line, and the denominator line everywhere — "Checked 47 anchored
   facts · 3 altered · 12 could not check". 2–3 d.
3. Split the catch from the shrug: "No such case in the record (complete as of
   <date>)" must never wear the same label as "withheld — no anchor". Reorder
   the demo: contradictions first, refusal as the closer. 1–2 d.
4. Wifi-off theater, real: "PROVIDER: DETERMINISTIC · LOOPBACK ONLY · 0 NETWORK
   CALLS" on the verdict surface + kill-wifi-on-camera beat. 1–2 d.

**Week 2 — the site sells what exists:**
5. Homepage reorder: villain hero ("AI invents citations. You sign them."),
   meta-description sentence as subhead, "Watch it catch a fake" button into
   the existing /demo prefilled with a sanctions-style catch; founder story
   below the product; journal/forum out of the pitch path. 2–4 d.
6. Stakes strip: sanctions-despite-vendor-tools band (Lacey, Farris, Stanford
   17–33%) — answers "doesn't ChatGPT check itself?" in one block. 2–3 d.
7. Sanctions-record specimen: the Mata v. Avianca fabricated cites, caught
   live, offline, in two seconds. Public-record cites only; framing is "this
   class of error is mechanically catchable". 2–3 d.

**Weeks 3–4 — the artifacts become instruments:**
8. **Signed certificates (Ed25519 issuer identity).** The #1 power upgrade:
   converts the certificate from self-consistent document to attributable
   instrument; every other artifact upgrades the day it ships. Key custody
   gets the security human-gate. 1–2 wk.
9. Free public Seal Bench + `cachet verify-cert` CLI: drop a certificate in,
   watch it re-verify offline. THE distribution channel (billions plan §2.2).
   If shipped before #8, label plainly "integrity-sealed, not issuer-signed
   yet". ~1 wk.
10. Public paste-anything demo, honestly scoped (site/api/verify.py already
    runs the kernel server-side): loud scope copy + "your confidential
    documents belong on-device, not here". 2–4 d.

**The companion's killer moment (queue after the above):**
11. Inline strike: the extension strikes through the hallucinated citation
    inside ChatGPT/Claude while it's still typing, hover reveals the source
    clause. Highest gasp in the product. MUST inherit the tier-3 demotion law
    and miss-don't-guess role gate (badge-model.mjs); an inline accusation
    carries a higher confidence bar, not lower. 1–2 wk.
12. Session source attachment ("verify against THIS contract") via the bridge —
    the companion's version of fix #1; kills ambient could_not_check noise. ~1 wk.
13. First-catch-in-60-seconds onboarding + seal-from-the-panel. days.

**Ceiling raisers (sequenced behind the above):**
14. Safe greens per ADR-0013 + scoped refusals (the certificate becomes a
    clearing instrument, not a refusal ledger). ~1 wk.
15. PDF source ingestion on the lectern (EinsteinIngestionBridge exists);
    OCR low-confidence fails closed to scoped refusal. ~1 wk.
16. Publish the conformance corpus + refusal-honesty benchmark + a measured
    catch-accuracy number (publish the misses too). ~1.5 wk.
17. FR/AR numeric/date/money anchor pack (bounded, serves the GCC demo). 1–2 wk.
18. Windows/VDI daemon: stays priced and gate-triggered; write the connecting
    sentence into the pitch now (1 hour).

## Vocabulary unification (do alongside week 1)

One public vocabulary across engine wire, app, companion, site, runbook, and
certificate. Today: engine says verified/altered/could_not_check; site says
Traced/Contradicted/Could not verify; demo says SUPPORTED/COULD NOT VERIFY;
runbook says verified/unsupported. Anyone who sees two artifacts sees two
products. The wire schema stays frozen; only display copy converges.

## Honesty guardrails (none of the above weakens the contract)

- Public verifier on unsigned seals must say so; never imply issuer
  authentication that doesn't exist (ship #8 first if possible).
- Inline strikes inherit tier-3 demotion; a struck span in a user's own text is
  the one unforgivable error.
- Greens only from kernel-owned comparators; paper/ink register, never literal
  green (DESIGN.md).
- OCR/locale packs fail closed to scoped refusals.
- Publish benchmark misses with hits; a cherry-picked number is the brand's
  first lie.

## Registered same-day facts

- Demo runbook's two demo files are untracked in git (standing loss risk — fix).
- The kernel extraction (ADR-0014 step 3, Carrel side) landed today:
  `cachet_verify/engine/` now owns anchors/sentences/citations_eyecite/
  contract_verify/quote_check/validators/subject_labeler; old paths are
  sys.modules alias shims; self-containment locked by
  `KernelSelfContainmentTests`. Companion drift gates verified live and green
  (corpus + nearcopy byte-identical across repos).
- The website mirror (`packages/cachet-kernel`) syncs manually; its next sync
  must follow the new `cachet_verify/engine/` layout.
