"""Stage 3 + Validators coverage for the typed-node Ask pipeline.

Master plan Phase 2 acceptance: at least 8 cases across the four match
functions and the two invariant enforcers in
`services.retrieval.validators`. Mirrors the existing tutor-validator test
file (`tests/test_citation_quote_validation.py`) but exercises the public
node-id-keyed API instead of the underscore-prefixed chunk-id-keyed
functions.

Cases:

1. `normalize_match_text` NFKC ligature expansion preserves index_map.
2. `normalize_match_text` smart-quote translation produces a stable form.
3. `validated_citation_quote` returns an exact-substring match with
   `repaired=False`.
4. `validated_citation_quote` repairs an LLM-emitted `finance` against
   source content carrying the `ﬁ` ligature, marking `repaired=True`.
5. `validated_citation_quote` rejects below the 0.95 fuzzy similarity
   floor (PR-D1 contract).
6. `enforce_citation_in_retrieved_set` drops a citation whose `node_id`
   is not in the retrieval result set (Invariant 1).
7. `enforce_citation_in_retrieved_set` keeps a citation whose `node_id`
   is in the set.
8. `enforce_verbatim_substring` rejects a lowercase quote against an
   uppercase node text (Invariant 2 case-strict).
9. `enforce_verbatim_substring` accepts an exact-case substring quote
   (Invariant 2 happy path).
10. `enforce_verbatim_substring` accepts after whitespace normalization
    of a non-breaking-space-separated quote.

The legacy chunks-tutor validator test at
`tests/test_citation_quote_validation.py` must stay green after this
file lands; both modules coexist until master plan Phase 3 ports the
Pro tutor to the typed-node path.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.retrieval.validators import (
    NodeCitation,
    enforce_citation_in_retrieved_set,
    enforce_verbatim_substring,
    normalize_match_text,
    slice_original_span,
    validated_citation_quote,
)


@dataclass(frozen=True)
class _FakeNode:
    """Stand-in for `services.retrieval.typed_hybrid.RetrievedNode`.

    `enforce_verbatim_substring` only reads `verbatim_text`; the full
    RetrievedNode shape is overkill for these unit tests. Using the real
    dataclass would pull in pgvector imports for a pure-Python test.
    """

    verbatim_text: str
    node_id: int = 1


# ---------------------------------------------------------------------------
# normalize_match_text
# ---------------------------------------------------------------------------


def test_normalize_match_text_nfkc_ligature_preserves_index_map():
    """NFKC expands `ﬁ` to `fi`; both output chars must point at the source
    index of the ligature so `slice_original_span` returns the literal
    ligature on read-back.

    Includes the round-trip slice assertion to lock the invariant: matching
    the full normalized span back to the source yields the original
    pre-NFKC form (with the ligature intact)."""
    result = normalize_match_text("ﬁnance")

    assert result.text == "finance"
    # First two normalized chars come from source index 0 (the ligature).
    assert result.index_map[0] == 0
    assert result.index_map[1] == 0
    # Subsequent chars index 1, 2, 3, 4, 5.
    assert result.index_map[2:7] == (1, 2, 3, 4, 5)

    # Round-trip: slicing the full 7-char normalized span returns the
    # original 6-char source string (ligature counts as one source char).
    assert slice_original_span("ﬁnance", result, 0, 7) == "ﬁnance"


def test_normalize_match_text_smart_quotes_translate_to_ascii():
    """Curly quotes normalize to straight ASCII quotes so cross-source
    quoting (LLM emits straight, source has curly or vice versa) matches."""
    curly = normalize_match_text("He said “hello”.")
    straight = normalize_match_text('He said "hello".')

    assert curly.text == straight.text == 'he said "hello".'


# ---------------------------------------------------------------------------
# validated_citation_quote
# ---------------------------------------------------------------------------


def test_validated_citation_quote_exact_match_not_repaired():
    """An LLM quote that is already a verbatim substring (after NFKC + ws
    collapse) returns repaired=False."""
    content = "Metaphase chromosomes align at the cell equator."
    match = validated_citation_quote("Metaphase chromosomes align", content)

    assert match is not None
    assert match.quote == "Metaphase chromosomes align"
    assert match.repaired is False


def test_validated_citation_quote_repairs_ligature_quote():
    """LLM quotes `finance`; source has the `ﬁ` ligature. NFKC normalizes
    both to the same form; slice returns the original ligature span and
    `repaired=True` flags the case fix."""
    content = "Mergers in ﬁnance often involve regulatory hurdles."
    match = validated_citation_quote("finance", content)

    assert match is not None
    # Original-form ligature returned, NOT the lowercase ASCII quote.
    assert match.quote == "ﬁnance"
    assert match.repaired is True


def test_validated_citation_quote_rejects_below_fuzzy_floor():
    """PR-D1 contract: similarity must reach 0.95. A 50-char quote with
    only a short common substring against unrelated content drops to
    `None` instead of being silently rewritten.

    This case rejects on the `min_length` guard (longest match shorter
    than 40 chars). The next test pins the 0.95 similarity floor
    specifically (match passes min_length, fails similarity)."""
    content = "Carrel is a study tool for people with deadlines."
    paraphrase = "Carrel is a research workspace for deadline-driven scholars"

    match = validated_citation_quote(paraphrase, content)

    assert match is None


def test_validated_citation_quote_rejects_on_similarity_floor_not_min_length():
    """Pin the 0.95 similarity floor specifically.

    Quote is 50 chars of repeating `x`. Content has 42 verbatim `x`
    chars followed by unrelated text. The longest common substring is 42
    chars (above the 40-char `min_length` guard) but similarity is
    42/50 = 0.84, below the 0.95 PR-D1 floor. Without this test, the
    rejection path that fires for the previous test is the min_length
    guard, leaving the similarity floor un-pinned."""
    quote = "x" * 50
    content = "x" * 42 + " unrelated text after the verbatim run"

    match = validated_citation_quote(quote, content)

    assert match is None


# ---------------------------------------------------------------------------
# enforce_citation_in_retrieved_set (Invariant 1)
# ---------------------------------------------------------------------------


def test_enforce_citation_in_retrieved_set_drops_hallucinated_node_id():
    """The model emitted node_id=99 but retrieval only surfaced {1, 2, 3}.
    The citation is hallucinated coverage and must be dropped."""
    citations = [
        NodeCitation(node_id=1, quote="legitimate quote"),
        NodeCitation(node_id=99, quote="hallucinated coverage"),
        NodeCitation(node_id=3, quote="another legitimate quote"),
    ]
    retrieved = {1, 2, 3}

    kept = enforce_citation_in_retrieved_set(citations, retrieved)

    kept_ids = [c.node_id for c in kept]
    assert kept_ids == [1, 3]
    assert all(c.node_id in retrieved for c in kept)


def test_enforce_citation_in_retrieved_set_keeps_all_when_all_in_set():
    """Happy path: every citation's node_id is in the retrieval set; no
    drops; ordering preserved."""
    citations = [
        NodeCitation(node_id=2, quote="q1"),
        NodeCitation(node_id=1, quote="q2"),
    ]
    retrieved = {1, 2, 3}

    kept = enforce_citation_in_retrieved_set(citations, retrieved)

    assert [c.node_id for c in kept] == [2, 1]
    assert len(kept) == len(citations)


# ---------------------------------------------------------------------------
# enforce_verbatim_substring (Invariant 2)
# ---------------------------------------------------------------------------


def test_enforce_verbatim_substring_rejects_case_mismatch():
    """`metaphase` (lowercase) is NOT a verbatim substring of `Metaphase
    chromosomes align`. The validator preserves case and rejects, unlike
    `validated_citation_quote` which would lowercase and accept."""
    node = _FakeNode(
        verbatim_text="Metaphase chromosomes align at the cell equator."
    )
    citation = NodeCitation(node_id=1, quote="metaphase chromosomes align")

    result = enforce_verbatim_substring(citation, node)

    assert result is None


def test_enforce_verbatim_substring_accepts_exact_substring():
    """Exact-case substring quote returns the citation unchanged."""
    node = _FakeNode(
        verbatim_text="Metaphase chromosomes align at the cell equator."
    )
    citation = NodeCitation(node_id=1, quote="Metaphase chromosomes align")

    result = enforce_verbatim_substring(citation, node)

    assert result is citation


def test_enforce_verbatim_substring_normalizes_non_breaking_space():
    """Quote uses normal space; source uses non-breaking space. NFKC +
    whitespace collapse on both sides aligns them; the substring check
    succeeds without losing case strictness on the rest of the string."""
    node = _FakeNode(
        verbatim_text="Metaphase chromosomes align at the cell equator."
    )
    citation = NodeCitation(node_id=1, quote="Metaphase chromosomes align")

    result = enforce_verbatim_substring(citation, node)

    assert result is citation
