"""Anchor detection for the Cachet deterministic verify engine.

An "anchor" is a deterministically detectable token that makes a
statement independently checkable: a citation, a quoted run, a money
amount, a date or duration, a section reference. Cachet verifies spans
that carry an anchor; anchor-free spans route to the loud
"not independently verifiable" tray, never silently passed.

Honesty tier T0: every detector is pure regex / string / table lookup,
no learned weights, no network. Money, duration, and date carry a
``canonical_value`` (integer cents, integer days, ISO date string) so a
downstream contradiction check is pure arithmetic.

Citation and quoted-run detection reuse the existing T0 building blocks
(``citations_eyecite``, ``quote_check``). The money/duration/date/section
regexes are clean-room MIT implementations (LexNLP is AGPL and partly
classifier-backed, so it is deliberately not used).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from dateutil import parser as date_parser

from .citations_eyecite import find_citations
from .quote_check import extract_draft_quote_spans


@dataclass(frozen=True)
class Anchor:
    """One verifiable artifact located in a span.

    ``start``/``end`` are character offsets into the span passed to
    :func:`extract_anchors`. ``canonical_value`` is populated only for
    parametric types: money -> integer cents, duration -> integer days,
    date -> ISO ``YYYY-MM-DD`` string, governing_law -> normalized
    jurisdiction key. It is ``None`` for the rest.
    """

    type: str  # citation | slip_op | quote | money | duration | date | percent | governing_law | polarity | section | party | defined_term
    text: str
    start: int
    end: int
    canonical_value: object | None = None


_SLIP_OP = re.compile(r"\bNo\.\s+\d{1,4}-\d{1,6}\b|\bslip\s+op\.", re.IGNORECASE)

# Scale words must be standalone (not "Million-dollar" adjective, not part of a
# longer word); single-letter M/B/K must be suffixed directly to the number
# ("$5M" scales, "$5 m" does not, because a spaced bare letter is ambiguous).
_MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:million|billion|thousand)(?![-\w])|(?:MM|M|B|K)(?![-\w]))?",
    re.IGNORECASE,
)

# Word-form money with no numeral ("one million dollars", "five hundred thousand
# dollars", "a billion dollars"). Bounded on purpose: a single leading number word
# (one..twenty, or "a"), an optional "hundred", and a scale word. An AI summary that
# paraphrases "$1,000,000" as "one million dollars" drops the numeral the digit
# _MONEY detector needs; without this the claim carries no money anchor and the
# parametric-contradiction catch cannot fire. The trailing negative lookahead
# defers to the digit form in the "one million dollars ($1,000,000)" convention so
# the figure is counted once. Compound numbers ("twenty-five million", "twenty
# five million", "one and a half million") and bare hundreds ("five hundred
# dollars") are outside the bounded grammar and must yield NO anchor, never a
# wrong value: the (?<![\w-]) guard stops "five" matching inside "twenty-five",
# and _NUMBER_WORD_BEFORE rejects a match whose preceding text ends with a
# number word ("twenty five million" must not anchor as $5M). A sentence whose
# only candidate anchor is rejected here carries no anchor at all and renders
# UNTREATED (plain draft text, no card) per the 2026-06-08 untreated split — a
# pinned recall gap (tests/test_anchors.py), not a hidden one.
_MONEY_WORD = re.compile(
    r"(?<![\w\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212])"
    r"(?P<unit>one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|a)\s+"
    r"(?:(?P<hundred>hundred)\s+)?"
    r"(?P<scale>thousand|million|billion)\s+(?:dollars|USD)\b"
    r"(?!\s*\(?\s*\$)",
    re.IGNORECASE,
)

# The compound rejector for _MONEY_WORD: a match is refused when the text right
# before it ends with a number word, because then the spelled-out amount is a
# space-separated compound the bounded grammar cannot represent and any
# canonical we minted would be the TAIL of the real number (a manufactured
# value in both verdict directions). Deliberately broader than
# _MONEY_WORD_UNITS: tens words and scale words reject too ("ninety five
# thousand", "hundred twenty five million").
_NUMBER_WORD_BEFORE = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|"
    r"billion)[\s,.\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]*$",
    re.IGNORECASE,
)

# Matches "5 years", "five (5) years", "30 calendar days". The digit may be bare
# or in the legal "word (digit)" convention; an optional spelled-out number word
# is captured for display (restricted to number words so it cannot grab "of").
_DURATION = re.compile(
    r"(?:(?P<word>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+)?"
    r"(?:\((?P<paren>\d+)\)|\b(?P<num>\d+))\s+(?:calendar\s+)?(?P<unit>year|month|week|day)s?\b",
    re.IGNORECASE,
)

_SECTION = re.compile(
    # Word keywords need a word boundary; the section sign (and its plural, §§)
    # does not. A leading \b before § never asserts (a space-to-§ run is non-word
    # to non-word), which is why a bare "§ 1983" / "§ 7.2" matched nothing before.
    r"(?:\b(?:Section|Sec\.|Clause|Article|Schedule|Exhibit)\s+|§§?\s?)"
    r"\d+(?:\.\d+)*(?:\([a-z0-9]+\))?",
    re.IGNORECASE,
)

# --- Polarity-pair detector (canonical_value = "{stem}:{noun-class}+|-"). The
# exclusivity flip ("exclusive" summarized from a non-exclusive grant, binding
# from non-binding, irrevocable from revocable) is the canonical single-token
# contract-summary error, and it is pure string work: a closed set of qualifier
# stems whose negated surface ("non-X", solid "nonX", or the ir- pair for
# revocable) shares the stem, so a flip is same-stem/different-sign. Precision
# is structural on three sides: the qualifier anchors ONLY when an unbroken
# closed-vocabulary adjective run leads to a grant noun (so "exclusive
# jurisdiction" is venue and never anchors, and "the exclusive distributor
# shall hold a license" breaks the run and refuses); the noun requirement is a
# lookahead, so each adjective in "an exclusive, non-transferable, irrevocable
# license" anchors individually; and a preceding negation ("not ... binding",
# "no binding") refuses outright, because minting either sign for a negated
# form would be a guess. "sole", un- prefixes ("unassignable"), and bare
# qualifiers with no grant noun are documented recall gaps, never wrong
# values. ---

# Affirmative surfaces; spelling variants normalize to one stem so a flip
# across spellings still shares the stem.
_POLARITY_STEM_NORMALIZE = {
    "cancelable": "cancellable",
    "sublicenseable": "sublicensable",
    "sub-licensable": "sublicensable",
}
_POLARITY_AFFIRMATIVES = (
    "exclusive",
    "transferable",
    "assignable",
    "revocable",
    "cancellable",
    "cancelable",
    "refundable",
    "binding",
    "sublicensable",
    "sublicenseable",
    "sub-licensable",
    "waivable",
)

_POLARITY_CANON: dict[str, str] = {}
for _surf in _POLARITY_AFFIRMATIVES:
    _stem = _POLARITY_STEM_NORMALIZE.get(_surf, _surf)
    _POLARITY_CANON[_surf] = f"{_stem}+"
    _POLARITY_CANON[f"non-{_surf}"] = f"{_stem}-"
    _POLARITY_CANON[f"non{_surf}"] = f"{_stem}-"
_POLARITY_CANON["irrevocable"] = "revocable-"

_POLARITY_TOKEN = (
    r"(?:non-?)?(?:exclusive|transferable|assignable|revocable|cancell?able|"
    r"refundable|binding|sub-?license?able|waivable)|irrevocable"
)
_GRANT_NOUN = (
    r"licenses|license|licences|licence|rights|right|grants|grant|"
    r"sublicenses|sublicense|obligations|obligation|offers|offer|"
    r"agreements|agreement|warranties|warranty|commitments|commitment|"
    r"undertakings|undertaking|deposits|deposit|fees|fee|payments|payment|"
    r"arbitration|mediation|remedies|remedy"
)
# What may sit between a qualifier and its grant noun: other qualifiers and a
# closed list of cosmetic adjectives. Anything outside it breaks the run.
_POLARITY_GAP_WORD = (
    rf"(?:{_POLARITY_TOKEN}|worldwide|perpetual|limited|personal|sole|global|"
    rf"royalty-free|royalty|free|fully|paid-up|paid|up|and)"
)
# The optional single unknown word directly before the noun admits compound
# noun heads ("non-exclusive TRADEMARK license", "exclusive PATENT rights")
# without reopening the run-break guard: "the exclusive distributor shall
# hold a license" still refuses because two unknown words ("distributor",
# "shall") cannot bridge to the noun. The unknown word may not itself be a
# grant noun, so "exclusive license rights" binds to "license" (the FIRST
# grant noun) and keys the same grant as "exclusive license" — otherwise the
# same grant would key under unstable noun classes and a real flip would land
# on different keys (round-3 note 1).
_POLARITY = re.compile(
    rf"\b(?P<tok>{_POLARITY_TOKEN})\b"
    rf"(?=(?:[,\s]+{_POLARITY_GAP_WORD}\b){{0,6}}(?:\s+(?!(?:{_GRANT_NOUN})\b)[A-Za-z][A-Za-z-]*)?"
    rf"[,\s]+(?P<noun>{_GRANT_NOUN})\b)",
    re.IGNORECASE,
)
# Predicative position: "the license granted hereunder is non-exclusive",
# "this Agreement is binding". The copula must directly precede the qualifier,
# which structurally refuses "is not exclusive" and "shall not be binding"
# (the negator breaks the adjacency, and no sign is ever guessed).
_POLARITY_PREDICATIVE = re.compile(
    rf"\b(?P<noun>{_GRANT_NOUN})\b[^.;:]{{0,30}}?\b(?:is|are|remains?|shall\s+be|will\s+be)\s+"
    rf"(?P<tok>{_POLARITY_TOKEN})\b",
    re.IGNORECASE,
)
# Scope negation ("nothing herein creates a binding obligation", "without
# granting an exclusive license", "in no event", "neither ... nor") reverses
# the qualifier's meaning from anywhere earlier in the sentence segment. The
# bounded grammar cannot represent negation scope, so ANY negator in the
# segment before the qualifier refuses the anchor outright; the segment is
# bounded at [.;:] so a prior sentence's negation cannot suppress a clean
# grant after it. False refusals ("not later than 30 days, Licensor grants an
# exclusive license") are recall loss in the safe direction.
_POLARITY_SCOPE_NEG = re.compile(
    r"\b(?:not|no|never|nothing|neither|nor|without|except)\b",
    re.IGNORECASE,
)

# Plural and spelling-variant grant nouns fold to one class so a flip across
# forms still shares a comparison key.
_NOUN_CLASS = {
    "licenses": "license",
    "licences": "license",
    "licence": "license",
    "rights": "right",
    "grants": "grant",
    "sublicenses": "sublicense",
    "obligations": "obligation",
    "offers": "offer",
    "agreements": "agreement",
    "warranties": "warranty",
    "commitments": "commitment",
    "undertakings": "undertaking",
    "deposits": "deposit",
    "fees": "fee",
    "payments": "payment",
    "remedies": "remedy",
}


def _noun_class(surface: str) -> str:
    lowered = surface.lower()
    return _NOUN_CLASS.get(lowered, lowered)


# Every word the polarity grammar can emit, for callers that must exclude the
# qualifiers themselves when reading a noun's SUBJECT MATTER (a predicative
# "license granted is non-exclusive" puts the qualifier inside the post-noun
# window; it is vocabulary, not subject matter).
POLARITY_VOCAB = frozenset(
    w for key in _POLARITY_CANON for w in re.findall(r"[a-z]+", key)
) | frozenset({"non"})


def grant_noun_pattern(noun_class: str) -> str:
    """Alternation of every surface form of a grant-noun class (plural and
    spelling variants included), longest-first. Used by the contract path to
    locate the qualified noun's subject matter in raw clause text."""
    surfaces = [s for s, c in _NOUN_CLASS.items() if c == noun_class] + [noun_class]
    return "|".join(re.escape(s) for s in sorted(set(surfaces), key=len, reverse=True))


