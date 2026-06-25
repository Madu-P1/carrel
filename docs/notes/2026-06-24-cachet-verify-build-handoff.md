# Cachet verify-engine build — session handoff (2026-06-24)

**For a fresh Claude session.** Two verify-engine PRs just merged to `main`. The next
build is a small queue of captured follow-ons. Scroll to **"Paste this to continue"** at
the bottom — it runs `/prompt-optimizer` to optimize-and-run the next build step. Read this
whole file first; you have no memory of the session that produced it.

---

## Baseline (trust this)

- `main` is at `664bb5bd6`. Both PRs below are MERGED and main is green: a combined
  engine re-verify ran **510 tests OK** (`tests.test_contract_verify[_integration]`,
  `test_quote_check`, `test_verify`, `test_verify_stream`, `test_zero_egress`,
  `test_deterministic_envelope`, `test_legal_sentences`, `test_anchors`, `test_align`,
  `test_briefs`, `test_demo_corpus`). Full CI on both PRs was green
  (python-quality / python-tests / frontend-build / Analyze(swift)).

## What just shipped to `main`

- **carrel#186 — BROAD percent scope-out** (`d0be16621`). The deterministic engine no
  longer affirms a bare percent. A `/cachet-adversary` red-team fuzz found the
  `_percent_subject` regex false-greens **8/8** on capitalized common-word pseudo-subjects
  (`"20% Interest"` vs `"20% Interest-free"`; `"20% Effective"` rate vs `"Effective date"`).
  So percent now mirrors money/duration: a value-MATCH → could-not-check; only a
  CONTRADICTION is a definite verdict; affirmation returns only via the AFM subject labeler.
  Held-out fixtures: `.claude/adversary/fixtures/percent-{labeled,subject}-binding/`.
  Memory: `cachet-percent-scope-out`. (Superseded + closed the narrow PR #181.)
- **carrel#187 — quote autopsy** (`664bb5bd6`). When the engine marks a cited quote
  `altered`, the Examination surface shows genuine words in ink and fabricated words struck
  through in oxblood, word-level. Render-only, disposition byte-identical, cry-wolf-safe
  (a word is struck only if its case-folded form is a substring of NO confident source).
  Memory: `cachet-quote-autopsy`.

## The build to continue — Forge queue `~/.local/state/forge/cachet-engine/queue.txt`

- **FU1 — bar-3 refusal-naming `[bounded, ~1 PR — DO THIS FIRST]`.** The acceptance gate
  `script/cachet-acceptance.py` bar 3 (refusals are specific) FAILs: multi-value / percent
  could-not-check refusals emit a content-free message ("The … values in the summary and
  the loaded source cannot be aligned one-to-one deterministically") that names no figure.
  Make each refusal NAME the figure(s) from its own statement; port the refusal-detail
  approach from the **closed** PR carrel#181. DETAIL-only — zero disposition change.
- **FU2 — AFM percent recall (bar 4) `[LARGE — design first, needs Madu's explicit go]`.**
  BROAD removed all deterministic percent greens, so bar 4 (definite-rate ≥ 0.70) stays RED.
  Wire percent through the ADR-0013 AFM subject labeler + 48-char verbatim post-check so a
  subject-CONFIRMED percent can green again without the disproven regex binder. Multi-day;
  do NOT auto-start — surface a design proposal.
- **FU3 — richer autopsy token-diff `[optional polish, #187 follow-up]`.** Show the genuine
  source passage beside the strike. Render-only, ships no extra source text, cry-wolf-safe.

## Non-negotiable invariants (the product IS the honest refusal)

- A false GREEN is catastrophic; a false ACCUSATION is serious; a refusal ("could not
  verify") is correct even when annoying. Never make the engine MORE confident.
- The deterministic engine never affirms a bare parametric value without a real subject
  labeler (AFM). Money, duration, and now percent all obey this.
- The safety gate is the held-out tests + `script/cachet-acceptance.py` bars 1 (zero false
  greens) and 2 (zero false accusations). Red-team with `/cachet-adversary`; review every
  diff with `/mythos`.

## Pipeline + conventions

- Test-gated additive PRs; clean branch off `main`; **draft** PR; no "Generated with Claude
  Code"/co-author footer. `main` is protected (1 review + the 4 CI checks above;
  `enforce_admins=false`). Do NOT `gh pr ready` / merge without Madu's explicit go.
- Tools: `/council` for judgment calls, `/forge` for the build loop, `/mythos` for
  independent review, `/cachet-adversary` to red-team the refusal, `/jarvis` for sitreps.
- Run from a worktree with `.venv` symlinked to the main checkout's `.venv`; the venv lives
  at `/Users/madu/Desktop/Codex/.venv`.

## Paste this to continue (a fresh session can run it verbatim)

```
/prompt-optimizer Continue the Cachet deterministic verify-engine build on a clean branch off main (currently 664bb5bd6). First read the Forge queue at ~/.local/state/forge/cachet-engine/queue.txt (tasks FU1/FU2/FU3) and the memories cachet-percent-scope-out + cachet-quote-autopsy. Then build FU1, the bounded next PR: make every multi-value / percent could-not-check refusal NAME the specific figure(s) from its own statement — the acceptance gate script/cachet-acceptance.py bar 3 currently FAILs with content-free "values cannot be aligned one-to-one" messages; port the refusal-detail approach from the closed PR Madu-P1/carrel#181. This is DETAIL-only: change zero verify dispositions. Hard invariants: never affirm a bare parametric value; a false green is catastrophic. Gate to green before prepping anything: script/cachet-acceptance.py bar 3 PASS while bars 1+2 (zero false greens / zero false accusations) stay PASS, and tests.test_contract_verify + tests.test_contract_verify_integration stay green; then red-team the result with /cachet-adversary and review the diff with /mythos. Prep it as a DRAFT PR off main — do not ready/merge without my go. Do NOT start FU2 (the AFM subject-labeler for percent recall): it is a multi-day design piece needing my explicit go — surface a one-page design proposal for it instead. FU3 (richer autopsy token-diff) is optional polish, lower priority.
```
