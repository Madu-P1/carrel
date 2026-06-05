"""Offline case-existence backend for the Cachet litigator demo.

Serves the CourtListener citation-lookup endpoint from a bundled,
in-process corpus of pre-vetted cases, behind the existing ``client=``
seam on ``case_verification`` / ``courtlistener``. The litigator catch
then runs with zero network: a real cite resolves from the corpus
(status 200), a fabricated cite is simply absent (status 404 ->
exists=False), exactly as the live API would answer.

Honesty: this is a DEMO corpus of a handful of real cases, not the full
CourtListener mirror. The scope is disclosed in the UI; a cite outside
the corpus returns "not found", which for the demo's pre-vetted draft is
correct, but is NOT a general litigator-coverage claim.

Usage (the demo sets a sentinel token so the lookup's token guard passes;
the token never leaves the device because the MockTransport answers
locally)::

    import os
    os.environ["COURTLISTENER_API_TOKEN"] = "local"
    client = local_caselaw_client()
    verify_claims_for_cases(claims, client=client, enable_holding_match=False)
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs

import httpx

from .citations_eyecite import find_citations

_CITATION_LOOKUP_PATH = "/citation-lookup/"


@dataclass(frozen=True)
class LocalCase:
    case_name: str
    absolute_url: str
    court: str
    date_filed: str


# Real, pre-vetted Supreme Court cases keyed by normalized citation.
DEMO_CORPUS: dict[str, LocalCase] = {
    "347 U.S. 483": LocalCase(
        "Brown v. Board of Education",
        "/opinion/103200/brown-v-board-of-education/",
        "scotus",
        "1954-05-17",
    ),
    "576 U.S. 644": LocalCase(
        "Obergefell v. Hodges", "/opinion/3036702/obergefell-v-hodges/", "scotus", "2015-06-26"
    ),
    "410 U.S. 113": LocalCase("Roe v. Wade", "/opinion/108713/roe-v-wade/", "scotus", "1973-01-22"),
}


def _lookup_response(text: str, corpus: dict[str, LocalCase]) -> list[dict]:
    """Build a CourtListener-shaped citation-lookup response from the corpus."""
    out: list[dict] = []
    for ref in find_citations(text):
        cite = ref.matched_text
        case = corpus.get(cite)
        if case is None:
            out.append(
                {
                    "citation": cite,
                    "normalized_citations": [cite],
                    "start_index": ref.start,
                    "end_index": ref.end,
                    "status": 404,
                    "error_message": f"Citation not found: '{cite}'",
                    "clusters": [],
                }
            )
            continue
        out.append(
            {
                "citation": cite,
                "normalized_citations": [cite],
                "start_index": ref.start,
                "end_index": ref.end,
                "status": 200,
                "error_message": "",
                "clusters": [
                    {
                        "case_name": case.case_name,
                        "absolute_url": case.absolute_url,
                        "court": case.court,
                        "date_filed": case.date_filed,
                    }
                ],
            }
        )
    return out


def local_caselaw_client(corpus: dict[str, LocalCase] | None = None) -> httpx.Client:
    """An ``httpx.Client`` that answers citation-lookup from ``corpus`` locally."""
    cases = corpus if corpus is not None else DEMO_CORPUS

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(_CITATION_LOOKUP_PATH):
            form = parse_qs(request.content.decode("utf-8"))
            text = (form.get("text") or [""])[0]
            return httpx.Response(200, json=_lookup_response(text, cases))
        return httpx.Response(404, json={})

    return httpx.Client(transport=httpx.MockTransport(handler))