# Every grant-noun surface, for callers that must exclude the nouns themselves
# (and their plural variants) when reading SUBJECT MATTER around a qualified
# noun — "license", "rights", "fee" name the grant, not what it covers.
GRANT_NOUN_WORDS = (
    frozenset(_NOUN_CLASS)
    | frozenset(_NOUN_CLASS.values())
    | frozenset({"arbitration", "mediation"})
)


def _polarity_anchors(text: str) -> list[Anchor]:
    anchors: list[Anchor] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in (_POLARITY, _POLARITY_PREDICATIVE):
        for m in pattern.finditer(text):
            span = (m.start("tok"), m.end("tok"))
            if span in seen_spans:
                continue
            segment_start = max(text.rfind(ch, 0, span[0]) for ch in ".;:") + 1
            if _POLARITY_SCOPE_NEG.search(text[segment_start : span[0]]):
                continue
            seen_spans.add(span)
            sign = _POLARITY_CANON[m.group("tok").lower()]
            # canonical = "{stem}:{noun-class}{sign}": the noun class travels
            # with the value so "exclusive license" and "exclusive remedy" can
            # never compare against each other (the cross-noun false green).
            canonical = f"{sign[:-1]}:{_noun_class(m.group('noun'))}{sign[-1]}"
            anchors.append(Anchor("polarity", m.group("tok"), span[0], span[1], canonical))
    return anchors


