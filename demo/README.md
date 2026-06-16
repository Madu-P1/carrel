# Cachet demo: run of show

A pre-vetted corpus where the catch genuinely fires, verified by the real engine
in `tests/test_demo_corpus.py`. No staging: every verdict below — the four
catches, the one green, the refusals — is produced by the deterministic engine,
not scripted.

## Setup (the night before, on the demo machine)

- `CACHET_DETERMINISTIC_VERIFY=1` (no-LLM deterministic engine). PREFLIGHT, the
  single most important check: assert this is exported in the SERVING process, not
  just your shell. If it is unset, the stream endpoint the UI calls falls through to
  the LLM + CourtListener path, which egresses the draft (silently, if an
  `ANTHROPIC_API_KEY` is present). Fail the demo launch loud if the flag is unset.
- `COURTLISTENER_API_TOKEN=local` (sentinel; the bundled SQLite answers locally).
- `CACHET_REQUIRE_SQLITE_VEC=1` (fail loud if sqlite-vec is missing).
- Embedder pre-cached via `CARREL_FASTEMBED_CACHE_DIR` (MANDATORY: the contract
  close needs the local embedding weights; with the deterministic flag on, a cold
  cache fails LOUD with an offline error rather than downloading, so Beat 3 would
  show an error banner instead of the contradiction. Warm the cache once online).
- Ingest **only** `demo/contract-msa.md` so its clauses are in the `nodes` table.
  The contract close scopes to every `ready` document, so a stray leftover ready
  doc from a dry-run would join the comparison and could surface the wrong clause.
  Confirm exactly one ready document before the demo.
- Staple the notarization ticket; launch once online, then go to airplane mode.

## Beat 1 — litigator opener (offline, sub-second)

Paste `demo/litigator-motion.md`. Three checks fire, all offline:

- `Brown v. Board of Education, 347 U.S. 483` resolves from the bundled corpus:
  the case exists, and the verbatim quote ("Separate educational facilities are
  inherently unequal") matches the bundled opinion text. (Honest note: existence
  and the quote are verified; whether the opinion supports the broader proposition
  is the assistive holding-match tier, off by default.)
