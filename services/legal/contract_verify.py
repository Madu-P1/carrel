"""Contract-claim verification (Cachet contract path, Phase 6).

Given one claim (a sentence from an AI-drafted summary of a contract) and a
candidate clause from the executed contract, decide deterministically (T0):

  - ``parametric_contradiction``: the claim's number / date / duration differs
    from the clause's same-type value. Pure arithmetic after regex extraction,
    no model. This is the gold case the litigator path cannot match.
  - ``present``: the claim's value or quoted language appears in the clause.
    This attests that the language appears, NEVER that the surrounding
    proposition is legally correct (a carve-out can change the meaning), so the
    detail tells the reader to review the full passage for context.
  - ``multi_value_unverifiable``: the claim and the clause each carry more than
    one value of the same type, so a deterministic check cannot align them
    one-to-one. Routed to the could-not-check tray instead of guessing: a guessed
    match would MASK a contradiction and a guessed miss would be a false
    accusation (ADR-0012 invariant 2). Role-aligned multi-value checking is T1.
  - ``not_found``: the claim asserts a value or language the clause does not
    contain. The honest scope exit, never dressed as a clean pass.

No LLM, no network. Money and date compare exactly; duration compares within a
small tolerance so equivalent terms ("12 months" vs "1 year") are not flagged
as a contradiction by the day-count approximation.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, replace

from services.legal.anchors import (
    GRANT_NOUN_WORDS,
    POLARITY_VOCAB,
    Anchor,
    extract_anchors,
    grant_noun_pattern,
    parse_grouped_number,
    polarity_flip_pairs,
    related_jurisdictions,
)
from ai.subject_labeler import get_subject_labeler
from services.retrieval.validators import verbatim_run_present

# percent compares by exact basis-point equality through the default
# set-intersection branch of _values_match (Decimal hashes by numeric value, so
# "0.5%" and "50 bps" intersect); governing_law compares normalized jurisdiction
# keys through the same branch (lexicon normalization makes "English law" and
# "laws of England and Wales" one key); duration alone keeps a tolerance.
# polarity is adjudicated PER STEM (a dedicated pass), because its values are
# heterogeneous across stems and a whole-type comparison would let a matching
# qualifier mask a flipped sibling.
_PARAMETRIC_TYPES = (
    "money",
    "magnitude",
    "percent",
    "date",
    "duration",
    "governing_law",
    "polarity",
)

# --- Near-verbatim altered-figure pass ---------------------------------------
# When a lawyer pastes a slide or passage VERBATIM and an AI (or a typo) has
# changed a number, the per-anchor path reports at most ONE altered figure and
# silently drops the rest (the BIM-lecture slide: "7 billion" altered from "2
# billion" went unreported while only the "26% vs 16%" showed; with ONLY the
# billion altered the sentence even read "present"). This pass names EVERY altered
# figure at once. Safe by construction (see _altered_figures_on_near_copy): it
# fires only on a near-identical skeleton with at least one figure value shared,
# and flags only a claim value that appears NOWHERE in the source, so a reorder or
# an unrelated sentence is never accused. It returns None on anything else and the
# normal anchor logic runs unchanged.
_SCALE_UNITS = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_NEAR_COPY_RATIO = 0.90

# A FIGURE is a number that is clearly a QUANTITY (a magnitude with a scale word, a
# percent, a currency amount, a 4-digit year, or a grouped large number), never a
# bare identifier digit ("Q1", "Section 8", "Pillar 1", "23 States"). That bound is
# what keeps "Pillar 1 vs Pillar 2" and "23 States" out of the positional diff.
_FIGURE = re.compile(
    r"(?:EUR|USD|GBP|\$)\s?\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand))?"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:billion|million|thousand)"
    r"|\d+(?:\.\d+)?\s*%"
    r"|(?:19|20)\d{2}"
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?",
    re.IGNORECASE,
)


def _figure_value(surface: str) -> float | None:
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand)?", surface, re.IGNORECASE)
    if not m:
        return None
    value = parse_grouped_number(m.group(1))
    if value is None:
        # Ambiguous comma-decimal ("1,2 billion"): refuse rather than diff a wrong
        # value (the whole near-copy pass then returns None and the anchor logic runs).
        return None
    scale = m.group(2)
    if scale:
        value *= _SCALE_UNITS[scale.lower()]
    return value


def _figure_shape(surface: str) -> str:
    s = surface.lower()
    if "%" in s:
        return "percent"
    for scale in ("billion", "million", "thousand"):
        if scale in s:
            return scale
    if re.fullmatch(r"\s*(?:19|20)\d{2}\s*", s):
        return "year"
    return "number"


def _number_digits(surface: str) -> str:
    """The bare digit sequence of a figure, separators and scale words stripped, so
    "1.2 billion", "1,2 billion", and "12 billion" all collapse to "12". Used to tell a
    NOTATION variance (a decimal-comma vs a decimal-point of the same value) from a
    genuine alteration when one side wrote the value as an ambiguous comma-decimal the
    canonical path skipped."""
    body = re.sub(r"(?:billion|million|thousand)", "", surface, flags=re.IGNORECASE)
    return re.sub(r"\D", "", body)


def _figure_skeleton(text: str, figures: list[re.Match]) -> str:
    """The text with every figure replaced by a placeholder, normalized for the
    similarity gate. Two passages whose only differences are their figures (a
    copy with numbers changed) collapse to the SAME skeleton."""
    out: list[str] = []
    last = 0
    for m in figures:
        out.append(text[last : m.start()])
        out.append("#")
        last = m.end()
    out.append(text[last:])
    return re.sub(r"[^a-z0-9#]+", " ", "".join(out).lower()).strip()


def _canonical_figures(matches: list[re.Match]) -> list[tuple[str, str, float]]:
    """(surface, shape, value) for each canonicalizable figure match.

    SKIPS an uncanonical figure (an ambiguous comma-decimal like "1,2 billion")
    rather than discarding the whole pass. Bailing on the first such figure meant
    one comma-decimal disabled the entire altered-figure catch for the sentence:
    on the BIM slide, "1,2 billion" turned off the catch of a genuinely-altered
    "60 billion" sitting right beside it. The skipped figure is simply absent from
    the (shape, value) membership test below, so it is never diffed (consistent
    with the engine already refusing to adjudicate ambiguous comma-decimals) while
    every canonicalizable figure is still compared."""
    out: list[tuple[str, str, float]] = []
    for m in matches:
        text = m.group(0).strip()
        value = _figure_value(text)
        if value is None:
            continue
        out.append((text, _figure_shape(text), value))
    return out


def _altered_figures_on_near_copy(claim: str, clause: str, where: str) -> ClauseVerdict | None:
    """Return a contradiction naming the altered figures when ``claim`` is a
    near-verbatim copy of ``clause`` with numbers changed, else None (the normal
    anchor logic then runs).

    Safe by construction, three gates that together cannot accuse a reorder or an
    unrelated sentence:
      1. NEAR-VERBATIM: the two texts are near-identical once the figures are
         masked (a paraphrase falls through).
      2. SHARED FIGURE: at least one figure value is identical on both sides, so
         the claim is provably derived from THIS clause, not a coincidental match.
      3. ABSENT VALUE: a claim figure is only ever flagged when its value appears
         NOWHERE in the clause. A value present elsewhere in the clause is a
         reorder, never a tamper, so it is never accused (the (shape, value)
         membership test, not a positional pairing).
    """
    claim_figs = list(_FIGURE.finditer(claim))
    clause_figs = list(_FIGURE.finditer(clause))
    if not claim_figs or len(claim_figs) != len(clause_figs):
        return None
    ratio = difflib.SequenceMatcher(
        None, _figure_skeleton(claim, claim_figs), _figure_skeleton(clause, clause_figs)
    ).ratio()
    if ratio < _NEAR_COPY_RATIO:
        return None
    claim_canon = _canonical_figures(claim_figs)
    clause_canon = _canonical_figures(clause_figs)
    claim_keys = {(shape, value) for _, shape, value in claim_canon}
    clause_keys = {(shape, value) for _, shape, value in clause_canon}
    if not (claim_keys & clause_keys):
        # No shared figure: two same-shaped but unrelated sentences. Naming a
        # pairing would be a guess (the multi-value refusal handles this).
        return None
    claim_only = [c for c in claim_canon if (c[1], c[2]) not in clause_keys]
    clause_only = [c for c in clause_canon if (c[1], c[2]) not in claim_keys]
    # Finding 7 (xhigh review): a claim figure the canonical set reports "absent" may
    # simply be the SAME value the clause wrote as an ambiguous comma-decimal the
    # canonical path skipped ("1.2 billion" vs the source's "1,2 billion"). Never accuse
    # a notation variance: drop a claim_only figure whose shape AND bare digits match a
    # skipped uncanonical clause figure (could-not-check via the normal path, not a
    # false contradiction). A genuinely altered figure beside a comma-decimal ("60
    # billion" for "20 billion", with "1,2 billion" present) has different digits and is
    # still caught.
    clause_uncanon = [
        (m.group(0).strip(), _figure_shape(m.group(0).strip()))
        for m in clause_figs
        if _figure_value(m.group(0).strip()) is None
    ]
    if clause_uncanon:
        claim_only = [
            c
            for c in claim_only
            if not any(
                shape == c[1] and _number_digits(text) == _number_digits(c[0])
                for text, shape in clause_uncanon
            )
        ]
    if not claim_only:
        # Every claim figure appears in the clause (an exact copy or a reorder), or the
        # only "absent" ones are notation variants of a skipped comma-decimal: not a
        # contradiction.
        return None
    # Pair each altered claim figure with a same-shape source figure (in order) for
    # the filing-grade detail; an altered figure with no same-shape source value is
    # named as absent rather than mispaired.
    diffs: list[tuple[str, str | None]] = []
    remaining = list(clause_only)
    for c_text, c_shape, _c_val in claim_only:
        match = next((i for i, (_, s, _v) in enumerate(remaining) if s == c_shape), None)
        if match is not None:
            diffs.append((c_text, remaining.pop(match)[0]))
        else:
            diffs.append((c_text, None))
    if len(diffs) == 1 and diffs[0][1] is not None:
        detail = f"The summary states {diffs[0][0]}; {where} states {diffs[0][1]}."
    else:
        parts = "; ".join(
            f"{claim_text} (the source states {src})"
            if src is not None
            else f"{claim_text} (not found in the source)"
            for claim_text, src in diffs
        )
        detail = f"The summary's figures differ from {where}: {parts}."
    return ClauseVerdict(
        "parametric_contradiction",
        detail,
        "figure",
        tuple(claim_text for claim_text, _ in diffs),
        tuple(src for _, src in diffs if src is not None),
        claim_span=diffs[0][0],
        clause_span=diffs[0][1],
        where=where,
    )


_DURATION_REL_TOLERANCE = 0.05
_DURATION_UNIT = re.compile(r"\b(year|month|week|day)s?\b", re.IGNORECASE)


@dataclass(frozen=True)
class ClauseVerdict:
    # present | parametric_contradiction | multi_value_unverifiable |
    # conflicting_clauses | not_found
    disposition: str
    detail: str
    anchor_type: str | None = None
    claim_values: tuple = ()
    clause_values: tuple = ()
    # The matched anchor spans (claim side / clause side) and the clause's own
    # "where" phrase, carried so the cross-clause adjudicator can compose a
    # filing-grade conflict detail naming both clauses without string surgery.
    # Server-internal (the contract_verdict never serializes to the wire).
    claim_span: str | None = None
    clause_span: str | None = None
    where: str | None = None


@dataclass(frozen=True)
class ClauseCandidate:
    """One retrieved clause's verdict, in retrieval-rank order, for the
    cross-clause adjudicator. ``on_topic`` is the C3 relevance gate's answer
    for present-shaped candidates and, since the accuser-selection fix, for
    parametric contradictions too (there it only ORDERS which accuser supplies
    the evidence, never gates whether an accusation stands). True for
    everything else."""

    verdict: ClauseVerdict
    section: str | None
    clause_text: str | None
    on_topic: bool


def _within_tolerance(a: float, b: float, rel: float = _DURATION_REL_TOLERANCE) -> bool:
    if a == b:
        return True
    hi = max(abs(a), abs(b)) or 1
    return abs(a - b) / hi <= rel


def _duration_unit(text: str) -> str | None:
    m = _DURATION_UNIT.search(text)
    return m.group(1).lower() if m else None


def _durations_match(claim_anchor: Anchor, clause_anchor: Anchor) -> bool:
    """Whether two single duration anchors agree.

    The 5% tolerance exists ONLY to bridge the day-count approximation across
    units (12 months canonicalizes to 360 days, 1 year to 365; the terms are
    the same). Within one unit there is no approximation to bridge, so the
    compare is exact: 23 months vs 24 months is a different term, not a
    rounding artifact, and a 360 vs 365 days basis is a real financial
    difference. An anchor whose unit cannot be re-derived (should not happen;
    the detector requires the unit word) falls back to the tolerant compare,
    the lenient pre-existing behavior.
    """
    claim_unit = _duration_unit(claim_anchor.text)
    clause_unit = _duration_unit(clause_anchor.text)
    if claim_unit is not None and claim_unit == clause_unit:
        return claim_anchor.canonical_value == clause_anchor.canonical_value
    return _within_tolerance(
        float(claim_anchor.canonical_value), float(clause_anchor.canonical_value)
    )


def _values_match(claim_values: list, clause_values: list) -> bool:
    # Invoked only on SINGLE-value pairs (one value per side): the caller routes any
    # multi-value type to multi_value_unverifiable, because "any matches any" cannot
    # align multiple values and would mask a contradiction (a claim's $1M cap spuriously
    # matching a clause's unrelated $1M line item). On a single pair the intersection
    # test is exact equality. Durations are compared by the caller via
    # `_durations_match` (unit-aware); this helper covers money and date.
    return bool(set(claim_values) & set(clause_values))


def _normalized_anchor_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _present_detail(claim_anchor: Anchor, clause_anchor: Anchor, where: str) -> str:
    """A literally-true detail line for a parametric present.

    Three forms, because the certification record stands on its own and must
    never assert text the clause does not contain:
      - identical written forms: "X appears in Section 8"
      - same value, different written form: "the summary's X matches Y in ..."
      - tolerant cross-unit duration: "the summary's X is consistent with Y in ..."
    """
    if _normalized_anchor_text(claim_anchor.text) == _normalized_anchor_text(clause_anchor.text):
        return f"{claim_anchor.text} appears in {where}; review the full passage for context."
    if claim_anchor.canonical_value == clause_anchor.canonical_value:
        return (
            f"The summary's {claim_anchor.text} matches {clause_anchor.text} in {where}; "
            "review the full passage for context."
        )
    return (
        f"The summary's {claim_anchor.text} is consistent with {clause_anchor.text} in {where}; "
        "review the full passage for context."
    )


# Function words, contract boilerplate, party roles, and cosmetic adjectives
# excluded when comparing the subject matter around a qualified grant noun
# ("license to use the SOFTWARE", "the TRADEMARK license"). Grant-noun and
# polarity vocabulary are excluded separately below.
_OBJECT_STOPWORDS = frozenset(
    {
        "this",
        "that",
        "these",
        "those",
        "with",
        "shall",
        "will",
        "under",
        "during",
        "herein",
        "hereunder",
        "hereto",
        "thereof",
        "thereto",
        "hereby",
        "pursuant",
        "term",
        "terms",
        "party",
        "parties",
        "granted",
        "grants",
        "receives",
        "section",
        "licensor",
        "licensee",
        "grantor",
        "grantee",
        "lessor",
        "lessee",
        "buyer",
        "seller",
        "vendor",
        "supplier",
        "customer",
        "client",
        "recipient",
        "worldwide",
        "perpetual",
        "limited",
        "personal",
        "sole",
        "global",
        "royalty",
        "free",
        "fully",
        "paid",
    }
)


def _noun_objects(text: str, noun_class: str) -> frozenset[str]:
    """Content words naming the subject matter around a grant noun.

    Bounded T0: for every surface form of the noun class, take the window up
    to the next [.;:,] after it AND back to the previous [.;:,] before it
    (max 60 chars each — "the TRADEMARK license" puts the subject matter
    pre-noun) and keep 4+ letter words minus boilerplate, qualifier
    vocabulary, and the grant nouns themselves. Empty means the side states
    no subject matter for this noun.
    """
    words: set[str] = set()
    for m in re.finditer(rf"\b(?:{grant_noun_pattern(noun_class)})\b", text, re.IGNORECASE):
        after = re.split(r"[.;:,]", text[m.end() : m.end() + 60], maxsplit=1)[0]
        before = re.split(r"[.;:,]", text[max(0, m.start() - 60) : m.start()])[-1]
        # The backward window stops at a granting verb so it reads the noun's
        # modifiers ("the TRADEMARK license"), never the sentence subject —
        # "The Company hereby grants an exclusive license" names a grantor,
        # not subject matter, and reading it suppressed real flips (round-3
        # note 2).
        before = re.split(
            r"\b(?:grants?|granted|granting|conveys?|issues?|provides?|"
            r"receives?|retains?|holds?|delivers?)\b",
            before,
            flags=re.IGNORECASE,
        )[-1]
        for window in (before, after):
            words.update(
                w
                for w in re.findall(r"[a-z]{4,}", window.lower())
                if w not in _OBJECT_STOPWORDS
                and w not in POLARITY_VOCAB
                and w not in GRANT_NOUN_WORDS
            )
    return frozenset(words)


def _grant_noun_count(text: str, noun_class: str) -> int:
    """How many times a grant noun of ``noun_class`` occurs in ``text``.

    One occurrence means there is a single grant of that kind in play, so a bare
    side cannot be referring to some OTHER grant of the class — the disambiguation
    that lets an asymmetric polarity FLIP stand as a contradiction.
    """
    return len(re.findall(rf"\b(?:{grant_noun_pattern(noun_class)})\b", text, re.IGNORECASE))


def _polarity_pass(
    claim_hits: list, clause_hits: list, where: str, claim: str, clause: str
) -> tuple[ClauseVerdict | None, ClauseVerdict | None, ClauseVerdict | None, ClauseVerdict | None]:
    """Per-(stem, noun-class) polarity adjudication:
    (contradiction, multi, present, not_found).

    Each key ("exclusive:license", "binding:arbitration", ...) is its own
    comparison, and the verdict's anchor_type is key-qualified
    ("polarity:exclusive:license") so the cross-clause adjudicator's same-type
    rules also operate per key — an exclusive REMEDY can never confirm or veto
    a claim about an exclusive LICENSE. A flip on any key is a contradiction
    even when a sibling key matches; one key carrying both signs on a side
    refuses; a key the clause never qualifies is an honest not_found.

    Subject-matter gate (round-2 hardening): the two qualifiers may describe
    different grants that are simultaneously true (an exclusive Software
    license beside a non-exclusive Documentation license), and comparing them
    in either direction would manufacture certainty. The pair refuses when
    the sides' stated subject matter cannot be matched:

    - ASYMMETRY: one side names subject matter and the other is bare. "The
      license is exclusive" cannot be aligned to "a non-exclusive license to
      the source code" — which license is unknowable deterministically.
    - MUTUAL DIFFERENCE: each side carries a content word the other lacks
      ("Product source code" vs "Product user manual" — a shared generic
      word does not make them the same grant).

    Both bare, equal, or one-a-subset-of-the-other still compares: verbose
    restatement of the same subject matter keeps the catch.
    """

    def by_key(hits: list) -> dict[str, list]:
        grouped: dict[str, list] = {}
        for a in hits:
            grouped.setdefault(str(a.canonical_value)[:-1], []).append(a)
        return grouped

    claim_keys = by_key(claim_hits)
    clause_keys = by_key(clause_hits)
    contradiction = multi = present = not_found = None
    for key, c_hits in claim_keys.items():
        k_hits = clause_keys.get(key, [])
        qualified = f"polarity:{key}"
        stem, noun = key.split(":", 1)
        c_vals = tuple(dict.fromkeys(a.canonical_value for a in c_hits))
        k_vals = tuple(dict.fromkeys(a.canonical_value for a in k_hits))
        if not k_hits:
            if not_found is None:
                not_found = ClauseVerdict(
                    "not_found",
                    f"The summary states {c_hits[0].text}, which the deterministic check "
                    "could not locate in your loaded sources.",
                    qualified,
                    c_vals,
                    (),
                )
            continue
        if len(c_vals) > 1 or len(k_vals) > 1:
            if multi is None:
                multi = ClauseVerdict(
                    "multi_value_unverifiable",
                    (
                        f"The summary and {where} carry {stem} qualifiers that cannot be "
                        "aligned one-to-one deterministically, so this sentence was not "
                        "independently checked."
                    ),
                    qualified,
                    c_vals,
                    k_vals,
                )
            continue
        claim_objects = _noun_objects(claim, noun)
        clause_objects = _noun_objects(clause, noun)
        asymmetric = bool(claim_objects) != bool(clause_objects)
        mutually_different = bool(claim_objects - clause_objects) and bool(
            clause_objects - claim_objects
        )
        # A pure asymmetry (one side names subject matter, the other is bare) is an
        # alignment gap ONLY when the bare side could be talking about a DIFFERENT grant
        # of this noun class than the named one. With exactly one grant noun of the class
        # on each side there is a single grant in play, so a polarity FLIP is a real
        # contradiction the reader must see — the same "one license in play" logic that
        # already lets a both-bare flip stand. A same-sign MATCH is still refused even
        # then (confirming a green from an unaligned subject would be a guess, the round-2
        # asymmetry rule), so only the opposite-sign flip is freed. mutually_different
        # (each side names a DIFFERENT subject) always refuses.
        bare_flip_is_catch = (
            asymmetric
            and not mutually_different
            and c_vals[0] != k_vals[0]
            and _grant_noun_count(claim, noun) == 1
            and _grant_noun_count(clause, noun) == 1
        )
        if (asymmetric or mutually_different) and not bare_flip_is_catch:
            if multi is None:
                multi = ClauseVerdict(
                    "multi_value_unverifiable",
                    (
                        f"The summary and {where} qualify a {noun} whose subject matter "
                        f"cannot be matched deterministically, so the {stem} qualifiers "
                        "were not independently checked."
                    ),
                    qualified,
                    c_vals,
                    k_vals,
                )
            continue
        if c_vals[0] == k_vals[0]:
            if present is None:
                present = ClauseVerdict(
                    "present",
                    # _present_detail, not a literal "appears in": the canonical
                    # values are equal but the surfaces may differ ("non-exclusive"
                    # vs "nonexclusive"), and a filing-grade detail must never
                    # assert text the clause does not contain.
                    _present_detail(c_hits[0], k_hits[0], where),
                    qualified,
                    c_vals,
                    k_vals,
                    claim_span=c_hits[0].text,
                    clause_span=k_hits[0].text,
                    where=where,
                )
            continue
        contradiction = ClauseVerdict(
            "parametric_contradiction",
            f"The summary states {c_hits[0].text}; {where} states {k_hits[0].text}.",
            qualified,
            c_vals,
            k_vals,
            claim_span=c_hits[0].text,
            clause_span=k_hits[0].text,
            where=where,
        )
        break
    return contradiction, multi, present, not_found


def _normalize_subject(s: str) -> str:
    return s.strip().lower()


def _group_by_subject(hits: list[Anchor]) -> dict[str, list[Anchor]]:
    """Group subject-bearing anchors by their normalized subject, in first-appearance
    (document) order. Anchors with no subject are dropped (they take the value-only
    path)."""
    grouped: dict[str, list[Anchor]] = {}
    for a in hits:
        if a.subject is not None:
            grouped.setdefault(_normalize_subject(a.subject), []).append(a)
    return grouped


def _subject_binding_is_ambiguous(anchors: list[Anchor], anchor_type: str) -> bool:
    """Whether a single subject carries TWO values that do not agree.

    The coarse (regex-window) subject binder can attach the same subject label to
    two different figures in one passage -- a clause stating both a "15% margin" and a
    "35% royalty" can bind BOTH percents to subject "royalty", and a clause that names
    one obligation twice with different amounts binds both to the same subject. When a
    subject resolves to several non-agreeing values on one side, a deterministic check
    cannot say WHICH value the subject actually owns, so the subject is not a usable
    alignment key: it must route to could-not-check, never green on the first value
    (the silent ``dict.setdefault`` collision that leaked a false green) nor accuse off
    it. This carries the multi-value-cannot-align rule the value-only path already
    enforces (ADR-0012 invariant 2) into the subject-keyed comparison paths.

    Duration uses the unit-aware compare so equivalent terms ("12 months" / "1 year")
    are not a collision; every other type compares canonical values exactly.
    """
    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            if anchor_type == "duration":
                if not _durations_match(anchors[i], anchors[j]):
                    return True
            elif anchors[i].canonical_value != anchors[j].canonical_value:
                return True
    return False


def _ambiguous_subject_verdict(
    claim_anchor: Anchor,
    where: str,
    ambiguous_anchors: list[Anchor],
    anchor_type: str,
    *,
    side: str,
    subject: str | None = None,
) -> ClauseVerdict:
    """The multi-value-cannot-align refusal for an ambiguously-bound subject.

    A subject that resolves to several non-agreeing values on one side cannot be
    aligned one-to-one deterministically -- which is exactly the ``multi_value_unverifiable``
    state. The detail names the claim's own figure (so the refusal can never read as
    content-free) plus the colliding values. ``subject`` overrides the displayed
    subject label for the labeler path, whose subject comes from an external map
    rather than ``anchor.subject``.
    """
    vals = ", ".join(dict.fromkeys(a.text for a in ambiguous_anchors))
    subj = subject if subject is not None else claim_anchor.subject
    if side == "clause":
        detail = (
            f"The summary states {claim_anchor.text} for {subj}; {where} carries multiple "
            f"values ({vals}) for that subject, which a deterministic check cannot align "
            "one-to-one, so this sentence was not independently checked."
        )
    else:
        detail = (
            f"The summary states multiple values ({vals}) for {subj}, which a deterministic "
            "check cannot align one-to-one, so this sentence was not independently checked."
        )
    return ClauseVerdict(
        "multi_value_unverifiable",
        detail,
        anchor_type,
        (claim_anchor.canonical_value,),
        tuple(dict.fromkeys(a.canonical_value for a in ambiguous_anchors)),
    )


def _subject_aware_percent(
    claim_hits: list[Anchor], clause_hits: list[Anchor], where: str
) -> ClauseVerdict | None:
    """Compare percents by SUBJECT, not by bare value (D2/D3).

    Returns a ClauseVerdict only when the claim's percents carry subjects (the
    "France" of "10% France"); otherwise None, so the value-only path runs
    unchanged for subject-less percents (no regression).

    A claim percent is compared ONLY to a clause percent about the SAME (normalized)
    subject, so "10% France" never conflicts with "16% profitability" — different
    subjects are different facts, not a contradiction (D2). A same-subject value
    mismatch IS a contradiction ("20% France" vs source "10% France", D3). Fails
    toward could-not-check: a claim subject the clause is silent on is not_found,
    never a contradiction, so a mis-bound subject costs a catch, never a green
    (the council's hard line). It is a comparison key, not a topicality gate: it
    does not suppress a standing contradiction, it prevents an apples-to-oranges one.
    """
    claim_groups = _group_by_subject(claim_hits)
    if not claim_groups:
        return None  # no subjects on the claim side -> value-only path
    clause_groups = _group_by_subject(clause_hits)
    # Same-subject value mismatch is the only contradiction this path may raise —
    # unless the claim's value appears in the clause under a DIFFERENT subject, which
    # is an ambiguous overlap (e.g. "10% profitability" also in the clause while the
    # claimed "Amount A = 10%" is contradicted by "Amount A = 25%").  Ambiguous
    # overlaps route to could-not-check (specific, never a guessed accusation). A
    # subject that itself binds to multiple distinct values (the coarse binder mapped
    # two percents to one subject) is ambiguous and cannot be aligned at all.
    for subj, c_anchors in claim_groups.items():
        ca = c_anchors[0]
        if _subject_binding_is_ambiguous(c_anchors, "percent"):
            return _ambiguous_subject_verdict(ca, where, c_anchors, "percent", side="claim")
        cl_anchors = clause_groups.get(subj)
        if cl_anchors is None:
            continue
        if _subject_binding_is_ambiguous(cl_anchors, "percent"):
            return _ambiguous_subject_verdict(ca, where, cl_anchors, "percent", side="clause")
        cl = cl_anchors[0]
        if ca.canonical_value != cl.canonical_value:
            claim_val_in_other_clause = any(
                a.canonical_value == ca.canonical_value
                for a in clause_hits
                if a.subject is None or _normalize_subject(a.subject) != subj
            )
            if claim_val_in_other_clause:
                return ClauseVerdict(
                    "not_found",
                    f"The summary states {ca.text} for {ca.subject}; {where} states "
                    f"{cl.text} for the same subject and {ca.text} for another, "
                    "so the binding could not be confirmed.",
                    "percent",
                    (ca.canonical_value,),
                    (),
                )
            return ClauseVerdict(
                "parametric_contradiction",
                f"The summary states {ca.text} for {ca.subject}; {where} states {cl.text}.",
                "percent",
                (ca.canonical_value,),
                (cl.canonical_value,),
                claim_span=ca.text,
                clause_span=cl.text,
                where=where,
            )
    matched = [
        s
        for s in claim_groups
        if s in clause_groups
        and not _subject_binding_is_ambiguous(clause_groups[s], "percent")
        and clause_groups[s][0].canonical_value == claim_groups[s][0].canonical_value
    ]
    # Present requires EVERY claim percent to be confirmed: each must carry a subject
    # AND the clause must state that subject (equal value -- a mismatch already returned
    # a contradiction above). The prior code greened on ANY one matched subject, so a
    # claim like "10% France and 20% Germany" against a clause stating only "10% France"
    # read present and the unconfirmed 20% Germany rode the green (xhigh review finding 1,
    # 2026-06-16). A subject the clause is silent on, or a subject-LESS sibling percent
    # (excluded from claim_groups, so len(claim_hits) > len(claim_groups)), leaves part of
    # the claim unconfirmed -> could-not-check, never a green the unconfirmed part rides
    # on (the council's hard line).
    all_confirmed = len(claim_hits) == len(claim_groups) == len(matched)
    if all_confirmed:
        ca, cl = claim_groups[matched[0]][0], clause_groups[matched[0]][0]
        return ClauseVerdict(
            "present",
            _present_detail(ca, cl, where),
            "percent",
            tuple(claim_groups[s][0].canonical_value for s in matched),
            tuple(clause_groups[s][0].canonical_value for s in matched),
            claim_span=ca.text,
            clause_span=cl.text,
            where=where,
        )
    # Not fully confirmed: the clause is silent on at least one claim subject, or a
    # subject-less sibling percent remains unchecked. Not a contradiction (different /
    # silent subjects are not a value conflict) and not a green -> honest could-not-check.
    first = next(iter(claim_groups.values()))[0]
    return ClauseVerdict(
        "not_found",
        f"The summary states {first.text} for {first.subject}, which {where} does not fully state.",
        "percent",
        tuple(c[0].canonical_value for c in claim_groups.values()),
        (),
    )


def _subject_aware_amount(
    claim_hits: list[Anchor],
    clause_hits: list[Anchor],
    where: str,
    anchor_type: str,
    claim_subjects: dict[tuple[int, int], str],
    clause_subjects: dict[tuple[int, int], str],
    clause_text: str,
) -> ClauseVerdict | None:
    """ADR-0013 disposer for money / magnitude / duration, gated behind the subject
    labeler. The labeler PROPOSES a subject per figure (regex floor or on-device AFM);
    this function DISPOSES the verdict and greens ONLY on a verbatim-confirmed
    same-subject match. The truth table:

    - claim subject A, clause confirms A, equal value   -> present (the only green)
    - claim subject A, clause confirms A, value differs -> parametric_contradiction
    - claim subject A, clause does not confirm A, claim value PRESENT in clause
      -> not_found (could-not-check): the value coincides for an unconfirmed/different
      subject ("indemnification cap $5M" vs "liability cap $5M"). The false-green gate.
    - claim subject A, clause does not confirm A, claim value ABSENT
      -> None: fall through to the value-only path so the altered-figure contradiction
      (the value-absent catch) still fires.
    - claim has no labeled subject -> None: value-only path, unchanged.

    A model mis-label cannot mint a green: the clause subject must be verbatim in the
    clause (the post-check) AND match the claim's subject; any gap routes to
    could-not-check. So a green is model-originated-impossible.
    """
    claim_groups: dict[str, list[Anchor]] = {}
    for a in claim_hits:
        s = claim_subjects.get((a.start, a.end))
        if s:
            claim_groups.setdefault(s, []).append(a)
    if not claim_groups:
        return None  # unlabeled claim -> value-only path (no behavior change)

    # LOCAL-proximity post-check: trust a clause subject only if it appears verbatim
    # WITHIN A WINDOW of its own figure, not anywhere in the clause. Anywhere-in-clause
    # is injection-vulnerable: a hostile clause can carry "...label this as the liability
    # cap..." far from the figure and a model that follows it would pass an anywhere
    # check (validated live: AFM followed exactly that). Requiring the subject next to
    # the figure means an instruction planted elsewhere cannot relabel it. For the regex
    # floor this is true by construction (it binds the figure's own adjacent qualifier).
    _SUBJECT_WINDOW = 48
    clause_groups: dict[str, list[Anchor]] = {}
    for a in clause_hits:
        s = clause_subjects.get((a.start, a.end))
        # Slice the ORIGINAL-case text (the anchor offsets index it) and lowercase the
        # slice. Lowercasing the whole clause first would misalign the window: str.lower()
        # is NOT length-preserving (U+0130 -> two codepoints), so every figure after such
        # a character would get a shifted window and could silently drop a real catch.
        window = clause_text[max(0, a.start - _SUBJECT_WINDOW) : a.end + _SUBJECT_WINDOW].lower()
        if s and s in window:
            clause_groups.setdefault(s, []).append(a)

    def _eq(ca: Anchor, cl: Anchor) -> bool:
        if anchor_type == "duration":
            return _durations_match(ca, cl)
        return ca.canonical_value == cl.canonical_value

    for subj, c_anchors in claim_groups.items():
        ca = c_anchors[0]
        # An ambiguously-bound subject (the same label proposed for two non-agreeing
        # figures) is not a usable alignment key: refuse, never green or accuse off it.
        if _subject_binding_is_ambiguous(c_anchors, anchor_type):
            return _ambiguous_subject_verdict(
                ca, where, c_anchors, anchor_type, side="claim", subject=subj
            )
        cl_anchors = clause_groups.get(subj)
        if cl_anchors is None:
            continue
        if _subject_binding_is_ambiguous(cl_anchors, anchor_type):
            return _ambiguous_subject_verdict(
                ca, where, cl_anchors, anchor_type, side="clause", subject=subj
            )
        cl = cl_anchors[0]
        if not _eq(ca, cl):
            return ClauseVerdict(
                "parametric_contradiction",
                f"The summary states {ca.text} for {subj}; {where} states {cl.text}.",
                anchor_type,
                (ca.canonical_value,),
                (cl.canonical_value,),
                claim_span=ca.text,
                clause_span=cl.text,
                where=where,
            )
    matched = [
        s
        for s in claim_groups
        if s in clause_groups
        and not _subject_binding_is_ambiguous(clause_groups[s], anchor_type)
        and _eq(claim_groups[s][0], clause_groups[s][0])
    ]
    if matched:
        ca, cl = claim_groups[matched[0]][0], clause_groups[matched[0]][0]
        return ClauseVerdict(
            "present",
            _present_detail(ca, cl, where),
            anchor_type,
            tuple(claim_groups[s][0].canonical_value for s in matched),
            tuple(clause_groups[s][0].canonical_value for s in matched),
            claim_span=ca.text,
            clause_span=cl.text,
        )
    # No verbatim-confirmed shared subject. Never green on a value coincidence.
    claim_vals = {c[0].canonical_value for c in claim_groups.values()}
    if claim_vals & {a.canonical_value for a in clause_hits}:
        first_subj, first_anchors = next(iter(claim_groups.items()))
        first = first_anchors[0]
        return ClauseVerdict(
            "not_found",
            f"The summary states {first.text} for {first_subj}; {where} carries "
            "that value but its subject could not be confirmed, so it was not independently checked.",
            anchor_type,
            tuple(claim_vals),
            (),
        )
    return None  # claim value absent -> value-only path (the value-absent catch fires)


# Obligation CONTAINER/UNIT nouns, quantifiers, and party roles that do NOT by
# themselves identify WHICH obligation a figure is about. "liability cap" and
# "indemnification cap" share "cap"; "notice period" and "warranty period" share
# "period"; "minimum order" and "maximum order" share "order". The DISTINCTIVE word
# (liability / indemnification / notice / warranty / minimum / maximum) is what tells
# two obligations apart, so the generic head is stripped before a subject is matched.
# Closed vocabulary, T0: a word outside the list is treated as distinctive, so the
# bias is toward refusing (a generic word we forgot to list costs a catch, never a
# green). Party roles are included because "of either party" names whose obligation,
# not which one.
_GENERIC_SUBJECT_WORDS = frozenset(
    {
        # container / unit nouns
        "cap", "caps", "period", "periods", "order", "orders", "term", "terms",
        "deposit", "deposits", "fee", "fees", "bonus", "penalty", "penalties",
        "retainer", "limit", "limits", "amount", "amounts", "sum", "payment",
        "payments", "price", "fund", "balance", "threshold", "thresholds",
        "value", "level", "obligation", "obligations", "rate", "interest",
        # quantifiers
        "aggregate", "total", "overall",
        # party roles
        "party", "parties", "either", "each", "both", "seller", "buyer",
        "licensor", "licensee", "grantor", "grantee", "lessor", "lessee",
        "vendor", "supplier", "customer", "client", "company",
    }
)  # fmt: skip


def _distinctive_subject_words(subject: str | None) -> frozenset[str]:
    """The obligation-identifying words of a figure's subject, generic heads stripped.

    "liability cap" -> {"liability"}, "notice period" -> {"notice"}, "minimum order"
    -> {"minimum"}. Empty when the subject names no distinctive obligation (a bare
    "cap" or "either party"), which keeps the binding from firing on a generic head.
    """
    if not subject:
        return frozenset()
    return frozenset(
        w for w in re.findall(r"[a-z]{3,}", subject.lower()) if w not in _GENERIC_SUBJECT_WORDS
    )


def _subject_words_precede_figure(words: frozenset[str], clause_text: str, fig_start: int) -> bool:
    """Whether every distinctive word appears in the clause SEGMENT before ``fig_start``.

    Backward only, bounded at the nearest preceding sentence boundary (. ; :), so a
    later-sentence injection ("...label the amount above as the liability cap...")
    can never supply the word: the obligation must sit in front of its own figure.
    """
    seg_start = max((clause_text.rfind(ch, 0, fig_start) for ch in ".;:"), default=-1) + 1
    segment = clause_text[seg_start:fig_start].lower()
    return all(re.search(rf"\b{re.escape(w)}\b", segment) for w in words)


def _subject_aware_figure_builtin(
    claim_hits: list[Anchor],
    clause_hits: list[Anchor],
    where: str,
    anchor_type: str,
    clause_text: str,
) -> ClauseVerdict | None:
    """Subject-aware money/magnitude comparison using anchor.subject (no labeler required).

    The anchor subject is set during extraction from adjacent finance-domain nouns
    ("revenue of EUR 7 billion" -> subject "revenue"; "EUR 20 billion in Revenues"
    -> subject "revenue").  When claim anchors carry subjects this function:

    - Same subject, same value   -> present  (subject-confirmed; bypasses ADR-0013
                                               scope-out because the obligation is bound)
    - Same subject, value differs -> parametric_contradiction
    - No same-subject clause anchor -> None (value-only path runs unchanged)

    Unlike the model-backed _subject_aware_amount, this path affirms subject-confirmed
    matches because the obligation identity comes from deterministic regex, not a
    model that could mis-label.  A green is impossible without a finance noun that
    appears verbatim in both claim and clause with the same normalised form.
    """
    claim_groups = _group_by_subject(claim_hits)
    if not claim_groups:
        return None  # unlabeled claim -> value-only path unchanged

    clause_groups = _group_by_subject(clause_hits)

    def _eq(ca: Anchor, cl: Anchor) -> bool:
        if anchor_type == "duration":
            return _durations_match(ca, cl)
        return ca.canonical_value == cl.canonical_value

    for subj, c_anchors in claim_groups.items():
        ca = c_anchors[0]
        # An ambiguously-bound subject (the coarse binder gave one obligation two
        # non-agreeing values) is not a usable alignment key: refuse, never green on
        # the first value or accuse off it.
        if _subject_binding_is_ambiguous(c_anchors, anchor_type):
            return _ambiguous_subject_verdict(ca, where, c_anchors, anchor_type, side="claim")
        cl_anchors = clause_groups.get(subj)
        if cl_anchors is None:
            continue
        if _subject_binding_is_ambiguous(cl_anchors, anchor_type):
            return _ambiguous_subject_verdict(ca, where, cl_anchors, anchor_type, side="clause")
        cl = cl_anchors[0]
        if not _eq(ca, cl):
            return ClauseVerdict(
                "parametric_contradiction",
                f"The summary states {ca.text} for {subj}; {where} states {cl.text}.",
                anchor_type,
                (ca.canonical_value,),
                (cl.canonical_value,),
                claim_span=ca.text,
                clause_span=cl.text,
                where=where,
            )

    matched = [
        s
        for s in claim_groups
        if s in clause_groups
        and not _subject_binding_is_ambiguous(clause_groups[s], anchor_type)
        and _eq(claim_groups[s][0], clause_groups[s][0])
    ]
    if matched:
        ca, cl = claim_groups[matched[0]][0], clause_groups[matched[0]][0]
        return ClauseVerdict(
            "present",
            _present_detail(ca, cl, where),
            anchor_type,
            tuple(claim_groups[s][0].canonical_value for s in matched),
            tuple(clause_groups[s][0].canonical_value for s in matched),
            claim_span=ca.text,
            clause_span=cl.text,
        )

    # Distinctive single-figure binding: the clause's own extracted subject can name
    # the wrong thing ("aggregate liability of either party" extracts the party, not
    # "liability"), so the exact-subject match above misses a real verification. When
    # the claim names an obligation by a DISTINCTIVE noun (not a generic head like
    # "cap") that appears immediately before the clause's SINGLE figure of this type,
    # and the values are equal, the obligation IS bound deterministically. Gated hard:
    # one figure on each side (no ambiguity which figure the noun binds — the
    # cap-multifigure guard) and a backward-segment-only search (a post-figure
    # injection cannot supply the word), so a green here is value-coincidence-proof.
    if len(claim_hits) == 1 and len(clause_hits) == 1:
        ca, cl = claim_hits[0], clause_hits[0]
        distinct = _distinctive_subject_words(ca.subject)
        if (
            distinct
            and _eq(ca, cl)
            and _subject_words_precede_figure(distinct, clause_text, cl.start)
        ):
            return ClauseVerdict(
                "present",
                _present_detail(ca, cl, where),
                anchor_type,
                (ca.canonical_value,),
                (cl.canonical_value,),
                claim_span=ca.text,
                clause_span=cl.text,
            )

    # No same-subject match. If the claim value appears in the clause under a
    # different subject, route to could-not-check to avoid a spurious value-only green.
    claim_vals = {c[0].canonical_value for c in claim_groups.values()}
    if claim_vals & {a.canonical_value for a in clause_hits}:
        first_subj, first_anchors = next(iter(claim_groups.items()))
        first_anchor = first_anchors[0]
        return ClauseVerdict(
            "not_found",
            f"The summary states {first_anchor.text} for {first_subj}; {where} carries "
            "that value but its subject could not be confirmed, so it was not independently checked.",
            anchor_type,
            tuple(claim_vals),
            (),
        )

    return None  # claim value absent -> value-only path (contradiction catch fires)


def _generic_polarity_flip(claim: str, clause: str, where: str) -> ClauseVerdict | None:
    """Catch a polarity flip on a noun OUTSIDE the curated grant-noun lexicon.

    The closed ``_GRANT_NOUN`` lexicon gives the standard polarity pass its precision
    on single-side detection ("exclusive jurisdiction" is venue and must not anchor).
    But a flip is material whatever the noun, so this fallback fires when the claim and
    the clause BOTH attribute a polarity qualifier to the SAME head noun with OPPOSITE
    signs of the same stem (e.g. "exclusive distributorship" vs "non-exclusive
    distributorship"). The matched-noun requirement is the precision guard the lexicon
    supplies elsewhere, and the existing subject-matter gate (asymmetry / mutual
    difference / single-grant disambiguation, reused verbatim from ``_polarity_pass``)
    still refuses when the two sides describe different instances of that noun, so a
    clean draft is never accused.

    Purely additive: it returns a contradiction or None, so it can only turn a missed
    flip into a contradiction -- never suppress a present nor mint a new refusal.
    """
    claim_pairs = polarity_flip_pairs(claim)
    if not claim_pairs:
        return None
    clause_pairs = polarity_flip_pairs(clause)
    if not clause_pairs:
        return None
    for c_stem, c_noun, c_sign, c_surf in claim_pairs:
        for k_stem, k_noun, k_sign, k_surf in clause_pairs:
            if c_stem != k_stem or c_noun != k_noun or c_sign == k_sign:
                continue
            # Subject-matter gate, identical to the lexicon polarity pass: align the
            # words around the noun on each side. A pure asymmetry is a catch only when
            # there is a single grant of the noun in play on each side; mutual
            # difference (each side names a subject the other lacks) always refuses.
            claim_objects = _noun_objects(claim, c_noun)
            clause_objects = _noun_objects(clause, k_noun)
            asymmetric = bool(claim_objects) != bool(clause_objects)
            mutually_different = bool(claim_objects - clause_objects) and bool(
                clause_objects - claim_objects
            )
            bare_flip_is_catch = (
                asymmetric
                and not mutually_different
                and _grant_noun_count(claim, c_noun) == 1
                and _grant_noun_count(clause, k_noun) == 1
            )
            if (asymmetric or mutually_different) and not bare_flip_is_catch:
                continue
            return ClauseVerdict(
                "parametric_contradiction",
                f"The summary states {c_surf} {c_noun}; {where} states {k_surf} {k_noun}.",
                f"polarity:{c_stem}:{c_noun}",
                (f"{c_stem}:{c_noun}{c_sign}",),
                (f"{k_stem}:{k_noun}{k_sign}",),
                claim_span=c_surf,
                clause_span=k_surf,
                where=where,
            )
    return None


def verify_claim_against_clause(claim: str, clause: str) -> ClauseVerdict:
    """Decide whether ``claim`` is supported, contradicted, or unfound vs ``clause``.

    The detail is filing-grade: it names the contract section and quotes the
    actual values ("The summary states $1,000,000; Section 8 states $500,000"),
    so the certification record stands on its own.
    """
    claim_anchors = extract_anchors(claim)
    clause_anchors = extract_anchors(clause)
    section = next((a.text for a in clause_anchors if a.type == "section"), None)
    # Singular on purpose: the fallback feeds "{where} states {value}" below.
    where = section or "the loaded source"

    # ADR-0013: resolve the subject labeler once. None when CARREL_SUBJECT_LABELER is
    # off -> the subject-aware amount path is skipped entirely and behavior is byte-for
    # -byte unchanged. When on, label money/magnitude/duration figures with the
    # obligation they are about so the disposer can refuse a cross-subject value
    # coincidence ("indemnification cap $5M" vs "liability cap $5M").
    _labeler = get_subject_labeler()
    claim_subjects: dict[tuple[int, int], str] = {}
    clause_subjects: dict[tuple[int, int], str] = {}
    if _labeler is not None:
        _amount_types = {"money", "magnitude", "duration"}
        for _span, _lab in _labeler.label_subjects(
            claim, [a for a in claim_anchors if a.type in _amount_types]
        ).items():
            claim_subjects[_span] = _normalize_subject(_lab.subject)
        for _span, _lab in _labeler.label_subjects(
            clause, [a for a in clause_anchors if a.type in _amount_types]
        ).items():
            clause_subjects[_span] = _normalize_subject(_lab.subject)

    # A pasted-verbatim passage with one or more figures changed: diff EVERY figure
    # at once and name them all. Runs before the per-anchor loop (which would report
    # at most one) and refuses on anything that is not a near-verbatim copy, so it
    # only ever adds catches, never accusations the per-anchor path would not make.
    near_copy = _altered_figures_on_near_copy(claim, clause, where)
    if near_copy is not None:
        return near_copy

    # A same-noun opposite-sign polarity flip on a noun the curated grant-noun lexicon
    # does not cover (e.g. "exclusive distributorship" vs "non-exclusive
    # distributorship"). A contradiction wins outright, so it runs before the per-type
    # loop; it only fires on non-lexicon nouns, so it never collides with the lexicon
    # polarity pass inside the loop.
    generic_flip = _generic_polarity_flip(claim, clause, where)
    if generic_flip is not None:
        return generic_flip

    # Evaluate EVERY parametric type the claim carries, not just the first. A
    # contradiction in ANY type wins outright: a sentence with a matching amount but a
    # falsified date must read contradiction, not "present" (returning on the first
    # type that matched would mask the wrong date). Among non-contradictions, a
    # present finding beats a not_found.
    present_verdict: ClauseVerdict | None = None
    not_found_verdict: ClauseVerdict | None = None
    multi_value_verdict: ClauseVerdict | None = None
    # A figure (money/magnitude/duration) not_found is a SCOPE-OUT (ADR-0013): a value
    # match will not be affirmed, and it must NOT block a sibling non-figure present
    # (the deliberate "50% royalty in a 12-month window" case). A NON-figure not_found
    # (percent / date / governing_law / polarity) means the claim asserts a value the
    # clause does not confirm -- an unconfirmed assertion that must OUTRANK a sibling
    # present, or the unconfirmed value rides the green (xhigh review, 2026-06-16:
    # "governed by NY law and the royalty is 20% Germany" vs a clause stating NY law +
    # "10% France" read present, laundering the unconfirmed 20% Germany).
    unconfirmed_verdict: ClauseVerdict | None = None
    for anchor_type in _PARAMETRIC_TYPES:
        claim_hits = [
            a for a in claim_anchors if a.type == anchor_type and a.canonical_value is not None
        ]
        if not claim_hits:
            continue
        clause_hits = [
            a for a in clause_anchors if a.type == anchor_type and a.canonical_value is not None
        ]
        if anchor_type == "polarity":
            contradiction, p_multi, p_present, p_not_found = _polarity_pass(
                claim_hits, clause_hits, where, claim, clause
            )
            if contradiction is not None:
                return contradiction
            multi_value_verdict = multi_value_verdict or p_multi
            present_verdict = present_verdict or p_present
            # Polarity is non-figure: an unconfirmed key must outrank a sibling present
            # (a partial polarity confirmation is could-not-check, not green).
            unconfirmed_verdict = unconfirmed_verdict or p_not_found
            continue
        # Equal canonicals collapse to one fact: "0.5% (50 bps)" is a single
        # rate written twice, not two values needing alignment. Only genuinely
        # different values trigger the multi-value refusal below.
        claim_values = tuple(dict.fromkeys(a.canonical_value for a in claim_hits))
        clause_values = tuple(dict.fromkeys(a.canonical_value for a in clause_hits))
        # D2/D3: percents that carry a subject are compared by subject, not by bare
        # value, BEFORE the value-only gates below (which would otherwise multi-value
        # or cross-subject-contradict). Subject-less percents return None here and
        # fall through to the unchanged value-only path.
        if anchor_type == "percent":
            sa = _subject_aware_percent(claim_hits, clause_hits, where)
            if sa is not None:
                if sa.disposition == "parametric_contradiction":
                    return sa
                if sa.disposition == "present":
                    present_verdict = present_verdict or sa
                else:
                    # Percent is non-figure: a percent the clause does not fully confirm
                    # is an unconfirmed assertion that must outrank a sibling present.
                    unconfirmed_verdict = unconfirmed_verdict or sa
                continue
        # Built-in (no-labeler) subject-aware check for money/magnitude/duration:
        # uses anchor.subject set during extraction from the obligation noun phrase
        # immediately before the figure.  Fires before the multi-value gate so a
        # subject-confirmed same-obligation match resolves to the correct definite
        # verdict without reaching could-not-check.  Duration is included here so
        # "The notice period is 3 years" can resolve to present/contradicted when
        # the same obligation name and the same (or different) value appear in the
        # clause — the ADR-0013 scope-out only applies when there is NO subject
        # binding; a confirmed binding lifts it (same as for money/magnitude).
        if anchor_type in ("money", "magnitude", "duration"):
            sa_builtin = _subject_aware_figure_builtin(
                claim_hits, clause_hits, where, anchor_type, clause
            )
            if sa_builtin is not None:
                if sa_builtin.disposition == "parametric_contradiction":
                    return sa_builtin
                if sa_builtin.disposition == "present":
                    # Subject-confirmed match: the obligation is bound deterministically,
                    # so the ADR-0013 scope-out does not apply; affirm the value.
                    present_verdict = present_verdict or sa_builtin
                elif sa_builtin.disposition == "multi_value_unverifiable":
                    # Ambiguous binding (one obligation, several non-agreeing values):
                    # the same cannot-align refusal the value-only multi-value gate
                    # raises, so it takes the multi_value tier (outranks a sibling
                    # present), matching that gate's precedence for money/duration.
                    multi_value_verdict = multi_value_verdict or sa_builtin
                else:
                    not_found_verdict = not_found_verdict or sa_builtin
                continue
        if _labeler is not None and anchor_type in ("money", "magnitude", "duration"):
            sa = _subject_aware_amount(
                claim_hits,
                clause_hits,
                where,
                anchor_type,
                claim_subjects,
                clause_subjects,
                clause,
            )
            if sa is not None:
                if sa.disposition == "parametric_contradiction":
                    return sa
                if sa.disposition == "multi_value_unverifiable":
                    # Ambiguous binding (one labeled obligation, several non-agreeing
                    # values): a genuine cannot-align refusal, kept at the multi_value
                    # tier rather than collapsed into the generic figure scope-out.
                    multi_value_verdict = multi_value_verdict or sa
                    continue
                # scope-out: a confirmed same-subject MATCH still does not affirm a
                # figure; only a contradiction is a definite figure verdict, everything
                # else is could-not-check. (Kept at the not_found tier on purpose: a
                # sibling non-figure present, e.g. a 50% royalty rate in a sentence that
                # also names a 12-month window, must still read present; routing the
                # incidental figure to the multi_value tier would over-refuse the real
                # verification and also perturbs the cross-clause carrier veto.)
                if not_found_verdict is None:
                    not_found_verdict = ClauseVerdict(
                        "not_found",
                        f"The summary states {claim_hits[0].text}; a deterministic check "
                        "does not affirm a figure without confirming its obligation, so it "
                        "was not independently verified.",
                        anchor_type,
                        claim_values,
                        clause_values,
                    )
                continue
        if not clause_hits:
            _absent = ClauseVerdict(
                "not_found",
                f"The summary states {claim_hits[0].text}, which the deterministic check "
                "could not locate in your loaded sources.",
                anchor_type,
                claim_values,
                (),
            )
            # A figure absent from the source is a scope-out (yields to a sibling
            # present); a non-figure value the source is silent on is an unconfirmed
            # assertion that must outrank a sibling present.
            if anchor_type in ("money", "magnitude", "duration"):
                not_found_verdict = not_found_verdict or _absent
            elif unconfirmed_verdict is None:
                unconfirmed_verdict = _absent
            continue
        if len(claim_values) > 1 or len(clause_values) > 1:
            # Multiple values of this type on a side: a deterministic clause-level check
            # cannot say WHICH claim value maps to WHICH clause value. The old
            # "any matches any" test could MASK a real contradiction (a claim's $1M cap
            # spuriously matching a clause's unrelated $1M line) or, on a clean miss, name
            # a guessed first-value contradiction (a false accusation). Neither is honest,
            # so route to the could-not-check tray (ADR-0012 invariant 2: below-confidence
            # is never a guessed verdict). Role-aligned multi-value checking is T1 work.
            if multi_value_verdict is None:
                _n_clause = len(clause_values)
                _unit_word = f"{anchor_type} value{'s' if _n_clause != 1 else ''}"
                multi_value_verdict = ClauseVerdict(
                    "multi_value_unverifiable",
                    (
                        f"The summary states {claim_hits[0].text}; {where} carries "
                        f"{_n_clause} {_unit_word} that cannot be aligned one-to-one "
                        "deterministically, so this sentence was not independently checked."
                    ),
                    anchor_type,
                    claim_values,
                    clause_values,
                )
            continue
        if anchor_type == "governing_law" and related_jurisdictions(
            claim_values[0], clause_values[0]
        ):
            # A container/member pair (UAE vs DIFC, United States vs Delaware):
            # the values differ but one jurisdiction sits inside the other, so a
            # flat comparison can neither confirm nor accuse. Routed to the
            # honest could-not-check as an alignment refusal (ADR-0012
            # invariant 2); sibling mismatches still contradict below.
            if multi_value_verdict is None:
                multi_value_verdict = ClauseVerdict(
                    "multi_value_unverifiable",
                    (
                        f"The summary states {claim_hits[0].text} and {where} states "
                        f"{clause_hits[0].text}: one jurisdiction contains the other, "
                        "which a flat deterministic comparison cannot adjudicate, so "
                        "this sentence was not independently checked."
                    ),
                    anchor_type,
                    claim_values,
                    clause_values,
                )
            continue
        # Durations compare unit-aware (this branch's fix); everything else by
        # the default value intersection.
        if anchor_type == "duration":
            matched = _durations_match(claim_hits[0], clause_hits[0])
        else:
            matched = _values_match(list(claim_values), list(clause_values))
        if matched:
            if anchor_type in ("money", "magnitude", "duration"):
                # ADR-0013 scope-out: a figure is never AFFIRMED. A deterministic check
                # cannot confirm a value belongs to the claimed obligation without subject
                # understanding it does not reliably have (the AFM 3B labeler was validated
                # and failed to earn it), so a value MATCH is could-not-check, never a green.
                # Figure claims only ever CATCH (the contradiction below / near-copy /
                # subject mismatch) or honestly refuse -> zero figure false greens by
                # construction. (not_found tier on purpose: an incidental figure must not
                # suppress a sibling non-figure present; see the subject-aware block note.)
                if not_found_verdict is None:
                    not_found_verdict = ClauseVerdict(
                        "not_found",
                        f"{claim_hits[0].text} appears in {where}, but a deterministic check "
                        "cannot confirm it states this obligation, so it was not "
                        "independently verified.",
                        anchor_type,
                        claim_values,
                        clause_values,
                    )
                continue
            if present_verdict is None:
                present_verdict = ClauseVerdict(
                    "present",
                    _present_detail(claim_hits[0], clause_hits[0], where),
                    anchor_type,
                    claim_values,
                    clause_values,
                    claim_span=claim_hits[0].text,
                    clause_span=clause_hits[0].text,
                    where=where,
                )
            continue
        return ClauseVerdict(
            "parametric_contradiction",
            f"The summary states {claim_hits[0].text}; {where} states {clause_hits[0].text}.",
            anchor_type,
            claim_values,
            clause_values,
            claim_span=claim_hits[0].text,
            clause_span=clause_hits[0].text,
            where=where,
        )
    # Precedence: a single-value contradiction already returned outright above. Among the
    # rest, an honest could-not-check outranks a present, because a sentence is not
    # "present" if any checkable part of it went unaligned (multi_value) or unconfirmed (a
    # non-figure value the clause is silent on). A FIGURE not_found is the exception: it is
    # a scope-out that yields to a sibling present, so it stays below present.
    if multi_value_verdict is not None:
        return multi_value_verdict
    if unconfirmed_verdict is not None:
        return unconfirmed_verdict
    if present_verdict is not None:
        return present_verdict
    if not_found_verdict is not None:
        return not_found_verdict

    for anchor in claim_anchors:
        if anchor.type == "quote" and verbatim_run_present(anchor.text, clause):
            return ClauseVerdict(
                "present",
                f'The quoted language "{anchor.text}" appears verbatim in {where}; '
                "review the full passage for context.",
                "quote",
            )

    return ClauseVerdict(
        "not_found", "The summary's language does not appear in your loaded sources."
    )


def _carried_clause_values(
    clause_text: str | None, contra: ClauseVerdict
) -> tuple[tuple, str | None] | None:
    """``(clause_values, section)`` when ``clause_text`` literally carries every
    claim value behind the contradiction ``contra``, else None.

    The rule-1 veto used to consult only candidates whose FINAL disposition was
    ``present``. That missed two carrier shapes, and the miss accused
    verbatim-correct drafts (the live Kellogg false contradiction, 2026-06-11):

      - a clause whose final verdict is ``multi_value_unverifiable`` because it
        bundles several same-type values, one of which IS the claim's value;
      - a clause whose final verdict belongs to a DIFFERENT anchor type (the
        per-clause precedence keeps one disposition per clause), while its text
        still carries the claim's value for the accused type.

    So the carrier test re-reads the clause TEXT, not the verdict label. Match
    semantics mirror ``verify_claim_against_clause``: durations compare
    unit-aware via ``_durations_match`` (re-deriving the claim anchor from
    ``contra.claim_span``); everything else compares canonical values exactly.
    Polarity is excluded: its values are noun-keyed grants adjudicated per stem,
    so the present-only veto remains its floor. Returns the clause's full value
    tuple for the type (honest: the carrier may hold more values than the
    claim's) plus its section anchor for the conflict wording.
    """
    if not clause_text or not contra.claim_values:
        return None
    # Polarity verdicts carry noun-keyed types ("polarity:exclusive:license"),
    # so the exclusion matches on the prefix, not equality.
    if contra.anchor_type is None or contra.anchor_type.startswith("polarity"):
        return None
    clause_anchors = extract_anchors(clause_text)
    clause_hits = [
        a for a in clause_anchors if a.type == contra.anchor_type and a.canonical_value is not None
    ]
    if not clause_hits:
        return None
    clause_values = tuple(dict.fromkeys(a.canonical_value for a in clause_hits))
    section = next((a.text for a in clause_anchors if a.type == "section"), None)
    if contra.anchor_type == "duration":
        claim_hits = [
            a
            for a in extract_anchors(contra.claim_span or "")
            if a.type == "duration" and a.canonical_value is not None
        ]
        if not claim_hits:
            return None
        carried = all(
            any(_durations_match(claim_a, clause_a) for clause_a in clause_hits)
            for claim_a in claim_hits
        )
        return (clause_values, section) if carried else None
    carried = set(contra.claim_values) <= set(clause_values)
    return (clause_values, section) if carried else None


def adjudicate_clause_candidates(
    candidates: list[ClauseCandidate],
) -> tuple[ClauseVerdict, str | None, str | None]:
    """Adjudicate one claim across ALL retrieved clauses (topicality decision,
    docs/notes/2026-06-10-cachet-contradiction-topicality.md).

    Returns ``(verdict, section, clause_text)`` for the claim card. The rules,
    in precedence order:

    1. A contradiction stands only when NO retrieved clause carries the claim's
       value for that anchor type. "Carries" is decided from the clause TEXT
       (``_carried_clause_values``), not the disposition label: a same-type
       present anywhere, OR a multi-value clause that bundles the claim's value
       among others, OR a clause adjudicated under a different type whose text
       still holds the value — each means the value is verbatim in the
       contract, so accusing from a different clause would be a guess: the
       engine REFUSES with both clauses named (``conflicting_clauses``, mapped
       to the could-not-check card). Certainty is manufactured in neither
       direction (ADR-0012 invariant 2); present-wins was rejected because a
       value coincidence would paint a green over an amended-contract conflict,
       the worst failure class.
    2. An uncontested contradiction wins, first by retrieval rank. Topicality
       never gates WHETHER an accusation stands, and never picks ACROSS anchor
       types (a falsified value LOWERS overlap with its true clause, so a
       relevance gate would suppress exactly the true catches); it only swaps
       the evidence WITHIN the standing contradiction's own type, on-topic
       accuser first. When same-type multi-value clauses were also retrieved,
       the detail says so: the accusing clause may not be the claim's true
       counterpart, and the reader should review the unaligned passages too.
    3. Otherwise the first ON-topic present wins (C3 unchanged: an off-topic
       value coincidence never earns a green).
    4. Otherwise the first multi-value refusal, then not_found.
    """
    presents_by_type: dict[str | None, ClauseCandidate] = {}
    on_topic_presents: list[ClauseCandidate] = []
    contradictions: list[ClauseCandidate] = []
    multi_value: ClauseCandidate | None = None
    for cand in candidates:
        disposition = cand.verdict.disposition
        if disposition == "present":
            presents_by_type.setdefault(cand.verdict.anchor_type, cand)
            if cand.on_topic or cand.verdict.anchor_type == "quote":
                on_topic_presents.append(cand)
        elif disposition == "parametric_contradiction":
            contradictions.append(cand)
        elif disposition == "multi_value_unverifiable" and multi_value is None:
            multi_value = cand

    # (accusing contradiction, carrier's where-phrase, carrier section,
    #  carrier clause text, carrier's same-type values)
    first_conflict: tuple[ClauseCandidate, str, str | None, str | None, tuple] | None = None
    for contra in contradictions:
        present = presents_by_type.get(contra.verdict.anchor_type)
        if present is not None:
            pair = (
                contra,
                present.verdict.where or "one retrieved clause",
                present.section,
                present.clause_text,
                tuple(present.verdict.clause_values),
            )
        else:
            pair = None
            for cand in candidates:
                if cand is contra:
                    continue
                carried = _carried_clause_values(cand.clause_text, contra.verdict)
                if carried is not None:
                    carried_values, carrier_where = carried
                    pair = (
                        contra,
                        carrier_where or "one retrieved clause",
                        cand.section,
                        cand.clause_text,
                        carried_values,
                    )
                    break
            if pair is None:
                # Uncontested for its type: the catch stands, first by rank.
                # Evidence swap WITHIN the type only: same-type contradictions
                # share one claim-value set, so they share the veto outcome,
                # and an on-topic sibling is the better-named accuser. Across
                # types rank order is untouched (topicality must never pick
                # which catch stands).
                if not contra.on_topic:
                    contra = next(
                        (
                            c
                            for c in contradictions
                            if c.verdict.anchor_type == contra.verdict.anchor_type and c.on_topic
                        ),
                        contra,
                    )
                # If same-type multi-value clauses were retrieved, say so: the
                # engine could not align their values, so the accusing clause
                # may not be the claim's true counterpart (the live $360M case
                # was accused with an unrelated clause's $7 billion while the
                # true clause sat unaligned in a multi-value passage).
                verdict = contra.verdict
                unaligned = any(
                    c is not contra
                    and c.verdict.disposition == "multi_value_unverifiable"
                    and c.verdict.anchor_type == verdict.anchor_type
                    for c in candidates
                )
                if unaligned:
                    type_noun = (verdict.anchor_type or "checked").replace("_", "-")
                    verdict = replace(
                        verdict,
                        detail=(
                            verdict.detail + f" Other retrieved passages carry further {type_noun} "
                            "values the deterministic check could not align; review them "
                            "before relying on the comparison."
                        ),
                    )
                return verdict, contra.section, contra.clause_text
        if first_conflict is None:
            first_conflict = pair
    if first_conflict is not None:
        contra, where_p, section_p, clause_text_p, values_p = first_conflict
        where_c = contra.verdict.where or "another retrieved clause"
        if where_p == where_c:
            where_p, where_c = "one retrieved clause", "another retrieved clause"
        claim_span = contra.verdict.claim_span or "this value"
        clause_span = contra.verdict.clause_span or "a different value"
        conflict = ClauseVerdict(
            "conflicting_clauses",
            (
                f"The summary states {claim_span}; {where_p} carries that value, but "
                f"{where_c} states {clause_span}. The retrieved clauses conflict, so this "
                "statement was not independently checked. Review both clauses."
            ),
            contra.verdict.anchor_type,
            contra.verdict.claim_values,
            values_p + tuple(contra.verdict.clause_values),
            claim_span=contra.verdict.claim_span,
            clause_span=contra.verdict.clause_span,
        )
        # Carry the value-bearing clause's location: it is where the claim's
        # value verifiably lives, so the quote pool and the card's section
        # point at real matching text rather than the accusing clause.
        return conflict, section_p, clause_text_p
    if on_topic_presents:
        chosen = on_topic_presents[0]
        return chosen.verdict, chosen.section, chosen.clause_text
    if multi_value is not None:
        return multi_value.verdict, multi_value.section, multi_value.clause_text
    return (
        ClauseVerdict("not_found", "no matching passage found in your loaded sources"),
        None,
        None,
    )