# --- Party-name detector (canonical_value None). Two T0 sub-patterns. Real NER
# for un-aliased names is T1 and off (per the design doc), so the entity branch is
# a best-effort T0 heuristic with two inherent capitalized-word limits, both
# documented + tested and routed to the verifier (never a false verdict; the
# precision/recall point is an operator human-gate call): a capitalized prose word
# directly before a suffix is swept in ("Defendant Stark Industries LLC"), and an
# all-caps heading whose suffix is itself all-caps (LLC/LP/PLC) can match ("THE
# BOARD LLC"). The parenthetical-alias branch has no such ambiguity. ---

# Defined-party alias in parentheses: ("Buyer"), (the "Seller"), (the "Initial
# Purchaser"). Unambiguous and precise.
_PARTY_ALIAS = re.compile(r"""\((?:the\s+)?["“']([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)*)["”']\)""")
# Company name ending in an UNAMBIGUOUS corporate suffix abbreviation. The
# terminal "(?:\.(?![A-Za-z])|(?![A-Za-z.-]))" stops a suffix from matching a
# longer word ("Corporate", "LLCs", "Incorporated"), a dot-then-letter
# ("Corp.oration", "L.P.s"), or a hyphen-adjective ("PLC-level", "Inc-owned"),
# while still allowing the optional trailing dot ("Inc."). Generic "Company"/"Co"
# and the spelled-out forms "Corporation"/"Limited"/"N.A" are excluded (common
# English words that false-positive in prose like "The Limited Partners") - a
# documented recall gap. "and" is NOT a connector (it joins distinct parties);
# "&"/"of" are (within-name: "Bank of America").
_PARTY_ENTITY = re.compile(
    r"\b[A-Z][A-Za-z0-9&.'\-]*(?:\s(?:&|of|[A-Z][A-Za-z0-9&.'\-]*))*"
    r",?\s(?:Inc|LLC|L\.L\.C|Corp|Ltd|L\.P|LP|PLC|GmbH)(?:\.(?![A-Za-z])|(?![A-Za-z.\-]))"
)

