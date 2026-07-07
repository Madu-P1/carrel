"""The vendored self-contradiction detectors, surfaced through the kernel.

Locks that the 8 campaign detectors are part of ``cachet_verify`` (not
``services``), that ``attest_draft`` surfaces their findings additively, and
that the certificate seals them. A planted words-vs-figures conflict must
surface as one FLAGGED structural finding; a clean draft must surface none; a
cross-document conflict across two sources must surface one FLAGGED
cross-document finding. The kernel stays self-contained: nothing here imports
from ``services``.
"""

from __future__ import annotations

import unittest

from cachet_verify.adapter import attest_draft
from cachet_verify.certificate import attest_and_issue, verify_certificate
from cachet_verify.detectors import scan_cross_document, scan_draft


class ScanDraftTests(unittest.TestCase):
    def test_words_figures_conflict_is_flagged(self) -> None:
        findings = scan_draft("The cure period is thirty (40) days after notice.")
        self.assertEqual(1, len(findings))
        self.assertEqual("words_figures_conflict", findings[0]["kind"])
        self.assertEqual("flagged", findings[0]["disposition"])
        self.assertEqual("thirty (40)", findings[0]["span"])

    def test_clean_draft_yields_no_findings(self) -> None:
        self.assertEqual([], scan_draft("The outlook remains bright and steady."))

    def test_empty_and_nonstring_drafts_are_safe(self) -> None:
        self.assertEqual([], scan_draft(""))
        self.assertEqual([], scan_draft(None))  # type: ignore[arg-type]


class ScanCrossDocumentTests(unittest.TestCase):
    def test_conflicting_label_across_two_sources_is_flagged(self) -> None:
        findings = scan_cross_document(
            [
                ("Agreement", "Termination Fee: $100"),
                ("Amendment", "Termination Fee: $250"),
            ]
        )
        self.assertEqual(1, len(findings))
        self.assertEqual("cross_document_conflict", findings[0]["kind"])
        self.assertEqual("flagged", findings[0]["disposition"])
        self.assertEqual("Termination Fee", findings[0]["label"])
        self.assertEqual(2, len(findings[0]["figures"]))

    def test_single_source_yields_no_findings(self) -> None:
        self.assertEqual([], scan_cross_document([("only", "Termination Fee: $100")]))

    def test_agreeing_sources_yield_no_findings(self) -> None:
        self.assertEqual(
            [],
            scan_cross_document(
                [
                    ("Agreement", "Termination Fee: $100"),
                    ("Amendment", "Termination Fee: $100"),
                ]
            ),
        )


class AttestDraftSurfacesFindingsTests(unittest.TestCase):
    def test_planted_words_figures_conflict_surfaces(self) -> None:
        draft = "The cure period is thirty (40) days after notice."
        att = attest_draft(draft, ["The cure period is thirty (40) days after notice."])
        self.assertEqual(1, len(att.structural_findings))
        self.assertEqual("words_figures_conflict", att.structural_findings[0]["kind"])
        self.assertEqual("flagged", att.structural_findings[0]["disposition"])

    def test_clean_draft_surfaces_no_structural_findings(self) -> None:
        att = attest_draft("The outlook remains bright.", ["The outlook remains bright."])
        self.assertEqual((), att.structural_findings)

    def test_cross_document_conflict_surfaces(self) -> None:
        draft = "The parties agree to the terms."
        sources = ["Termination Fee: $100", "Termination Fee: $250"]
        att = attest_draft(draft, sources)
        self.assertEqual(1, len(att.cross_document_findings))
        self.assertEqual("cross_document_conflict", att.cross_document_findings[0]["kind"])
        self.assertEqual("flagged", att.cross_document_findings[0]["disposition"])
        self.assertEqual("Termination Fee", att.cross_document_findings[0]["label"])

    def test_findings_are_additive_not_state_changing(self) -> None:
        # The structural pass never moves the draft-level state: a faithfully
        # copied draft stays verified even while an intra-draft self-conflict is
        # flagged (the conflict is a review register, not a source verdict).
        draft = "The cure period is thirty (40) days after notice."
        att = attest_draft(draft, [draft])
        self.assertEqual("verified", att.state)
        self.assertTrue(att.structural_findings)


class CertificateSealsFindingsTests(unittest.TestCase):
    ISSUED = "2026-07-07T00:00:00+00:00"

    def test_findings_ride_inside_the_sealed_body(self) -> None:
        draft = "The cure period is thirty (40) days after notice."
        cert = attest_and_issue(draft, [draft], self.ISSUED)
        self.assertIn("structural_findings", cert)
        self.assertIn("cross_document_findings", cert)
        self.assertTrue(cert["structural_findings"])
        self.assertTrue(verify_certificate(cert))

    def test_tampering_a_finding_breaks_the_seal(self) -> None:
        draft = "The cure period is thirty (40) days after notice."
        cert = attest_and_issue(draft, [draft], self.ISSUED)
        cert["structural_findings"][0]["disposition"] = "could_not_check"
        self.assertFalse(verify_certificate(cert))


if __name__ == "__main__":
    unittest.main()


class TamperEvidenceOnSealedFindings(unittest.TestCase):
    """Mythos 2026-07-07: the sealed structural_findings/cross_document_findings must
    revalidate like claims, so a stripped FLAGGED catch cannot be re-fingerprinted into
    an authentic-looking certificate (a false-green on the exhibit)."""

    def _cert_and_inputs(self):
        from cachet_verify.adapter import SourceText
        from cachet_verify.certificate import attest_and_issue

        draft = "The initial term is thirty (40) days from the Effective Date."
        sources = [SourceText("The initial term is thirty days.")]
        return attest_and_issue(draft, sources, "2026-07-07T00:00:00Z"), draft, sources

    def test_stripping_a_sealed_finding_fails_revalidation(self):
        import copy

        from cachet_verify.certificate import (
            canonical_json,
            revalidate_certificate,
            sha256_hex,
        )

        cert, draft, sources = self._cert_and_inputs()
        self.assertTrue(cert.get("structural_findings"), "precondition: a finding was sealed")
        # The attack: strip the flagged finding and recompute the self-consistency seal.
        tampered = copy.deepcopy(cert)
        tampered["structural_findings"] = []
        body = {k: v for k, v in tampered.items() if k != "fingerprint"}
        tampered["fingerprint"] = sha256_hex(canonical_json(body))
        result = revalidate_certificate(tampered, draft, sources)
        self.assertFalse(result["valid"], "a stripped finding must not revalidate as authentic")
        self.assertFalse(result["verdicts_reproduced"])

    def test_honest_certificate_still_revalidates(self):
        from cachet_verify.certificate import revalidate_certificate

        cert, draft, sources = self._cert_and_inputs()
        self.assertTrue(revalidate_certificate(cert, draft, sources)["valid"])
