"""Value-anchor candidate index (2026-07-05): verify FIGURE-DENSE long documents.

The old kernel compared each claim against EVERY source sentence and refused
outright once a source passed ~4,000 sentences. The first candidate index (L1)
retrieved a SUPERSET of the old full scan -- every content-token match PLUS
every digit-bearing sentence -- so it was byte-identical but still refused a
figure-DENSE long document (a real contract, thousands of amounts): the all-digit
term alone blew the per-claim ceiling. The value-anchor index fixes that: a claim
retrieves only the sentences sharing one of its content TOKENS or one of its own
anchor VALUES, so a figure-dense document verifies as long as THIS claim's values
and vocabulary are sparse in it.

The safety argument, pinned here as tests:

  HONESTY FLOOR (the guarantee that matters) -- value-anchor can only DROP
      sentences the old full scan visited (those sharing no token and none of the
      claim's values). Such a sentence can never have been the source of a
      ``verified`` (that needs a value carrier -> value_ids, a normalized
      restatement -> norm_ids, or a verbatim quote -> the pool, ALL kept) and
      never a legitimate accusation (a zero-token-overlap contradiction is
      cross-fact noise the clause leg already filters). So dropping it can only
      turn a catch or a would-be false accusation into a REFUSAL -- never a false
      green, never a new false accusation. ``HonestyFloorDifferential`` proves
      this directly against the full-scan reference over random corpora: 0 false
      greens, 0 false accusations, every divergence ``altered -> could_not_check``
      on degenerate multi-value word-salad claims.

  SCALE -- a figure-dense long source verifies a faithful claim and catches a
      buried alteration (no oversize refusal from source size alone); a long
      DRAFT attests every claim; a genuinely degenerate claim still refuses.

This is a deliberately WEAKER guarantee than L1's byte-identity, taken because
byte-identity was worthless on the actual deliverable (it refused the whole
document). The honesty floor -- no false green, no false accusation -- is the
property the product's trust rests on, and it is preserved and tested here; the
whole cachet_verify suite, the frozen parity corpus, and the adversarial rotation
remain the behavior oracle and stay GREEN on this path.
"""

from __future__ import annotations

import random
import unittest

import cachet_verify.adapter as adapter
from cachet_verify.adapter import (
    _claim_value_keys,
    _content_tokens,
    _normalize,
    attest_draft,
    build_source_index,
    verify_claim,
)

# A vocabulary that mixes prose, figures, dates, durations, and polarity so the
# generated sources exercise every leg (clause, residue, restatement, quote).
_SUBJECTS = ["fee", "term", "cap", "revenue", "penalty", "license", "budget", "headcount", "margin"]
_VALUES = [
    "$500",
    "$1,000,000",
    "2 years",
    "30 days",
    "20%",
    "60 billion",
    "1,240",
    "March 1, 2019",
]
_WORDS = ["the", "was", "is", "set", "at", "under", "agreement", "shall", "exclusive", "provides"]


def _sentence(rng: random.Random) -> str:
    n = rng.randint(3, 9)
    parts = [rng.choice(_WORDS + _SUBJECTS + _VALUES) for _ in range(n)]
    return " ".join(parts).capitalize() + "."