# Defined-term definition pattern: a quoted, capitalized term (one or more words,
# all-caps included) immediately followed by `means | shall mean | refers to`. The
# parenthetical-alias form (the "Term") reuses _PARTY_ALIAS. Case-sensitive on the
# leading capital, so a lowercase "buyer" is not captured. It DOES over-capture a
# rhetorical `"X" means Y` from prose (e.g. `"Justice" means a lot`); that is the
# safe direction - an extra review anchor routed to the tray, never a false verdict;
# whether to tighten is a human gate. Single-letter and hyphenated terms ("A",
# "Class A", "Non-Competition") are a documented recall gap.
_DEFN = re.compile(
    r"""["“']([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)*)["”']"""
    r"\s+(?:means|shall\s+mean|refers?\s+to|shall\s+refer\s+to)\b"
)

_DATE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}"
    r"|(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4})\b"
)

# --- Governing-law detector (canonical_value = normalized jurisdiction key). A
# falsified choice of law is the contract path's most consequential single-token
# error, and it is pure string equality after lexicon normalization. Precision is
# structural on two sides: the TRIGGER side fires only on governing verbs
# ("governed by", "construed ... laws of", "X law governs/applies"), so forum
# selection ("courts of Delaware"), incorporation ("a Delaware corporation"), and
# liability propositions ("liable under New York law") never anchor; the VALUE
# side is a closed lexicon (US states + DC + the major commercial and GCC/MENA
# jurisdictions), so an unknown jurisdiction yields NO anchor, never a guessed
# canonical. Adjectival forms map to the jurisdiction they designate ("English
# law" -> england and wales, the conventional referent) so the contradiction
# check cannot accuse a summary across a naming variant. Jurisdictions outside
# the lexicon are a documented recall gap (could-not-check, the safe direction),
# not a hidden one. ---

_US_STATES = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming",
    "District of Columbia",
)  # fmt: skip

