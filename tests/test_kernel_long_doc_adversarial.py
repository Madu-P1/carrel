"""L6 (2026-07-05): the long-document adversarial family.

The L1 candidate index lets a claim be checked against a LONG source. This
red-teams that path for the one catastrophic failure -- a FALSE GREEN (a
fabricated/altered claim coming back 'verified') -- and secondarily a false
accusation (a faithful claim flagged 'altered'). A refusal is always acceptable.

Each attack buries the load-bearing sentence deep in thousands of filler
sentences, exactly where the old kernel refused outright and the index now must
find it WITHOUT ever greening a bad claim. The honesty floor is the ship bar:
0 false greens, 0 false accusations, whatever the depth.
"""

from __future__ import annotations

import unittest

from cachet_verify.adapter import verify_claim

# Digit-free prose filler, so the buried numeric clause is the signal, not noise.
_FILLER = "This clause concerns an administrative matter of no numeric consequence."


def _bury(target: str, depth: int = 5000, *, before: bool = True) -> str:
    block = "\n".join(_FILLER for _ in range(depth))
    return f"{target}\n{block}" if before else f"{block}\n{target}"


# (id, claim, source, truth) where truth in {altered, faithful, uncheckable}.
# A refusal is honest for any of them; the FLOOR is: altered never 'verified',
# faithful never 'altered'.
_ATTACKS = [
    (
        "buried-money-alteration",
        "The aggregate liability shall not exceed $1,000,000.",
        _bury("The aggregate liability shall not exceed $500,000.", before=False),
        "altered",
    ),
    (
        "buried-money-faithful",
        "The fee is $500,000 under the agreement.",
        _bury("The fee is $500,000 under the agreement.", before=True),
        "faithful",
    ),
    (
        "value-coincidence-buried",
        "The break fee is $7 million.",
        "The marketing budget is $7 million.\n"
        + "\n".join(_FILLER for _ in range(4000))
        + "\nThe break fee is $3 million.",
        # The claimed $7M coincides with a DIFFERENT fact's figure deep in the
        # source; the real break fee is $3M. Must never green on the coincidence.
        "uncheckable",
    ),
    (
        "buried-percent-alteration",
        "The penalty equals 2% of the underpayment.",
        _bury("The penalty equals 20% of the underpayment.", before=False),
        "altered",
    ),
    (
        "buried-date-faithful",
        "The agreement was executed on March 11, 2023.",
        _bury("The agreement was executed on March 11, 2023.", before=True),
        "faithful",
    ),
    (
        "quote-straddling-old-ceiling",
        'The record states "subject to regulatory approval".',
        "\n".join(_FILLER for _ in range(3999))
        + "\nThe deal closes subject to regulatory approval, the parties agreed.",
        # A verbatim quote whose source sits right at the old 4,000 ceiling: the
        # index must find it (verified) or refuse -- never a false 'altered'.
        "faithful",
    ),
    (
        "buried-duration-alteration",
        "The term is 8 months across three waves.",
        _bury("The term is 18 months across three waves.", before=False),
        "altered",
    ),
    (
        "far-apart-superseded-value",
        "The purchase price is $5 million.",
        "The purchase price was originally $5 million.\n"
        + "\n".join(_FILLER for _ in range(4500))
        + "\nThe amendment revised the purchase price to $7 million.",
        # A stale value stated early, superseded far later: the sources disagree
        # about this fact, so the honest verdict is a refusal, never a green.
        "uncheckable",
    ),
]


class LongDocAdversarialFloor(unittest.TestCase):
    def test_no_false_green_no_false_accusation_at_depth(self) -> None:
        false_greens: list[str] = []
        false_accusations: list[str] = []
        for aid, claim, source, truth in _ATTACKS:
            state = verify_claim(claim, [source]).state
            if truth in ("altered", "uncheckable") and state == "verified":
                false_greens.append(f"{aid}: expected not-verified, got verified")
            if truth == "faithful" and state == "altered":
                false_accusations.append(f"{aid}: expected not-altered, got altered")
        self.assertEqual(false_greens, [], "FALSE GREEN on the long-doc path (catastrophic)")
        self.assertEqual(false_accusations, [], "FALSE ACCUSATION on the long-doc path")

    def test_the_buried_alterations_are_actually_caught(self) -> None:
        # Not just 'no false green' -- the index must genuinely FIND the buried
        # contradiction, else the long-doc win is hollow. The anchored money/
        # percent/duration alterations must read 'altered' at depth.
        for aid, claim, source, truth in _ATTACKS:
            if truth != "altered":
                continue
            self.assertEqual(
                verify_claim(claim, [source]).state,
                "altered",
                f"{aid}: a buried anchored alteration must be caught, not missed",
            )


if __name__ == "__main__":
    unittest.main()
