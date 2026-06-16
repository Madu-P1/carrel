"""ADR-0013 subject labeler: the regex floor, provider resolution, provenance.

The labeler PROPOSES a subject; the deterministic disposer DISPOSES the verdict, so
these tests pin the floor's conservatism (qualifier-only, never a bare role, which is
what manufactured false accusations in the reverted regex-gate attempt) and the
fail-closed provider resolution (off by default; visible degrade to the floor).
"""

from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

from ai.subject_labeler import (
    AFMSubjectLabeler,
    Label,
    RegexFloorLabeler,
    get_subject_labeler,
    regex_subject,
)
from services.legal.anchors import extract_anchors


@contextmanager
def _env(value):
    prev = os.environ.get("CARREL_SUBJECT_LABELER")
    if value is None:
        os.environ.pop("CARREL_SUBJECT_LABELER", None)
    else:
        os.environ["CARREL_SUBJECT_LABELER"] = value
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("CARREL_SUBJECT_LABELER", None)
        else:
            os.environ["CARREL_SUBJECT_LABELER"] = prev


def _money_start(text):
    return next(a.start for a in extract_anchors(text) if a.type == "money")


class RegexFloorBindingTests(unittest.TestCase):
    def test_binds_the_qualified_shape(self):
        t = "The liability cap is $5,000,000."
        self.assertEqual("liability", regex_subject(t, _money_start(t)))

    def test_binds_a_different_qualified_subject(self):
        t = "The indemnification cap is $5,000,000."
        self.assertEqual("indemnification", regex_subject(t, _money_start(t)))

    def test_declines_a_bare_role_word(self):
        # "the cap is $5M" -> bare role, no qualifier -> None (NEVER bind a bare role;
        # that is what manufactured false accusations on multi-figure lists).
        t = "The cap is $5,000,000."
        self.assertIsNone(regex_subject(t, _money_start(t)))

    def test_declines_the_capped_at_phrasing(self):
        # The regex-unbindable shape the AFM labeler exists to cover. Floor declines.
        t = "The Seller's liability shall be capped at $5,000,000."
        self.assertIsNone(regex_subject(t, _money_start(t)))

    def test_floor_label_map_carries_regex_provenance(self):
        t = "The security deposit is $250,000."
        labels = RegexFloorLabeler().label_subjects(t, extract_anchors(t))
        self.assertEqual(1, len(labels))
        (label,) = labels.values()
        self.assertIsInstance(label, Label)
        self.assertEqual("security", label.subject)
        self.assertEqual("regex", label.source)


class ProviderResolutionTests(unittest.TestCase):
    def test_off_by_default_returns_none(self):
        with _env(None):
            self.assertIsNone(get_subject_labeler())

    def test_explicit_off_returns_none(self):
        with _env("false"):
            self.assertIsNone(get_subject_labeler())

    def test_regex_mode_returns_floor(self):
        with _env("regex"):
            labeler = get_subject_labeler()
        self.assertIsInstance(labeler, RegexFloorLabeler)

    def test_afm_mode_falls_back_visibly_to_floor_when_unavailable(self):
        # AFM unavailable -> the AFM labeler degrades to the floor and emits NO "afm"
        # provenance (no silent AI fallback: it never claims a model labeled).
        labeler = AFMSubjectLabeler(afm_client=None)
        t = "The notice period is 3 years."
        labels = labeler.label_subjects(t, extract_anchors(t))
        self.assertTrue(labels)
        self.assertTrue(all(v.source == "regex" for v in labels.values()))


class _FakeResult:
    def __init__(self, ok, json_payload):
        self.ok = ok
        self.json_payload = json_payload


class _FakeAFM:
    """Stands in for AFMClient so the request body is tested without AFM hardware."""

    def __init__(self, ok=True, payload=None):
        self._ok = ok
        self._payload = payload
        self.calls = []

    def ai_enabled(self):
        return True

    def request_json(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResult(self._ok, self._payload)


class AFMRequestBodyTests(unittest.TestCase):
    def test_model_label_wins_with_afm_provenance(self):
        fake = _FakeAFM(ok=True, payload={"1": "liability cap"})
        t = "The liability cap is $5,000,000."
        labels = AFMSubjectLabeler(afm_client=fake).label_subjects(t, extract_anchors(t))
        (label,) = labels.values()
        self.assertEqual("liability cap", label.subject)
        self.assertEqual("afm", label.source)
        # The request was actually issued with the verify request_kind.
        self.assertEqual("verify.subject_label", fake.calls[0]["request_kind"])

    def test_afm_failure_falls_back_to_floor_visibly(self):
        fake = _FakeAFM(ok=False, payload=None)
        t = "The liability cap is $5,000,000."
        labels = AFMSubjectLabeler(afm_client=fake).label_subjects(t, extract_anchors(t))
        self.assertTrue(all(v.source == "regex" for v in labels.values()))

    def test_malformed_payload_falls_back_to_floor(self):
        fake = _FakeAFM(ok=True, payload="not a dict")
        t = "The liability cap is $5,000,000."
        labels = AFMSubjectLabeler(afm_client=fake).label_subjects(t, extract_anchors(t))
        self.assertTrue(all(v.source == "regex" for v in labels.values()))

    def test_null_subject_on_unbindable_text_yields_no_label(self):
        # Floor cannot bind "shall be capped at"; the model returns null -> no label.
        fake = _FakeAFM(ok=True, payload={"1": None})
        t = "The Seller shall be capped at $5,000,000."
        labels = AFMSubjectLabeler(afm_client=fake).label_subjects(t, extract_anchors(t))
        self.assertEqual({}, labels)


if __name__ == "__main__":
    unittest.main()