# Non-US jurisdictions and adjectival forms: surface (lowercase) -> canonical key.
_JURISDICTION_ALIASES = {
    "england and wales": "england and wales",
    "england": "england and wales",
    "english": "england and wales",
    "scotland": "scotland",
    "scots": "scotland",
    "scottish": "scotland",
    "northern ireland": "northern ireland",
    "ireland": "ireland",
    "irish": "ireland",
    "france": "france",
    "french": "france",
    "germany": "germany",
    "german": "germany",
    "switzerland": "switzerland",
    "swiss": "switzerland",
    "netherlands": "netherlands",
    "dutch": "netherlands",
    "belgium": "belgium",
    "belgian": "belgium",
    "luxembourg": "luxembourg",
    "spain": "spain",
    "spanish": "spain",
    "italy": "italy",
    "italian": "italy",
    "sweden": "sweden",
    "swedish": "sweden",
    "norway": "norway",
    "norwegian": "norway",
    "denmark": "denmark",
    "danish": "denmark",
    "finland": "finland",
    "finnish": "finland",
    "austria": "austria",
    "austrian": "austria",
    "poland": "poland",
    "polish": "poland",
    "portugal": "portugal",
    "portuguese": "portugal",
    "greece": "greece",
    "greek": "greece",
    "cyprus": "cyprus",
    "malta": "malta",
    "singapore": "singapore",
    "hong kong": "hong kong",
    "japan": "japan",
    "japanese": "japan",
    "india": "india",
    "indian": "india",
    "china": "china",
    "chinese": "china",
    "people's republic of china": "china",
    "south korea": "south korea",
    "south korean": "south korea",
    "korean": "south korea",
    "australia": "australia",
    "australian": "australia",
    "new south wales": "new south wales",
    "new zealand": "new zealand",
    "canada": "canada",
    "canadian": "canada",
    "ontario": "ontario",
    "british columbia": "british columbia",
    "quebec": "quebec",
    "united states": "united states",
    "united arab emirates": "united arab emirates",
    "uae": "united arab emirates",
    "dubai international financial centre": "difc",
    "difc": "difc",
    "abu dhabi global market": "adgm",
    "adgm": "adgm",
    "dubai": "dubai",
    "abu dhabi": "abu dhabi",
    "saudi arabia": "saudi arabia",
    "saudi arabian": "saudi arabia",
    "saudi": "saudi arabia",
    "qatar": "qatar",
    "qatari": "qatar",
    "kuwait": "kuwait",
    "kuwaiti": "kuwait",
    "bahrain": "bahrain",
    "bahraini": "bahrain",
    "oman": "oman",
    "omani": "oman",
    "jordan": "jordan",
    "jordanian": "jordan",
    "egypt": "egypt",
    "egyptian": "egypt",
    "lebanon": "lebanon",
    "lebanese": "lebanon",
    "israel": "israel",
    "israeli": "israel",
    "turkey": "turkey",
    "turkish": "turkey",
    "brazil": "brazil",
    "brazilian": "brazil",
    "mexico": "mexico",
    "mexican": "mexico",
    "south africa": "south africa",
    "south african": "south africa",
    "cayman islands": "cayman islands",
    "bermuda": "bermuda",
    "british virgin islands": "british virgin islands",
    "jersey": "jersey",
    "guernsey": "guernsey",
    "isle of man": "isle of man",
}

_JURISDICTION_CANON: dict[str, str] = {
    **{state.lower(): state.lower() for state in _US_STATES},
    **_JURISDICTION_ALIASES,
}

# Containment map: canonical key -> canonical keys of jurisdictions inside it.
# A flat string mismatch between a container and one of its members ("UAE law"
# vs "DIFC law", "the laws of the United States" vs "the laws of Delaware") is
# a relationship, not a contradiction: the member's law differs from the
# container's, but a summary naming the container may be describing the member
# imprecisely rather than falsifying it. The contract path refuses such pairs
# (could-not-check) instead of accusing. SIBLING mismatches (New York vs
# Delaware, England and Wales vs Scotland, DIFC vs ADGM) stay accusable: two
# disjoint systems named against each other is the real catch.
_JURISDICTION_CONTAINS: dict[str, frozenset[str]] = {
    "united states": frozenset(state.lower() for state in _US_STATES),
    "united arab emirates": frozenset({"difc", "adgm", "dubai", "abu dhabi"}),
    "dubai": frozenset({"difc"}),
    "abu dhabi": frozenset({"adgm"}),
    "china": frozenset({"hong kong"}),
    "canada": frozenset({"ontario", "british columbia", "quebec"}),
    "australia": frozenset({"new south wales"}),
}


def related_jurisdictions(a: str, b: str) -> bool:
    """True when one canonical jurisdiction key contains the other.

    Consulted by the contract path before minting a governing-law
    contradiction; a containment pair routes to the honest could-not-check
    instead. Unknown keys are unrelated (False).
    """
    return b in _JURISDICTION_CONTAINS.get(a, ()) or a in _JURISDICTION_CONTAINS.get(b, ())


