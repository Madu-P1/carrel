# Cachet Adversary — percent-path red-team, 2026-06-16

Branch: `claude/cachet-percent-scope-out` (off `claude/crazy-brahmagupta-301932`).
Target: the percent path of the deterministic verify engine, after the ADR-0013
percent-addendum fix (subject-less percents scoped out; value match -> could-not-check;
routed to the unconfirmed tier so it cannot launder a co-occurring present).

## Headline

**Refusal engine HELD 13/13 refusal-or-catch attacks across 3 families; 2/2
non-vacuity guards correct; 0 P0 false greens, 0 false accusations.**

## Families attacked

| Family | Attacks | HELD | Cracks |
|---|---|---|---|
| Same-value / different-subject (surface shapes the generator does not emit) | 7 | 7 | 0 |
| Near-miss numerics (must contradict, never green) | 2 | 2 | 0 |
| Could-not-check laundering (multi-anchor, the highest-value family) | 4 | 4 | 0 |
| Non-vacuity (a real subject-bound green / contradiction must still decide) | 2 | 2 | 0 |

### Same-value / different-subject (all -> could-not-check)
Word-form ("ten percent"), basis-points canonicalization ("50 bps" == 0.5%),
percent-of-X ("10% of net revenue" vs "10% of gross sales"), "up to X%", "X% per
annum", "capped at X%", decimal-notation variance ("12.50%" vs "12.5%"). Each is a
value coincidence across a different obligation; each returned `not_found`
(could-not-check). The fix is not phrasing-specific — it scopes the value-only path,
so every surface that reaches it is covered.

### Near-miss numerics (all -> contradicted)
"5%" vs "0.5%", "10%" vs "10.5%": the value-only contradiction catch (retained per
ADR-0013) fires. A false green here would be the worst case; none occurred.

### Could-not-check laundering (all -> could-not-check) — the one that matters
An unconfirmed percent paired with a genuinely-confirmed sibling must NOT ride that
sibling to a green:
- via governing-law present ("Governed by Delaware law and the royalty is 10%" vs a
  clause confirming Delaware + a different 10%) -> could-not-check.
- via polarity present ("license is exclusive and the royalty is 10%") -> could-not-check.
- via verbatim quote -> could-not-check.
- via a confirmed SUBJECT-BOUND percent sibling ("Allocation is 10% France and the
  royalty is 10%") -> could-not-check.
The unconfirmed tier outranks present, so the laundering vector is closed in every case.

### Non-vacuity (the engine still DECIDES the real case)
- "Allocation is 10% France" vs same -> supported (the one preserved percent green).
- "Allocation is 20% France" vs "10% France" -> contradicted.

## Disposition of cracks

None. Nothing routed to the Forge queue (a crack is only "found" when it fails). The
7 strongest distinct attacks (3 surface shapes + 4 multi-anchor laundering) were LOCKED
into `evals/cachet_acceptance/percent_collision_corpus.jsonl` via
`gen_percent_collision_corpus.py::_adversary_locked()` so a future engine change cannot
silently reopen them. Fixtures: `~/Desktop/Codex/.claude/adversary/fixtures/percent/`.

## Coverage / kill date

Covered this pass: percent same-value-diff-subject, near-miss, multi-anchor laundering.
NOT attacked this pass (percent-adjacent, future): percent inside a multi-value clause
with role alignment (T1), percent ranges ("between 5% and 10%"), percent vs fraction
("one-tenth"). Kill/refresh fixtures by 2026-09-16 or when the percent path changes.
