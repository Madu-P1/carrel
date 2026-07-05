# Adversary report — long-document family (L6, 2026-07-05)

**Headline: the refusal engine HELD 8/8 long-document attacks. Zero false
greens, zero false accusations, at depth.**

Context: L1's candidate index lets a claim be checked against a long source
(thousands of sentences). This family buries the load-bearing sentence deep in
digit-free filler — exactly where the old kernel refused outright — and attacks
the one catastrophic failure: a false green on the long-doc path.

Locked as a regression test: `tests/test_kernel_long_doc_adversarial.py`
(the floor AND that buried anchored alterations are genuinely caught, not just
refused).

## The 8 attacks

| id | buried at | truth | engine | held |
|---|---|---|---|---|
| buried-money-alteration | sentence 5000 | altered | altered | catch |
| buried-money-faithful | sentence 0 (5000 after) | faithful | verified | confirm |
| value-coincidence-buried | $7M budget @4000, $3M fee | uncheckable | could_not_check | refuse |
| buried-percent-alteration | sentence 5000 | altered | altered | catch |
| buried-date-faithful | sentence 0 | faithful | verified | confirm |
| quote-straddling-old-ceiling | sentence ~4000 | faithful | verified/refuse | confirm |
| buried-duration-alteration | sentence 5000 | altered | altered | catch |
| far-apart-superseded-value | $5M @0, $7M @4500 | uncheckable | could_not_check | refuse |

## The numbers

- **FALSE GREEN: 0** — no altered/uncheckable claim came back verified, at any depth.
- **FALSE ACCUSATION: 0** — no faithful claim was flagged, at any depth.
- **Buried alterations CAUGHT** — the money/percent/duration alterations at
  sentence 5,000 read `altered`, not missed in the noise. The long-doc win is
  real, not hollow.
- The two hardest cross-fact cases held via refusal: a value that COINCIDES with
  a different fact's figure deep in the source (`could_not_check`, the C3 guard
  at distance), and a stale value superseded 4,500 sentences later
  (`could_not_check`, never picking a winner).

## Kill date + coverage

- Kill date **2026-10-01** — rotate or retire; do not let this ossify into a
  second in-distribution corpus.
- Covers the anchored numeric/date/duration + quote + cross-fact classes at
  depth. Not covered: OCR-degraded long sources (Track D scanned-PDF path) and
  multi-source long-doc conflicts — next rotation candidates.

## The validation-demo line

**"Buried a fabrication at sentence 5,000 of an 8,000-sentence document; the
engine caught it and never once greened a bad claim or flagged a faithful one.
What it could not adjudicate, it refused."**