# Modifier rejector for the adjectival lexicon forms: a jurisdiction adjective
# immediately preceded by a directional or qualifying modifier designates a
# DIFFERENT body of law than the bare adjective ("North Korean law" is not
# South Korea's; "Federal Indian law" is a body of US law, not India's;
# "West German law" is historical Germany's, not the Federal Republic's).
# The bounded grammar cannot represent those, so the anchor is refused rather
# than minted with the wrong canonical. Multi-word lexicon entries ("South
# Korea", "British Columbia") match longest-first as their own surface form and
# never reach this guard with the modifier still outside the match.
_JUR_MODIFIER_BEFORE = re.compile(
    r"\b(?:north|south|east|west|federal|american|native|british|anglo)[\s\-]+$",
    re.IGNORECASE,
)

# Longest-first alternation so "West Virginia" wins over "Virginia" and
# "New Jersey" over "Jersey" (the US state vs the Channel Island).
_JUR_ALT = "|".join(re.escape(name) for name in sorted(_JURISDICTION_CANON, key=len, reverse=True))

# Form A, the contract boilerplate: a governing verb, a bounded connective run,
# then "laws of [the] [State/Commonwealth/Province of] <JUR>". The connective
# gap must read like boilerplate: all-lowercase or all-caps (the conspicuous
# clause convention), commas allowed, digits and mixed-case nouns excluded. The
# scoped (?-i:...) keeps that case discipline inside an otherwise IGNORECASE
# pattern: "governed by and construed in accordance with the" passes, while an
# intervening object that changes the proposition ("governed by Section 4, and
# payments comply with the laws of New York", "governed by ERISA and ... the
# laws of Texas") refuses the anchor rather than mint a governing-law value
# from a compliance phrase. Bare "in accordance with the laws of X" (no
# governing verb) deliberately does NOT trigger for the same reason.
_GOV_LAW_OF = re.compile(
    rf"\b(?:governed\s+by|construed)(?-i:[\sa-z,]{{0,60}}?|[\sA-Z,]{{0,60}}?)\blaws?\s+of\s+"
    rf"(?:the\s+)?(?:(?:State|Commonwealth|Province)\s+of\s+)?(?P<jur>{_JUR_ALT})\b",
    re.IGNORECASE,
)
# Form B, the summary phrasings: "governed by New York law" / "New York law
# governs" / "Delaware law applies".
_GOV_JUR_LAW = re.compile(
    rf"\bgoverned\s+by\s+(?:the\s+)?(?P<jur>{_JUR_ALT})\s+law\b",
    re.IGNORECASE,
)
# Form C, the inverted boilerplate: "the laws of [the State of] X shall
# govern". The governing verb comes AFTER the jurisdiction; the bounded
# all-lowercase gap (same case discipline as Form A) keeps an intervening
# capitalized object from bridging to a distant "govern".
_LAWS_OF_GOVERN = re.compile(
    rf"\blaws?\s+of\s+(?:the\s+)?(?:(?:State|Commonwealth|Province)\s+of\s+)?"
    rf"(?P<jur>{_JUR_ALT})\b(?-i:[\sa-z,]{{0,40}}?|[\sA-Z,]{{0,40}}?)\bgoverns?\b",
    re.IGNORECASE,
)
_JUR_LAW_GOVERNS = re.compile(
    rf"\b(?P<jur>{_JUR_ALT})\s+law\s+(?:shall\s+|will\s+)?(?:governs?|appl(?:y|ies))\b",
    re.IGNORECASE,
)

# Percent / rate, DIGIT forms only with the unit marker in-span: "5%", "12.5
# percent", "12 per cent", "50 bps", "50 basis points". Canonical value is
# basis points via exact decimal arithmetic, so "0.5%" and "50 bps" compare
# equal with no float drift and no tolerance. Refusals, each pinned by tests,
# never a guessed value: word-form percent ("five percent" — the same
# bounded-grammar lesson as _MONEY_WORD), range forms ("5-10%": the leading
# lookbehind rejects a digit-dash-digit tail, so anchoring either end cannot
# manufacture a verdict against a clause stating the other), and "percentage
# points" (an additive quantity, not a rate; `percent\b` fails inside
# "percentage" and `points` is required after `basis` only).
_PERCENT = re.compile(
    # num accepts a plain digit run or VALID US thousands grouping only; a
    # European decimal comma ("12,5%") fits neither branch and the comma in the
    # lookbehind stops the tail ("5%") from anchoring alone, so the whole form
    # refuses rather than canonicalize 12,5% as 1250%. The lookbehind also
    # carries the Unicode dash family so "5\u201310%" and minus-signed rates
    # refuse the same way the ASCII range form does.
    r"(?<![\w.,\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212])"
    r"(?P<num>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<unit>%|percent\b|per\s?cent\b|bps\b|basis\s+points?\b)",
    re.IGNORECASE,
)

