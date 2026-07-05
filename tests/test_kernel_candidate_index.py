"""L1 (2026-07-05): the candidate index that lifts the O(draft x source) ceiling.

The old kernel compared each claim against EVERY source sentence and refused
outright once a source passed ~4,000 sentences, so a long document could not be
verified at all. The candidate index retrieves only the sentences that could
affect a claim's verdict, so a long document verifies while the honesty
guarantees are untouched.

The safety argument, pinned here as tests:

  P2 (superset) -- ``candidate_ids`` is a SUPERSET of every sentence the
      per-sentence legs could act on (a clause candidate needs
      ``_sentence_relevant`` = token|digit; a residue outcome needs a residue
      anchor, which is digit-bearing; a restatement is a normalized match). So
      iterating candidates and keeping the identical guards/bodies visits every
      sentence that mattered -- the change is cost, never correctness.

  P3/P5 (scale) -- a long source with a small draft attests every claim
      (no oversize refusal from source size alone), and a long DRAFT does too;
      a genuinely degenerate claim still refuses honestly.

Verdict equivalence itself (P1/P4/P6) is pinned by the whole cachet_verify
suite, the frozen parity corpus, and the adversarial rotation all running
GREEN on this indexed path -- they are the behavior oracle; this file pins the
mechanism that makes their green trustworthy at scale.
"""

from __future__ import annotations

import random
import unittest

from cachet_verify.adapter import (
    _content_tokens,
    _normalize,
    _sentence_relevant,
    attest_draft,
    build_source_index,
    compare_residue,
    extract_residue_anchors,
    verify_claim,
)
from services.legal.anchors import extract_anchors

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


def _effective_ids(index, claim: str) -> set[int]:
    """Every sentence id the per-sentence legs could produce an effect for:
    a clause candidate (``_sentence_relevant``), a residue outcome
    (``compare_residue`` non-None), or a restatement (normalized match). The
    candidate set MUST be a superset of this or a verdict could change."""
    claim_tokens = _content_tokens(claim)
    norm_claim = _normalize(claim)
    claim_serv = extract_anchors(claim)
    claim_res = extract_residue_anchors(claim, claimed_spans=[(a.start, a.end) for a in claim_serv])
    serv_spans = [(a.start, a.end) for a in claim_serv]
    res_spans = [(a.start, a.end) for a in claim_res]
    all_spans = serv_spans + res_spans
    effective: set[int] = set()
    for i, entry in enumerate(index.sentences):
        if _sentence_relevant(claim_tokens, entry):
            effective.add(i)
        if norm_claim and entry.normalized == norm_claim:
            effective.add(i)
        if claim_res:
            outcome = compare_residue(
                claim,
                claim_res,
                all_spans,
                entry.text,
                list(entry.res_anchors),
                list(entry.all_spans),
            )
            if outcome is not None:
                effective.add(i)
    return effective


class CandidateSupersetProperty(unittest.TestCase):
    def test_candidates_superset_the_effective_set_over_random_corpora(self) -> None:
        rng = random.Random(20260705)
        for _ in range(200):
            source = "\n".join(_sentence(rng) for _ in range(rng.randint(5, 40)))
            index = build_source_index([source])
            claim = _sentence(rng)
            candidates = index.candidate_ids(_content_tokens(claim), _normalize(claim))
            effective = _effective_ids(index, claim)
            missing = effective - candidates
            self.assertEqual(
                missing,
                set(),
                f"candidate set dropped an effective sentence: claim={claim!r} missing={missing}",
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


if __name__ == "__main__":
    unittest.main()