class HonestyFloorDifferential(unittest.TestCase):
    """The honesty-floor lock, the strongest safety statement value-anchor CAN
    make (byte-identity is gone by design). Run the SAME verify_claim twice on
    the same input -- once on the real value-anchor candidate set, once with
    candidate_ids monkeypatched to return ALL sentence ids (the old full scan) --
    over randomized corpora, and assert the floor holds every time:

      * NO false green  -- value-anchor never returns ``verified`` where the
        full scan did not (a green needs a value carrier, a normalized
        restatement, or a verbatim quote, all of which value-anchor keeps).
      * NO new false accusation -- value-anchor never returns ``altered`` where
        the full scan did not.
      * every divergence is ``altered -> could_not_check`` -- value-anchor
        REFUSING where the full scan flagged, which the honesty ordering permits
        (a refusal is always acceptable). In practice these are degenerate
        multi-value word-salad claims, the very cross-clause false-accusation
        class, so the refusal is if anything more honest.

    Same code path, only the candidate set differs, so this is a direct proof of
    the floor -- a future change that let the index manufacture a green or an
    accusation would fail HERE."""

    def test_value_anchor_never_greens_or_accuses_where_full_scan_did_not(self) -> None:
        real = adapter.SourceIndex.candidate_ids

        def full_scan(self, claim_tokens, norm_claim, value_keys):  # noqa: ANN001 - test shim
            return frozenset(range(len(self.sentences)))

        rng = random.Random(4242)
        divergences: list[tuple[str, str, str]] = []
        for _ in range(1500):
            source = "\n".join(_sentence(rng) for _ in range(rng.randint(4, 30)))
            claim = _sentence(rng)
            indexed = verify_claim(claim, [source])
            try:
                adapter.SourceIndex.candidate_ids = full_scan
                brute = verify_claim(claim, [source])
            finally:
                adapter.SourceIndex.candidate_ids = real
            if indexed.state == brute.state:
                continue
            divergences.append((brute.state, indexed.state, claim))
            # The floor: never a green the full scan withheld, never an
            # accusation the full scan withheld.
            self.assertNotEqual(
                "verified",
                indexed.state,
                f"value-anchor manufactured a green: claim={claim!r} full_scan={brute.state}",
            )
            self.assertNotEqual(
                "altered",
                indexed.state,
                f"value-anchor manufactured an accusation: claim={claim!r} full_scan={brute.state}",
            )
            # The only permitted divergence: full scan flagged, value-anchor
            # honestly refused.
            self.assertEqual(
                ("altered", "could_not_check"),
                (brute.state, indexed.state),
                f"unexpected divergence direction: claim={claim!r}",
            )


class ScaleProperty(unittest.TestCase):
    def test_a_long_source_with_sparse_figures_no_longer_refuses(self) -> None:
        # 6,000 prose sentences (far past the old 4,000 ceiling), figures sparse.
        lines = []
        for i in range(6000):
            if i % 50 == 0:
                lines.append("The fee is $500 under the agreement.")
            else:
                # Genuinely digit-free prose, so the figure sentences are the
                # only digit-bearing candidates (the real sparse-figure case).
                lines.append("The parties met to discuss the matter at length.")
        source = "\n".join(lines)
        # A claim that used to refuse (source >> 4,000 sentences) now verifies.
        result = verify_claim("The fee is $500 under the agreement.", [source])
        self.assertEqual(result.state, "verified")
        self.assertNotIn("too large", " ".join(c.detail for c in result.checks).lower())

    def test_a_long_draft_against_a_normal_source_attests_every_claim(self) -> None:
        # P5: the long-DRAFT mirror. 5,000 claim sentences, one real catch.
        source = "The cap is $500,000 in the agreement."
        claims = ["The weather was mild that quarter." for _ in range(4999)]
        claims.append("The cap is $1,000,000 in the agreement.")
        draft = "\n".join(claims)
        att = attest_draft(draft, [source])
        # The planted alteration is still caught at scale (no oversize refusal).
        states = [c.attestation.state for c in att.claims]
        self.assertIn(
            "altered", states, "the planted $1M-vs-$500K alteration must survive at scale"
        )

    def test_a_degenerate_all_figure_source_still_refuses_honestly(self) -> None:
        # The ceiling does not vanish: a source where nearly every sentence is a
        # figure carrier (so candidates ~= all sentences) still refuses past the
        # bound rather than silently truncating.
        source = "\n".join("The value is $500." for _ in range(5000))
        result = verify_claim("The value is $500.", [source])
        self.assertEqual(result.state, "could_not_check")
        self.assertIn("too large", " ".join(c.detail for c in result.checks).lower())


class RealLongDocumentCatch(unittest.TestCase):
    def test_an_alteration_buried_in_a_long_source_is_still_caught(self) -> None:
        # REAL-WORLD REGRESSION RULE: a real long document with the contradicting
        # clause on "page 400". The old kernel refused the whole thing; the
        # indexed path finds the clause and flags the altered figure.
        filler = "\n".join(
            "This clause concerns an administrative matter of no numeric consequence."
            for _ in range(5000)
        )
        source = filler + "\nThe aggregate liability shall not exceed $500,000."
        result = verify_claim("The aggregate liability shall not exceed $1,000,000.", [source])
        self.assertEqual(result.state, "altered")