- The next sentence cites the same case but misquotes it as "separate facilities
  are inherently equal". The engine does not have the full opinion bundled, so
  instead of guessing it **REFUSES**: "Could not verify this quotation against the
  available opinion text." Narrate this as the refusal, not as an accusation: the
  tool will not call a quote fabricated unless it can prove it, and it never does
  here. (To turn this into a hard "altered quote caught", bundle the full Brown
  opinion; that is a roadmap step, not today's behavior.)
- `Marbury v. Carcosa, 999 U.S. 999` does not exist: **Citation not found** (the
  fabricated-cite catch), produced by a local lookup with the network monitor flat.

## Beat 2 — the pivot

"Cite-checking is table stakes. Here is the part a cloud tool structurally
cannot do."

## Beat 3 — contract close (the confidential document never leaves the machine)

Lead with what it CAUGHT. Load `demo/contract-msa.md`, paste
`demo/contract-ai-summary.md`. Frame first: everything here runs on this device,
no socket opens (the airplane-mode proof below) — the only reason a regulated
in-house team can run an AI tool on a live contract at all.

**The hero: four contradictions, caught cold, on-device.**

- "executed on March 11, 2024" vs the contract's March 11, 2023:
  **contradiction** ("The summary states March 11, 2024; Section 1 states
  March 11, 2023").
- "capped at $1,000,000" vs the contract's $500,000: **contradiction** ("The
  summary states $1,000,000; Section 8 states $500,000"), pure arithmetic, zero
  ML.
- "an exclusive license" vs the contract's non-exclusive Section 3 grant:
  **contradiction** ("The summary states exclusive; Section 3 states
  non-exclusive"). One word, and it reverses who else can use the Software.
- "governed by New York law" vs Section 14's Delaware choice of law:
  **contradiction** naming both jurisdictions. The moat in one beat: the contract
  sends disputes to NEW YORK COURTS (venue) but chooses DELAWARE law — an AI
  summary flips the two, and the engine is not fooled.

**The one green — the rare place the engine WILL vouch.** The summary also says
the parties submit to "the exclusive jurisdiction of the courts of New York", and
the engine confirms it: **present**, a verbatim quote of Section 14. Set it beside
the line right above: same two words, "New York" — one RED (the choice of law,
wrong) and one GREEN (the venue, verbatim-correct). Narration: "it does not refuse
everything. It vouches when, and only when, the text is character-for-character
faithful to the contract — a green here was checked against the source, not
guessed." This is the single affirmed verdict on screen, by design, so the buyer
can calibrate what every refusal means.

**One line, do not dwell:** the two-year term — though it is in the contract —
reads **could-not-check** ("no matching passage found" on the current build): the
engine will not affirm a bare figure it cannot bind to its obligation (ADR-0013).
That restraint is what makes the green worth something. (PR #182 sharpens the
wording to "two (2) years appears in Section 12, but not independently verified";
deploy it AFTER interview #1, calibrated by whether the buyer found it clear.)

- "best efforts" carries no checkable anchor, so it is **untreated**: no verdict
  card, plain draft text. Do not point at this line.

## Beat 4 — the audit artifact

Open the Certification Exhibit: timestamp, draft SHA-256, per-source SHA-256, the
named "No data left this device" attestation, the on-device provenance badge,
flagged-items-first. Save as PDF and as JSON.

## Airplane-mode proof

Airplane mode on, network monitor projected and flat for the whole run. The
zero-egress guarantee is also a CI test (`tests/test_zero_egress.py`): both
surfaces run with real sockets forbidden. State honestly that this is behavioral
proof today; the structural split-shell proof is roadmap.

## Honest scope (state plainly, do not oversell)

- The quote check confirms a quote that is verbatim in the bundled opinion and
  REFUSES (could-not-check) when it is not, because the bundled opinion is not
  guaranteed complete. It never calls a quote "altered/fabricated". Attribution is
  same-sentence only, and a quote from a non-cited source is never checked. No
  false accusations, by design.
- Caption matching auto-flags a clearly-different caption (no shared party token,
  or a near-equal collision) and surfaces the resolved case name on every cite, so
  the attorney can compare it to the draft's parties. It does NOT claim to catch a
  fabrication that reuses a genuine party token ("Board v. <fake>") or a one-letter
  caption; for those the resolved name is shown and the comparison is the lawyer's.
- Case-existence and the bundled opinion text cover a handful of pre-vetted cases,
  not the full reporter. A cite outside the corpus reads "not found", which is
  correct for the pre-vetted draft but is not a general coverage claim.
- Contract checking evaluates every anchor type in a sentence, so a matching
  amount cannot mask a wrong date (a contradiction in any type wins). It affirms
  only provably-safe anchors — a verbatim quote, like the venue line, matched
  character-for-character against the source; a bare figure is never affirmed, it
  returns could-not-check (ADR-0013). So the one green is real and there are no
  false greens, by design.
- The open gap is the other direction: the contradiction path does NOT yet bind a
  figure to its obligation, so two same-typed figures about DIFFERENT obligations
  (an indemnification cap vs a liability cap) can false-RED. The semantic
  subject-labeler that would close it is off by default and still open work — a
  flag does not fix it. The curated corpus avoids the case by construction (one
  value per sentence, no cross-subject pairs), so keep the demo on-script: do not
  invite multi-value or cross-subject edits on stage. If asked, say so plainly —
  the tool refuses to affirm rather than risk a false green, but a confident RED
  on an off-script cross-subject figure pair is a known limitation, not a claim of
  infallibility.
- Screenshots at 1440 and 1920 and the full `CLAUDE.md` verify chain (macOS build,
  swift test, evals, benchmarks) run on the demo machine, not in this worktree.
