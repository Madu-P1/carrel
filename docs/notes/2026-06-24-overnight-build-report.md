# Morning report — overnight Cachet build (2026-06-24)

You slept; I built. Branch `claude/tender-chaplygin-bb518e`, **3 commits, nothing
pushed**, working tree clean, full Python verify green. No engine truth-surface
file, no frontend, no Swift was touched — the moat was never edited.

## The one-line jaw-drop

Cachet now attacks its own deterministic verify engine: **508 adversarial probes
across 23 attack families ran through the REAL engine, under a proven zero-egress
socket ban, and it HELD 505 of them** — 0 false accusations, 0 laundering — while
honestly surfacing **2 real false greens** and **1 coverage gap**, each with a
minimal repro and the exact test that locks it. The whole thing is read-only
against the moat, fully test-gated, and independently reviewed (Mythos) before it
landed.

## What to look at, in order (≈10 min)

1. **The confession ledger** — `.claude/adversary/confession-ledger-*.md`. Leads
   with the cracks, then honest coverage. This is the buyer-legible artifact.
2. **The two findings** — `docs/notes/2026-06-24-redteam-findings.md` (RT1 percent
   subject-binding false green; RT2 quote case-sensitivity). Each has a 1-line
   repro and a locking test.
3. **The harness code** — `evals/adversary/` (~1,100 lines, 8 modules). Start at
   `engine_probe.py` (the only engine-touching module, read-only) and
   `contracts.py::classify`. Skip the 10k-line `confession-ledger-*.json` — it is
   generated data, the `.md` is the read.
4. **The decision** — `docs/decisions/0008-unattended-redteam-discovery-not-fix.md`
   (why discovery-only, not unattended engine fixes).

## How the night was decided (council)

Convened the full council on the highest-value build target. Three seats (Harvey,
Vulcan, Bellwether) independently chose **engine hardening / a defensible
adversarial artifact**: the 2026 sanctions frontier has moved off citation-existence
onto misrepresented holdings and altered quotes (the false-green surface), and a
regulated in-house buyer's security review is *built to consume* an
adversarial-findings artifact. The required adversary won the *mechanism* argument
decisively — an unattended loop editing the gated truth-surface files reproduces
the `mln` laundering failure with you asleep, and the repo's own
`human_gates.security` + missing held-out set make an autonomous engine ship
impossible anyway. Resolution: **split the red-team** — discovery is read-only
(safe to run unattended, and IS the artifact); fixes are drafted + queued for your
review, never merged.

## What it found (honest)

- **RT1 (P0 false green)**: a single-value percent clause affirms ANY claim
  carrying that percent value, even when the claim's subject is absent from the
  clause. `"The audit fee is 10%"` reads *supported* against a clause that says the
  *royalty* is 10%. Money and duration scope this out (ADR-0013); percent does not,
  in either subject-labeler mode. This reproduces the known operator-gated
  "role-aligned clause matching" item as a deterministic minimal repro — it is
  **distinct from** the multi-value subject-collision that was already fixed (that
  one held 7/7).
- **RT2 (P3, honest-direction)**: a verbatim quote present in the clause but
  differing only in case at a sentence start is left could-not-verify instead of
  supported. Safe direction, never a false green, but a real coverage gap.
- **What HELD under fire**: 120 money + 111 near-miss-duration + 24 date + 117
  percent + currency-confusion + magnitude-scaling contradictions all caught or
  honestly refused; 8 fabricated + 14 misattributed citations refused/flagged; 16
  fabricated quotes never affirmed; the previously-fixed multi-value
  subject-collision still holds.

## Your move (nothing here was done without your sign-off)

- **Decide RT1's fix** — two options in the findings doc (scope percent out like
  money/duration, OR the role-aligned subject binding). It's operator-gated
  (validation-tied), so I drafted only. Queue entries: `.claude/forge.engine.tasks.md`
  → "Red-team findings". Locking tests: `tests/test_redteam_findings.py`
  (`expectedFailure` until fixed — they flip to a failing "unexpected success" the
  day the engine is fixed, prompting you to promote them).
- **Nothing is pushed or PR'd.** Say the word and I open a draft PR.

## Process notes (honest)

- **S1 and D4 were already implemented** in the repo (the split_sentences slide
  coverage and the supported-count-beside-refusal beat + its RTL test). The Forge
  queue just hadn't been reconciled. So the night's genuine net-new value is the
  confession-ledger harness — which is exactly what the three council seats wanted.
- **Mythos reviewed the whole diff** (fresh-context, 3 finders). Security finder
  clean (zero-egress + read-only verified empirically). I fixed every real finding
  before the final commit: removed a dead/wrong `baseline_state` field, hardened the
  litigator probe for `caption_unconfirmed`, and added 4 test guards (exact
  false-green allow-set, disposition coverage, non-vacuous quote check, determinism).
- **Verify**: `ruff check` + `ruff format --check` clean across the project; mypy
  clean; 463 engine + harness tests green (3 expected-failure tripwires). Frontend /
  Swift / benchmarks untouched, so unaffected.
