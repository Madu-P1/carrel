"""Seed corpus of clean (claim, clause) pairs for the adversarial harness.

Every seed is a CLEAN pair: the draft claim is consistent with the source clause.
The mutators in ``mutators.py`` perturb these seeds into adversarial cases whose
honest verdict is provable from the perturbation. Keeping the seeds clean and the
perturbations typed is what lets the harness know the honest answer by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

# Anchor types the contract path can check.
MONEY = "money"
DURATION = "duration"
PERCENT = "percent"
DATE = "date"
GOVERNING_LAW = "governing_law"
POLARITY = "polarity"
QUOTE = "quote"


@dataclass(frozen=True)
class Seed:
    """A clean (claim, clause) pair plus the surface token the mutators rewrite.

    ``value`` must appear verbatim in ``claim`` (mutators rewrite it with a single
    str.replace). ``subject`` is the bound subject for percent/governing-law
    subject-swap. ``quote`` is the verbatim phrase for quote seeds.
    """

    seed_id: str
    domain: str
    anchor_type: str
    claim: str
    clause: str
    value: str | None = None
    subject: str | None = None
    quote: str | None = None
    # False when the clause carries MULTIPLE values of this anchor type (e.g. two
    # percents). The engine honestly refuses multi-value clauses
    # (multi_value_unverifiable), so the single-value contradiction mutators skip
    # these and the subject-swap family takes over.
    single_value: bool = True


# --- money ------------------------------------------------------------------
_MONEY_SEEDS = [
    Seed(
        "money.liability_cap",
        "liability cap",
        MONEY,
        "The aggregate liability cap is $500,000.",
        "in no event shall the aggregate liability of the parties exceed $500,000",
        value="$500,000",
    ),
    Seed(
        "money.indemnity_cap",
        "indemnity cap",
        MONEY,
        "Indemnification is capped at $2,000,000.",
        "the indemnifying party's total indemnification obligation shall not exceed $2,000,000",
        value="$2,000,000",
    ),
    Seed(
        "money.purchase_price",
        "purchase price",
        MONEY,
        "The purchase price is $15,000,000.",
        "the Buyer shall pay the Seller a purchase price of $15,000,000 at Closing",
        value="$15,000,000",
    ),
    Seed(
        "money.deposit",
        "deposit",
        MONEY,
        "The earnest money deposit is $250,000.",
        "Purchaser shall deliver an earnest money deposit of $250,000 within three business days",
        value="$250,000",
    ),
    Seed(
        "money.annual_fee",
        "annual fee",
        MONEY,
        "The annual license fee is $90,000.",
        "Customer shall pay an annual license fee of $90,000 payable in advance",
        value="$90,000",
    ),
]

# --- duration ---------------------------------------------------------------
_DURATION_SEEDS = [
    Seed(
        "duration.confidentiality",
        "confidentiality survival",
        DURATION,
        "Confidentiality obligations survive termination for 5 years.",
        "the confidentiality obligations shall survive termination for a period of 5 years",
        value="5 years",
    ),
    Seed(
        "duration.noncompete",
        "non-compete",
        DURATION,
        "The non-compete lasts 24 months following termination.",
        "Section 9.1. The employee shall not compete for a period of 24 months following termination.",
        value="24 months",
    ),
    Seed(
        "duration.term",
        "term",
        DURATION,
        "The initial term is 3 years.",
        "this Agreement shall have an initial term of 3 years from the Effective Date",
        value="3 years",
    ),
    Seed(
        "duration.cure_period",
        "cure period",
        DURATION,
        "The cure period is 30 days.",
        "the breaching party shall have 30 days after written notice to cure the breach",
        value="30 days",
    ),
]

# --- percent ----------------------------------------------------------------
_PERCENT_SEEDS = [
    Seed(
        "percent.royalty",
        "royalty",
        PERCENT,
        "The royalty rate is 10%.",
        "Licensee shall pay Licensor a royalty of 10% of Net Sales",
        value="10%",
    ),
    Seed(
        "percent.interest",
        "interest",
        PERCENT,
        "Default interest accrues at 8%.",
        "overdue amounts shall bear interest at a rate of 8% per annum",
        value="8%",
    ),
    Seed(
        "percent.equity",
        "equity",
        PERCENT,
        "The investor receives 20% of the equity.",
        "in consideration of the Investment the Investor shall receive 20% of the fully diluted equity",
        value="20%",
    ),
]

# Subject-bound percent seeds for the subject-swap family (right value, wrong
# subject). ``subject`` is what gets swapped; ``value`` stays matched.
_SUBJECT_SEEDS = [
    Seed(
        "subject.allocation_france",
        "allocation by country",
        PERCENT,
        "The allocation to France is 10%.",
        "the allocation to France shall be 10% and the allocation to Germany shall be 25%",
        value="10%",
        subject="France",
        single_value=False,
    ),
    Seed(
        "subject.rate_classA",
        "rate by class",
        PERCENT,
        "The Class A coupon is 6%.",
        "the Class A notes bear a coupon of 6% and the Class B notes bear a coupon of 9%",
        value="6%",
        subject="Class A",
        single_value=False,
    ),
]

# --- date -------------------------------------------------------------------
_DATE_SEEDS = [
    Seed(
        "date.effective",
        "effective date",
        DATE,
        "The Effective Date is March 11, 2024.",
        "this Agreement is entered into and effective as of March 11, 2024",
        value="March 11, 2024",
    ),
    Seed(
        "date.closing",
        "closing date",
        DATE,
        "Closing occurs on September 30, 2025.",
        "the Closing shall take place on September 30, 2025 or such other date as the parties agree",
        value="September 30, 2025",
    ),
]

# --- governing law (exploratory tier) ---------------------------------------
_GOVERNING_LAW_SEEDS = [
    Seed(
        "law.ny",
        "governing law",
        GOVERNING_LAW,
        "This Agreement is governed by the laws of New York.",
        "this Agreement shall be governed by and construed in accordance with the laws of the State of New York",
        value="New York",
    ),
    Seed(
        "law.delaware",
        "governing law",
        GOVERNING_LAW,
        "This Agreement is governed by Delaware law.",
        "this Agreement shall be governed by the laws of the State of Delaware without regard to conflicts of law",
        value="Delaware",
    ),
]

# --- polarity (exploratory tier) --------------------------------------------
_POLARITY_SEEDS = [
    Seed(
        "polarity.exclusive",
        "exclusivity",
        POLARITY,
        "The license is exclusive.",
        "Licensor hereby grants to Licensee an exclusive license to the Licensed Technology",
        value="exclusive",
    ),
    Seed(
        "polarity.survives",
        "survival polarity",
        POLARITY,
        "The indemnity survives termination.",
        "the indemnification obligations in this Section shall survive termination of this Agreement",
        value="survives",
    ),
]

# --- quote (the only path to a green) ---------------------------------------
_QUOTE_SEEDS = [
    Seed(
        "quote.survive_termination",
        "survival quote",
        QUOTE,
        'The agreement says the obligations "survive termination" of the contract.',
        "These obligations survive termination of this Agreement for any reason.",
        quote="survive termination",
    ),
    Seed(
        "quote.hold_harmless",
        "indemnity quote",
        QUOTE,
        'The contract requires the vendor to "indemnify and hold harmless" the customer.',
        "Vendor shall indemnify and hold harmless Customer from any and all claims arising hereunder.",
        quote="indemnify and hold harmless",
    ),
    Seed(
        "quote.time_of_essence",
        "time-of-essence quote",
        QUOTE,
        'The contract states that "time is of the essence" for all deadlines.',
        "Time is of the essence with respect to each obligation under this Agreement.",
        quote="time is of the essence",
    ),
    Seed(
        "quote.as_is",
        "as-is quote",
        QUOTE,
        'The seller provides the goods on an "as is" basis.',
        "The goods are provided strictly on an as is basis without warranty of any kind.",
        quote="as is",
    ),
]

SEEDS: list[Seed] = [
    *_MONEY_SEEDS,
    *_DURATION_SEEDS,
    *_PERCENT_SEEDS,
    *_SUBJECT_SEEDS,
    *_DATE_SEEDS,
    *_GOVERNING_LAW_SEEDS,
    *_POLARITY_SEEDS,
    *_QUOTE_SEEDS,
]


def seeds_by_anchor(anchor_type: str) -> list[Seed]:
    return [s for s in SEEDS if s.anchor_type == anchor_type]
