"""Cachet adversary battery: contract-path wrapped-quote anchor-laundering (bedd143a1).

Report-only. Attacks the new logical-sentence contract pass in
build_deterministic_envelope for FALSE GREENS (a verified card that rides a
fabricated/altered wrapped quote) and over-refusals (a verbatim wrapped quote
wrongly downgraded). Minimal mock-retrieval harness so each case controls its
exact clause(s); no network, deterministic engine only.
"""

from __future__ import annotations

import os
import sqlite3
from unittest import mock

from services import verify as verify_service
from services.legal.deterministic_envelope import build_deterministic_envelope
from services.legal.local_caselaw import local_caselaw_client
from services.retrieval.typed_hybrid import RetrievedNode

NL = chr(10)
CR = chr(13)
LDQ = chr(8220)  # “
RDQ = chr(8221)  # ”


def _node(text: str, order: int = 0) -> RetrievedNode:
    return RetrievedNode(
        node_id=order + 1,
        doc_id="d1",
        node_type="body",
        heading_path="Agreement",
        page=None,
        char_start=0,
        char_end=len(text),
        verbatim_text=text,
        snippet=text,
        score=1.0 - order * 0.01,
    )


def _conn(clauses: list[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE documents (id TEXT, status TEXT)")
    conn.execute("INSERT INTO documents VALUES ('d1', 'ready')")
    conn.execute("CREATE TABLE nodes (doc_id TEXT, verbatim_text TEXT, reading_order INTEGER)")
    for i, c in enumerate(clauses):
        conn.execute("INSERT INTO nodes VALUES ('d1', ?, ?)", (c, i))
    conn.commit()
    return conn


def run_case(draft: str, clauses: list[str]) -> list[dict]:
    conn = _conn(clauses)
    nodes = [_node(c, i) for i, c in enumerate(clauses)]
    with (
        mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False),
        mock.patch(
            "services.legal.deterministic_envelope.search_typed_hybrid",
            return_value=nodes,
        ),
    ):
        env = build_deterministic_envelope(
            draft, conn=conn, doc_ids=["d1"], embedder=object(), client=local_caselaw_client()
        )
    result = verify_service._verify_result_from_envelope(draft, env, 0.0)
    out = []
    # Align cards to claims by claim_index, NOT positionally: _verify_result_from_envelope
    # drops untreated/non-dict claims from claim_verdicts while env["claims"] keeps every
    # claim in order, so a leading anchor-free sentence would shift a positional zip and
    # read disposition/anchor_type off the wrong claim. claim_index is the enumerate index
    # into env["claims"]; span cards carry indices past the claim list and map to None.
    claims_by_index = {i: c for i, c in enumerate(env["claims"])}
    for card in result.claim_verdicts:
        claim = claims_by_index.get(card.claim_index)
        cv = (claim.get("contract_verdict") if isinstance(claim, dict) else None) or {}
        out.append(
            {
                "text": card.claim_text,
                "verdict": card.verdict,
                "disposition": cv.get("disposition"),
                "anchor_type": cv.get("anchor_type"),
                "quote_reason": bool(
                    isinstance(claim, dict) and claim.get("quote_could_not_check_reason")
                ),
            }
        )
    # untreated claims produce no card; surface them too for completeness
    carded = {c.claim_text for c in result.claim_verdicts}
    for claim in env["claims"]:
        if claim.get("untreated") and claim["text"] not in carded:
            out.append(
                {
                    "text": claim["text"],
                    "verdict": "(untreated)",
                    "disposition": None,
                    "anchor_type": None,
                    "quote_reason": False,
                }
            )
    return out


GOV = (
    "Section 11. This Agreement shall be governed by and construed in accordance with "
    "the laws of the State of Delaware; the parties submit to the exclusive "
    "jurisdiction of the courts of New York."
)
PCT = (
    "Section 9.2. The royalty equals 50% of the net fees received in the twelve (12) "
    "months preceding each report."
)
POL = (
    "Section 2.1. Licensor hereby grants Licensee a non-exclusive, non-transferable "
    "license to use the Software during the Term."
)
NEUTRAL = "Section 3. The parties shall cooperate in good faith on all matters."

# Each case: (id, attack-family, draft, clauses, fabricated_or_altered_phrase, note)
# fabricated_phrase: the words that must NEVER appear inside a 'verified' card.
# If fabricated_phrase is None, the quote is CLEAN (verbatim) and the present must
# stay 'verified' (over-refusal hunt).
CASES = [
    # ---- Family A: wrapped fabricated quote riding a non-quote present ----
    (
        "A1",
        "false_green",
        "gov present, fab quote OPENS on present line",
        'The agreement is governed by Delaware law and the parties stipulated that "the'
        + NL
        + 'receiving party shall return all materials upon request."',
        [GOV],
        "receiving party shall return all materials upon request",
    ),
    (
        "A2",
        "false_green",
        "gov present, fab quote WHOLLY on line 2",
        "The agreement is governed by Delaware law and the parties further agreed"
        + NL
        + '"the vendor shall maintain insurance of any amount it deems prudent."',
        [GOV],
        "the vendor shall maintain insurance of any amount it deems prudent",
    ),
    (
        "A3",
        "false_green",
        "percent present, fab quote wrapped",
        'The royalty equals 50% of net fees and the schedule states that amounts are "paid'
        + NL
        + 'only after written acceptance by the steering committee."',
        [PCT],
        "paid only after written acceptance by the steering committee",
    ),
    (
        "A4",
        "false_green",
        "polarity present, fab quote wrapped",
        'The agreement grants Licensee a non-exclusive license and the parties confirmed that "the'
        + NL
        + 'Software may be freely redistributed to any third party."',
        [POL],
        "Software may be freely redistributed to any third party",
    ),
    (
        "A5",
        "false_green",
        "gov present, fab quote split across THREE lines",
        'The agreement is governed by Delaware law and it provides that "the'
        + NL
        + "receiving party shall return"
        + NL
        + 'all materials upon request."',
        [GOV],
        "receiving party shall return all materials upon request",
    ),
    (
        "A4b",
        "false_green",
        "clean polarity PRESENT + fab quote wrapped (forces a polarity green)",
        'The agreement grants Licensee a non-exclusive license to use the Software and notes that "the'
        + NL
        + 'Licensee keeps one copy for its own files."',
        [POL],
        "Licensee keeps one copy for its own files",
    ),
    (
        "A6",
        "false_green",
        "percent present + ALTERED quote with a [bracket] edit-mark straddling the wrap",
        'The royalty equals 50% of net fees and the clause provides "received in the [twelve]'
        + NL
        + 'months following each report."',
        [PCT],
        "months following each report",
    ),
    (
        "A7",
        "false_green",
        "percent present + quote whose words are SCATTERED (non-contiguous) in clause, wrapped",
        'The royalty equals 50% of net fees and the clause provides that fees are "received'
        + NL
        + 'each report."',
        [PCT],
        "received each report",
    ),
    # ---- Family B: clean verbatim wrapped quote must STAY verified (over-refusal hunt) ----
    (
        "B1",
        "over_refusal",
        "percent present, VERBATIM wrapped quote",
        'The royalty equals 50% of net fees and the clause provides that fees are "received'
        + NL
        + 'in the twelve (12) months preceding each report."',
        [PCT],
        None,
    ),
    (
        "B2",
        "over_refusal",
        "percent present, verbatim wrapped quote with CRLF",
        'The royalty equals 50% of net fees and the clause provides that fees are "received'
        + CR
        + NL
        + 'in the twelve (12) months preceding each report."',
        [PCT],
        None,
    ),
    (
        "B3",
        "over_refusal",
        "percent present, verbatim wrapped quote in CURLY quotes",
        "The royalty equals 50% of net fees and the clause provides that fees are "
        + LDQ
        + "received"
        + NL
        + "in the twelve (12) months preceding each report."
        + RDQ,
        [PCT],
        None,
    ),
    (
        "B4",
        "over_refusal",
        "percent present, verbatim wrapped quote, leading-letter case flip",
        'The royalty equals 50% of net fees and the clause provides that "Received'
        + NL
        + 'in the twelve (12) months preceding each report."',
        [PCT],
        None,
    ),
    # ---- Family C: proximity is not attribution (real sentence boundary) ----
    (
        "C1",
        "boundary",
        "gov present then PERIOD then fab wrapped quote (separate sentence)",
        'The agreement is governed by Delaware law. The parties also agreed that "the'
        + NL
        + 'receiving party shall return all materials upon request."',
        [GOV],
        "receiving party shall return all materials upon request",
    ),
    # ---- Family D: multi-clause pooling scope ----
    (
        "D1",
        "pooling",
        "gov present (clause A); fab quote is VERBATIM in sibling non-present clause B",
        'The agreement is governed by Delaware law and the parties agreed that "the'
        + NL
        + 'receiving party shall return all materials upon request."',
        [
            GOV,
            "Section 5. Upon termination, the receiving party shall return all materials upon request.",
        ],
        # Honest deterministic call: the quote sits in B, not in the governing present's clause A,
        # so attributing it to the present is unconfirmed -> refusal is correct (recall-safe).
        "receiving party shall return all materials upon request",
    ),
    # ---- Family E: quote-present + a SECOND fabricated quote (pre-existing exemption probe) ----
    (
        "E1",
        "quote_present_multi",
        "verbatim quote (quote-present) + second FABRICATED quote, same line",
        'The agreement requires that "The parties shall cooperate in good faith on all matters" '
        'and also that "no party shall ever be liable for consequential damages."',
        [NEUTRAL],
        "no party shall ever be liable for consequential damages",
    ),
    (
        "E2",
        "quote_present_multi",
        "verbatim quote (quote-present) + second FABRICATED quote, WRAPPED",
        'The agreement requires that "The parties shall cooperate in good faith on all matters" '
        'and also that "no party shall ever' + NL + 'be liable for consequential damages."',
        [NEUTRAL],
        "no party shall ever be liable for consequential damages",
    ),
]


def classify(case, cards) -> tuple[str, str]:
    cid, family, note, draft, clauses, fab = case
    # Normalize whitespace for the "phrase inside a verified card" test (the card text
    # is the per-line segment; a wrapped fabricated phrase may be split, so also test
    # the whole-draft verified set by joining all verified card texts).
    verified_text = " ".join(
        " ".join(c["text"].split()) for c in cards if c["verdict"] == "verified"
    )
    if fab is None:
        # Over-refusal hunt: the present must remain verified.
        any_verified = any(c["verdict"] == "verified" for c in cards)
        if any_verified:
            return "HELD", "verbatim quote kept the present verified (no over-refusal)"
        return (
            "OVER_REFUSAL",
            "a verbatim wrapped quote was downgraded; the present should stay verified",
        )
    # False-green hunt: the fabricated phrase must NOT sit inside any verified card.
    fab_norm = " ".join(fab.split())
    if fab_norm in verified_text:
        return "FALSE_GREEN", f"fabricated phrase appears inside a verified card: {fab_norm!r}"
    return "HELD", "no verified card carries the fabricated phrase (refused or isolated)"


def main() -> int:
    print("Cachet adversary battery — contract wrapped-quote laundering\n")
    counts = {"HELD": 0, "FALSE_GREEN": 0, "OVER_REFUSAL": 0}
    cracks = []
    for case in CASES:
        cid, family, note, draft, clauses, fab = case
        cards = run_case(draft, clauses)
        verdict, why = classify(case, cards)
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict != "HELD":
            cracks.append((cid, family, note, why, cards))
        flag = {"HELD": "ok", "FALSE_GREEN": "P0!!", "OVER_REFUSAL": "P1"}[verdict]
        print(f"[{cid}] {family:20} {verdict:13} [{flag}]  {note}")
        for c in cards:
            print(
                f"        - {c['verdict']:11} disp={str(c['disposition']):26} "
                f"qreason={c['quote_reason']}  {c['text'][:70]!r}"
            )
    print(
        f"\nSUMMARY: HELD {counts['HELD']}  FALSE_GREEN {counts['FALSE_GREEN']}  "
        f"OVER_REFUSAL {counts['OVER_REFUSAL']}  (of {len(CASES)})"
    )
    if cracks:
        print("\nCRACKS:")
        for cid, family, note, why, _cards in cracks:
            print(f"  - [{cid}] {family}: {why}")
    else:
        print(
            "\nNo cracks: every attack was HELD (refused or isolated; no false green, no over-refusal)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