class FigureDenseLongDocument(unittest.TestCase):
    """The motivating win: a FIGURE-DENSE long document (every sentence carries a
    figure) that the all-digit index (L1) refused outright now verifies, because
    a claim retrieves only the sentences carrying its own value/vocabulary rather
    than the whole digit population. 5,000 distinct money clauses -> the old
    ``_too_large(1, digit_ids)`` short-circuit fired on all 5,000 digit-bearing
    sentences and refused; value-anchor pulls the handful sharing the claim's
    value and subject."""

    @staticmethod
    def _subject(i: int) -> str:
        # A distinct all-alphabetic subject per clause (base-26 -> "aaaa"...), so
        # each sentence's lone content token appears once. Real long documents
        # have varied vocabulary; uniform boilerplate ("the fee for item N") is
        # the degenerate case and is meant to refuse on token density, not here.
        letters = "abcdefghijklmnopqrstuvwxyz"
        return "".join(letters[(i // 26**p) % 26] for p in range(3, -1, -1))

    def _dense_source(self) -> str:
        # 5,000 clauses, each a DISTINCT subject + amount, EVERY sentence
        # digit-bearing. The all-digit candidate term (L1) would be 5,000 here.
        return "\n".join(f"The {self._subject(i)} is ${1000 + i:,}." for i in range(5000))

    def test_a_faithful_claim_against_a_dense_source_verifies(self) -> None:
        source = self._dense_source()
        # Verbatim restatement of one clause among 5,000 figure-bearing ones.
        result = verify_claim(f"The {self._subject(4200)} is $5,200.", [source])
        self.assertEqual(result.state, "verified")
        self.assertNotIn("too large", " ".join(c.detail for c in result.checks).lower())

    def test_a_buried_alteration_in_a_dense_source_is_caught(self) -> None:
        source = self._dense_source()
        # The altered figure for that same clause is flagged, not lost in the
        # 5,000-figure haystack and not swallowed by an oversize refusal.
        result = verify_claim(f"The {self._subject(4200)} is $9,999.", [source])
        self.assertEqual(result.state, "altered")

    def test_the_dense_source_would_have_refused_under_the_all_digit_bound(self) -> None:
        # Guards the motivation: every sentence is digit-bearing, so the old
        # all-digit candidate term alone was >> the ~4,000 ceiling. The
        # value-anchor index carries no such term, which is why the two tests
        # above verify instead of refusing.
        index = build_source_index([self._dense_source()])
        digit_bearing = sum(1 for e in index.sentences if e.has_digit)
        self.assertGreater(digit_bearing, 4000)
        # The claim's OWN candidate set, by contrast, is tiny.
        claim = f"The {self._subject(4200)} is $5,200."
        candidates = index.candidate_ids(
            _content_tokens(claim), _normalize(claim), _claim_value_keys(claim)
        )
        self.assertLess(len(candidates), 4000)


class AggregateAntiWedge(unittest.TestCase):
    """mythos D-track+L1 c4: the per-claim bound does not bound the SUM. A
    crafted in-caps draft x a source of ~3,999 candidate-bearing sentences (each
    claim just under the per-claim refusal) drove ~10M comparisons. The
    aggregate work pre-pass must refuse the whole draft fast."""

    def test_a_crafted_just_under_bound_draft_refuses_fast(self) -> None:
        import time

        source = "\n".join(
            f"Clause about the payment matter number {i} of the record here." for i in range(3999)
        )
        draft = "\n".join(
            f"The payment matter number {i} is discussed at length in this record."
            for i in range(2500)
        )
        t0 = time.perf_counter()
        att = attest_draft(draft, [source])
        elapsed = time.perf_counter() - t0
        self.assertEqual(att.state, "could_not_check")
        self.assertLess(elapsed, 5.0, f"aggregate wedge took {elapsed:.1f}s, must refuse fast")
        self.assertTrue(
            any("too large" in c.detail for a in att.claims for c in a.attestation.checks)
        )

    def test_a_long_prose_draft_against_a_sparse_source_still_attests(self) -> None:
        # The fix must not over-refuse: a long prose draft (few candidates per
        # claim) against a sparse source stays far under the aggregate budget.
        source = "The cap is $500,000 in the agreement.\nThe term is two years."
        draft = "\n".join(
            f"The cap is $500,000 in the agreement number {i % 3}." for i in range(3000)
        )
        att = attest_draft(draft, [source])
        # Processed PER CLAIM (3000 claims), not collapsed into the single
        # oversize-refusal blob, and no claim carries the 'too large' refusal.
        self.assertEqual(len(att.claims), 3000)
        self.assertFalse(
            any("too large" in c.detail for a in att.claims for c in a.attestation.checks),
            "a long draft against a sparse source must not hit the aggregate ceiling",
        )


if __name__ == "__main__":
    unittest.main()
