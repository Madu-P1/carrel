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

import hashlib
from dataclasses import dataclass
from urllib.parse import parse_qs

import httpx

from .citations_eyecite import find_citations

_CITATION_LOOKUP_PATH = "/citation-lookup/"

# The attribute under which a corpus-serving client carries its measured
# attestation (E2). The deterministic envelope reads it back to cross-check an
# operator's scope="complete" manifest against the corpus actually loaded, so a
# manifest string alone can never turn a real-but-unbundled cite into a false
# "no such case". Named, not arbitrary: the attestation travels with the corpus
# on the client that serves it, mirroring how the manifest travels with the
# corpus rather than living in the engine.
CORPUS_ATTESTATION_ATTR = "cachet_corpus_attestation"


@dataclass(frozen=True)
class LocalCase:
    case_name: str
    absolute_url: str
    court: str
    date_filed: str
    # A verbatim opinion snippet, for the litigator altered-quote check (L4). The
    # demo bundles a real holding passage; production would serve full text.
    opinion_text: str = ""


@dataclass(frozen=True)
class CorpusManifest:
    """What the bundled corpus attests about itself (D13).

    The deterministic envelope reads this to decide ``bounded_corpus`` per run
    instead of hard-coding it: only a corpus whose operator attests
    ``scope="complete"`` may let a citation miss read "no such case as of
    <as_of>"; any other scope (or a missing manifest) folds a miss to the
    honest could-not-check. The attestation is the operator's claim about the
    data artifact, not something the engine can prove, which is why it is a
    manifest the corpus carries rather than a constant in the engine.
    """

    scope: str  # "demo" | "complete"
    case_count: int
    as_of: str  # ISO date the corpus snapshot reflects
    # Optional content fingerprint of the corpus the operator attests to (E2).
    # When present it is cross-checked against the measured corpus, so an operator
    # who declares the right SIZE but loaded a different set of cases is still
    # caught. Optional ("when available" in the spec): a manifest that predates
    # fingerprinting still cross-checks on size alone.
    content_hash: str | None = None

    def matches(self, attestation: CorpusAttestation) -> bool:
        """Does this DECLARED manifest match the MEASURED corpus (E2)?

        Size must agree. The content hash is checked only when this manifest
        declares one; a size-only manifest cross-checks on size alone, which is
        why a deployment that wants the strongest guarantee should also declare a
        ``content_hash`` (a size-only match cannot distinguish a same-size but
        different set of cases).
        """
        if self.case_count != attestation.case_count:
            return False
        if self.content_hash is not None and self.content_hash != attestation.content_hash:
            return False
        return True


@dataclass(frozen=True)
class CorpusAttestation:
    """The MEASURED truth of a loaded corpus: its size and a content fingerprint.

    Distinct from ``CorpusManifest``, which is the operator's DECLARATION. E2
    cross-checks the declaration against this measurement before honoring
    ``scope="complete"``. Computed over the in-memory corpus only, never the
    network, so the zero-egress invariant holds.
    """

    case_count: int
    content_hash: str


def corpus_fingerprint(corpus: dict[str, LocalCase]) -> str:
    """Order-independent sha256 over the corpus's citations and case identities.

    Two corpora holding the same cases produce the same fingerprint regardless of
    dict insertion order; adding, removing, or renaming any case changes it. Pure:
    same input -> same output, no I/O.
    """
    lines = sorted(
        f"{key}\x1f{case.case_name}\x1f{case.court}\x1f{case.date_filed}"
        for key, case in corpus.items()
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def attest_corpus(corpus: dict[str, LocalCase]) -> CorpusAttestation:
    """Measure a corpus: its case count and content fingerprint (E2)."""
    return CorpusAttestation(case_count=len(corpus), content_hash=corpus_fingerprint(corpus))


# Real, pre-vetted Supreme Court cases keyed by normalized citation.
DEMO_CORPUS: dict[str, LocalCase] = {
    "347 U.S. 483": LocalCase(
        "Brown v. Board of Education",
        "/opinion/103200/brown-v-board-of-education/",
        "scotus",
        "1954-05-17",
        opinion_text=(
            "We conclude that in the field of public education the doctrine of "
            "separate but equal has no place. Separate educational facilities are "
            "inherently unequal."
        ),
    ),
    "576 U.S. 644": LocalCase(
        "Obergefell v. Hodges", "/opinion/3036702/obergefell-v-hodges/", "scotus", "2015-06-26"
    ),
    "410 U.S. 113": LocalCase("Roe v. Wade", "/opinion/108713/roe-v-wade/", "scotus", "1973-01-22"),
}

# The bundled corpus is a demo, and its manifest says so: a miss against it
# must never read "citation not found". as_of is the snapshot date the cases
# were vetted and bundled (PR #115).
DEMO_MANIFEST = CorpusManifest(scope="demo", case_count=len(DEMO_CORPUS), as_of="2026-06-05")


def local_opinion_text(citation: str, corpus: dict[str, LocalCase] | None = None) -> str | None:
    """The bundled opinion text for a resolved citation, or None if not bundled.

    Tries the citation as given, then eyecite's normalized form, so a cite
    written in the official "347 U. S. 483" spacing still finds its opinion
    text (the altered-quote check must not silently degrade to could_not_check
    just because of reporter spacing).
    """
    cases = corpus if corpus is not None else DEMO_CORPUS
    case = cases.get(citation)
    if case is None and citation:
        for ref in find_citations(citation):
            case = cases.get(ref.corrected or ref.matched_text)
            if case is not None:
                break
    return case.opinion_text if case and case.opinion_text else None


def _lookup_response(text: str, corpus: dict[str, LocalCase]) -> list[dict]:
    """Build a CourtListener-shaped citation-lookup response from the corpus."""
    out: list[dict] = []
    for ref in find_citations(text):
        # Case-existence applies only to case citations. A statute/regulation
        # (C.F.R., U.S.C., an EU Directive) is not a case; never emit a not-found
        # verdict for one (it would read as a fabricated-case accusation on a real
        # regulation). Such cites are skipped here and handled as other anchors.
        if ref.kind != "case":
            continue
        cite = ref.matched_text
        # Key the corpus on eyecite's normalized form so the official reporter
        # spacing ("347 U. S. 483") and a trailing pincite/year still resolve;
        # the displayed `citation` stays as the lawyer wrote it.
        case = corpus.get(ref.corrected or cite) or corpus.get(cite)
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

    client = httpx.Client(transport=httpx.MockTransport(handler))
    # Carry the measured attestation of the corpus this client serves, so the
    # envelope can cross-check an operator's scope="complete" manifest against the
    # corpus actually loaded (E2). Computed offline over the in-memory dict.
    setattr(client, CORPUS_ATTESTATION_ATTR, attest_corpus(cases))
    return client