# Worded/spaced range rejector for _PERCENT: a match whose preceding text ends
# with a bare number and a range connector ("5 to ", "between 5 and ", "5 - ")
# is the TOP END of a range. Anchoring it would manufacture a verdict against a
# clause stating any other point of the range (the same rule the dash lookbehind
# enforces for "5-10%"). "from 5% to 10%" is NOT rejected: both ends carry the
# unit, two anchors emerge, and the multi-value refusal handles them honestly.
_PERCENT_RANGE_BEFORE = re.compile(
    r"\d\s*(?:[-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]|\b(?:to|and|or|through)\b)\s*$",
    re.IGNORECASE,
)

_MONEY_SCALE = {
    "thousand": 1_000,
    "k": 1_000,
    "million": 1_000_000,
    "m": 1_000_000,
    "mm": 1_000_000,  # legal/finance notation: $5MM == $5 million
    "billion": 1_000_000_000,
    "b": 1_000_000_000,
}
_DURATION_DAYS = {"year": 365, "month": 30, "week": 7, "day": 1}
_MONEY_WORD_UNITS = {
    "a": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def _money_cents(text: str) -> int | None:
    """Canonical integer cents for a matched money span, or None."""
    m = re.search(
        r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|billion|thousand|MM|M|B|K)?", text, re.IGNORECASE
    )
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    scale = m.group(2)
    if scale:
        amount *= _MONEY_SCALE[scale.lower()]
    return round(amount * 100)


def _money_word_cents(unit: str, hundred: str | None, scale: str) -> int:
    """Canonical integer cents for a spelled-out money span (no numeral)."""
    amount = _MONEY_WORD_UNITS[unit.lower()]
    if hundred:
        amount *= 100
    amount *= _MONEY_SCALE[scale.lower()]
    return amount * 100


def _duration_days(num: int, unit: str) -> int:
    """Canonical day count (year=365, month=30, week=7, day=1, approximate)."""
    return num * _DURATION_DAYS[unit.lower()]


def _percent_bps(num_text: str, unit: str) -> Decimal:
    """Canonical basis points for a percent/rate span, exact decimal arithmetic."""
    value = Decimal(num_text.replace(",", ""))
    u = unit.lower()
    if u == "bps" or u.startswith("basis"):
        return value
    return value * 100


def _date_iso(text: str) -> str | None:
    try:
        return date_parser.parse(text, fuzzy=False).date().isoformat()
    except (ValueError, OverflowError):
        return None


def _governing_law_anchors(text: str) -> list[Anchor]:
    """Governing-law anchors; text/offsets are the jurisdiction surface form.

    The same choice of law stated twice in one span (e.g. matched by both the
    long form and the summary form) dedupes by span, and downstream
    canonical-value dedup collapses equal keys, so one stated jurisdiction is
    always one fact.
    """
    anchors: list[Anchor] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in (_GOV_LAW_OF, _GOV_JUR_LAW, _JUR_LAW_GOVERNS, _LAWS_OF_GOVERN):
        for m in pattern.finditer(text):
            span = (m.start("jur"), m.end("jur"))
            if span in seen_spans:
                continue
            if _JUR_MODIFIER_BEFORE.search(text[: span[0]]):
                # A modified adjective ("North Korean", "Federal Indian"): the
                # match is only the tail of the real designation. Refuse the
                # anchor rather than mint the wrong jurisdiction.
                continue
            seen_spans.add(span)
            canonical = _JURISDICTION_CANON[m.group("jur").lower()]
            anchors.append(Anchor("governing_law", m.group("jur"), span[0], span[1], canonical))
    return anchors


def _party_anchors(text: str) -> list[Anchor]:
    anchors: list[Anchor] = []
    for pattern in (_PARTY_ALIAS, _PARTY_ENTITY):
        for m in pattern.finditer(text):
            anchors.append(Anchor("party", m.group(0), m.start(), m.end()))
    return anchors


def build_alias_table(text: str) -> dict[str, str]:
    """Build a {defined-term -> canonical} map from a document's own definitions.

    Two T0 sources: the parenthetical alias form `(the "Buyer")` and the
    definition form `"Confidential Information" means ...`. canonical is the
    defined term itself (the normalization key); a richer canonical (what the term
    resolves to) is left to a later unit. Pass the result to `extract_anchors` as
    `alias_table` to detect occurrences of these terms as `defined_term` anchors.
    """
    table: dict[str, str] = {}
    for pattern in (_PARTY_ALIAS, _DEFN):
        for m in pattern.finditer(text):
            term = m.group(1)
            table[term] = term
    return table


def _defined_term_anchors(text: str, alias_table: dict[str, str]) -> list[Anchor]:
    # Occurrences of an actually-defined term. Precision is structural: only terms
    # the document itself defined are in the table, so this cannot fire on an
    # undefined capitalized word. canonical_value is the term's canonical form
    # (from the table, not the matched text). Terms are matched literally
    # (re.escape) at word boundaries; a term whose edge char is non-word (e.g.
    # "U.S.") may not match - build_alias_table only ever produces word-edge terms.
    anchors: list[Anchor] = []
    for term, canonical in alias_table.items():
        for m in re.finditer(rf"\b{re.escape(term)}\b", text):
            anchors.append(Anchor("defined_term", m.group(0), m.start(), m.end(), canonical))
    return anchors


def extract_anchors(span: str, *, alias_table: dict[str, str] | None = None) -> list[Anchor]:
    """Return every verifiable anchor in ``span`` (possibly several types).

    ``alias_table`` ({defined-term -> canonical}, e.g. from
    :func:`build_alias_table`) turns on the defined-term detector: occurrences of
    each defined term become ``defined_term`` anchors. With the default ``None``,
    no defined-term anchors are emitted and the result is identical to the other
    detectors alone. Anchors are returned sorted in document order.
    """
    if not span or not span.strip():
        return []
    anchors: list[Anchor] = []
    citation_spans: list[tuple[int, int]] = []
    for ref in find_citations(span):
        anchors.append(Anchor("citation", ref.matched_text, ref.start, ref.end))
        citation_spans.append((ref.start, ref.end))

    def _within_citation(a: Anchor) -> bool:
        return any(a.start < ce and cs < a.end for cs, ce in citation_spans)

    for m in _SLIP_OP.finditer(span):
        anchors.append(Anchor("slip_op", m.group(0), m.start(), m.end()))
    for text, start, end in extract_draft_quote_spans(span):
        anchors.append(Anchor("quote", text, start, end))
    for m in _MONEY.finditer(span):
        anchors.append(Anchor("money", m.group(0), m.start(), m.end(), _money_cents(m.group(0))))
    for m in _MONEY_WORD.finditer(span):
        if _NUMBER_WORD_BEFORE.search(span[: m.start()]):
            # A space-separated compound ("twenty five million dollars"): the
            # match is only the tail of the real number. Refuse the anchor
            # rather than mint a wrong canonical value.
            continue
        cents = _money_word_cents(m.group("unit"), m.group("hundred"), m.group("scale"))
        anchors.append(Anchor("money", m.group(0), m.start(), m.end(), cents))
    for m in _DURATION.finditer(span):
        num = int(m.group("paren") or m.group("num"))
        anchors.append(
            Anchor("duration", m.group(0), m.start(), m.end(), _duration_days(num, m.group("unit")))
        )
    for m in _DATE.finditer(span):
        iso = _date_iso(m.group(0))
        if iso is not None:
            # Drop date-shaped but invalid values (2024-13-45) rather than emit
            # an anchor whose canonical_value is None (two would compare equal).
            anchors.append(Anchor("date", m.group(0), m.start(), m.end(), iso))
    for m in _PERCENT.finditer(span):
        if _PERCENT_RANGE_BEFORE.search(span[: m.start()]):
            # The top end of a worded/spaced range ("between 5 and 10%"):
            # refuse the anchor rather than collapse a range to one endpoint.
            continue
        anchors.append(
            Anchor(
                "percent",
                m.group(0),
                m.start(),
                m.end(),
                _percent_bps(m.group("num"), m.group("unit")),
            )
        )
    for m in _SECTION.finditer(span):
        # A "section" hit inside a citation span is that citation's own section
        # symbol (e.g. the "§ 1983" of "42 U.S.C. § 1983"), not an intra-document
        # section reference; drop it so a statute is not double-counted. A
        # standalone section reference has no overlapping citation and survives.
        candidate = Anchor("section", m.group(0), m.start(), m.end())
        if not _within_citation(candidate):
            anchors.append(candidate)
    anchors.extend(_governing_law_anchors(span))
    anchors.extend(_polarity_anchors(span))
    anchors.extend(_party_anchors(span))
    if alias_table:
        anchors.extend(_defined_term_anchors(span, alias_table))
    anchors.sort(key=lambda a: (a.start, a.end))
    return anchors


def has_anchor(span: str) -> bool:
    """True if ``span`` carries any verifiable anchor."""
    return bool(extract_anchors(span))
