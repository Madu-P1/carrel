"""Tests for the streaming Verify path (Cachet PR3).

Covers ``services.verify.verify_draft_stream`` + ``POST /api/verify/stream``:
  - event sequence: progress -> claims -> cite_verdict(s) -> result
  - the claims skeleton carries EMPTY case_verdicts (no premature pass)
  - the final result payload matches the non-stream ``verify_draft`` mapping
  - CRITICAL (invariant #6): a dropped/raising stream emits NO result event,
    so un-yielded claims are never reported as supported
  - empty draft short-circuits to a single result event
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from services import verify as verify_service

DRAFT = "Per 576 U.S. 644 the rule is X."


def _engine_claims():
    return [
        {
            "text": "Per 576 U.S. 644 the rule is X.",
            "citations": [{"node_id": "c1"}],
            "case_verdicts": [],
        },
        {
            "text": "Unsupported model claim.",
            "citations": [],
            "case_verdicts": [],
        },
    ]


def _case_verdict(index, *, verdicts):
    return {
        "claim_index": index,
        "ok": True,
        "verdicts": verdicts,
        "error_code": None,
        "error_message": None,
    }


_EXISTS_VERDICTS = [
    {
        "citation": "576 U.S. 644",
        "status": 200,
        "exists": True,
        "case_name": "Obergefell v. Hodges",
    }
]


def _final_envelope():
    return {
        "answer": "stub",
        "claims": [
            {
                "text": "Per 576 U.S. 644 the rule is X.",
                "citations": [{"node_id": "c1"}],
                "case_verdicts": [_case_verdict(0, verdicts=_EXISTS_VERDICTS)],
            },
            {
                "text": "Unsupported model claim.",
                "citations": [],
                "case_verdicts": [],
            },
        ],
        "unsupported_spans": ["Out-of-corpus span."],
        "model": "claude-sonnet-4-6",
        "error": None,
    }


def _happy_events():
    yield {"type": "progress", "phase": "extracting"}
    yield {
        "type": "claims",
        "claims": _engine_claims(),
        "unsupported_spans": ["Out-of-corpus span."],
    }
    yield {
        "type": "cite_verdict",
        "claim_index": 0,
        "case_verdict": _case_verdict(0, verdicts=_EXISTS_VERDICTS),
    }
    yield {
        "type": "cite_verdict",
        "claim_index": 1,
        "case_verdict": _case_verdict(1, verdicts=[]),
    }
    yield {"type": "result", "envelope": _final_envelope()}


class VerifyDraftStreamTests(unittest.TestCase):
    def _run(self, steps_factory):
        with mock.patch.object(
            verify_service.tutor_service,
            "grounded_tutor_envelope_steps",
            side_effect=lambda *a, **k: steps_factory(),
        ):
            return list(
                verify_service.verify_draft_stream(
                    conn=None,
                    draft=DRAFT,
                    log_study_event=lambda *a, **k: None,
                    fetch_recent_events=lambda *a, **k: [],
                )
            )

    def test_event_sequence(self) -> None:
        events = self._run(_happy_events)
        types = [e["type"] for e in events]
        self.assertEqual(["progress", "claims", "cite_verdict", "cite_verdict", "result"], types)

    def test_claims_event_precedes_every_cite_verdict(self) -> None:
        # The real sequencing guarantee verify_draft_stream owns: the claims
        # skeleton is emitted BEFORE any cite_verdict, so the UI can build its
        # cards first and resolve each cite axis only as its verdict lands. (The
        # "skeleton carries no resolved verdicts" guarantee is upstream, in
        # grounded_tutor_envelope_steps, which serializes claims before running
        # _attach_case_verdicts_steps; this function is a faithful relay of that
        # order, so we assert the order it must preserve, not a tautology.)
        events = self._run(_happy_events)
        types = [e["type"] for e in events]
        claims_idx = types.index("claims")
        cite_indices = [i for i, t in enumerate(types) if t == "cite_verdict"]
        self.assertTrue(cite_indices, "fixture must emit at least one cite_verdict")
        self.assertLess(claims_idx, min(cite_indices))
        self.assertLess(max(cite_indices), types.index("result"))

    def test_claims_skeleton_relays_engine_cards_faithfully(self) -> None:
        # verify_draft_stream is a pass-through re-shaper, not a stripper. It
        # relays exactly the cards the engine put in its claims event. Feed a
        # claims event whose first card ALREADY carries a (resolved) case_verdict
        # and assert it is relayed verbatim, so this test fails if the mapping
        # ever silently drops or mutates engine-supplied verdict data.
        def steps():
            yield {"type": "progress", "phase": "extracting"}
            yield {
                "type": "claims",
                "claims": [
                    {
                        "text": "Per 576 U.S. 644 the rule is X.",
                        "citations": [{"node_id": "c1"}],
                        "case_verdicts": [_case_verdict(0, verdicts=_EXISTS_VERDICTS)],
                    }
                ],
                "unsupported_spans": [],
            }
            yield {
                "type": "cite_verdict",
                "claim_index": 0,
                "case_verdict": _case_verdict(0, verdicts=_EXISTS_VERDICTS),
            }
            yield {"type": "result", "envelope": _final_envelope()}

        events = self._run(steps)
        claims_event = next(e for e in events if e["type"] == "claims")
        cards = claims_event["claim_verdicts"]
        self.assertEqual(1, len(cards))
        self.assertEqual("verified", cards[0]["verdict"])
        self.assertEqual(
            "Obergefell v. Hodges",
            cards[0]["case_verdicts"][0]["verdicts"][0]["case_name"],
        )

    def test_cite_verdict_passthrough(self) -> None:
        events = self._run(_happy_events)
        cv = [e for e in events if e["type"] == "cite_verdict"]
        self.assertEqual([0, 1], [e["claim_index"] for e in cv])
        self.assertTrue(cv[0]["case_verdict"]["verdicts"][0]["exists"])

    def test_final_result_matches_non_stream_mapping(self) -> None:
        events = self._run(_happy_events)
        result = events[-1]
        self.assertEqual("result", result["type"])
        verify = result["verify"]
        self.assertEqual(3, verify["summary"]["total"])
        self.assertEqual(1, verify["summary"]["verified"])
        self.assertEqual(2, verify["summary"]["unsupported"])
        # the verified claim card carries the attached case verdict
        self.assertEqual(
            "Obergefell v. Hodges",
            verify["claim_verdicts"][0]["case_verdicts"][0]["verdicts"][0]["case_name"],
        )
        # identical to the non-stream verify_draft mapping for the same envelope
        with mock.patch.object(
            verify_service.tutor_service,
            "grounded_tutor_envelope",
            return_value=_final_envelope(),
        ):
            non_stream = verify_service.verify_result_to_payload(
                verify_service.verify_draft(
                    conn=None,
                    draft=DRAFT,
                    log_study_event=lambda *a, **k: None,
                    fetch_recent_events=lambda *a, **k: [],
                )
            )
        # latency differs run-to-run; compare the stable verdict shape
        self.assertEqual(non_stream["claim_verdicts"], verify["claim_verdicts"])
        self.assertEqual(non_stream["summary"], verify["summary"])

    def test_empty_draft_single_result_event(self) -> None:
        events = list(
            verify_service.verify_draft_stream(
                conn=None,
                draft="   ",
                log_study_event=lambda *a, **k: None,
                fetch_recent_events=lambda *a, **k: [],
            )
        )
        self.assertEqual(1, len(events))
        self.assertEqual("result", events[0]["type"])
        self.assertFalse(events[0]["verify"]["ok"])
        self.assertEqual("empty_draft", events[0]["verify"]["error"])

    def test_dropped_stream_emits_no_result(self) -> None:
        # CRITICAL invariant #6: a stream that dies mid-flight must never emit
        # a result, so un-yielded claims are never reported as a pass.
        def dying_steps():
            yield {"type": "progress", "phase": "extracting"}
            yield {"type": "claims", "claims": _engine_claims(), "unsupported_spans": []}
            yield {
                "type": "cite_verdict",
                "claim_index": 0,
                "case_verdict": _case_verdict(0, verdicts=[]),
            }
            raise RuntimeError("courtlistener exploded mid-stream")

        collected = []
        with mock.patch.object(
            verify_service.tutor_service,
            "grounded_tutor_envelope_steps",
            side_effect=lambda *a, **k: dying_steps(),
        ):
            gen = verify_service.verify_draft_stream(
                conn=None,
                draft=DRAFT,
                log_study_event=lambda *a, **k: None,
                fetch_recent_events=lambda *a, **k: [],
            )
            with self.assertRaises(RuntimeError):
                for ev in gen:
                    collected.append(ev)

        types = [e["type"] for e in collected]
        self.assertEqual(["progress", "claims", "cite_verdict"], types)
        self.assertNotIn("result", types)
        # claim 1 never received a cite_verdict; its skeleton card stays empty,
        # so the client keeps it could_not_check rather than reading a pass.
        claims_event = next(e for e in collected if e["type"] == "claims")
        self.assertEqual([], claims_event["claim_verdicts"][1]["case_verdicts"])


class VerifyStreamRouteTests(unittest.TestCase):
    """The SSE endpoint frames events as ``data: {json}\\n\\n``, ends with
    ``data: [DONE]``, and surfaces errors as an error event (never a pass)."""

    def _post(self, steps_factory):
        from contextlib import contextmanager

        from fastapi.testclient import TestClient

        import main
        from services.local_api_security import HEADER_NAME, get_local_api_token

        @contextmanager
        def fake_db():
            yield None

        with mock.patch("routes.verify.db.get_db", fake_db):
            with mock.patch.object(
                verify_service.tutor_service,
                "grounded_tutor_envelope_steps",
                side_effect=lambda *a, **k: steps_factory(),
            ):
                client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})
                return client.post("/api/verify/stream", json={"draft": DRAFT})

    @staticmethod
    def _data_events(body: str):
        events = []
        for line in body.splitlines():
            if line.startswith("data:"):
                payload = line[len("data:") :].strip()
                if payload and payload != "[DONE]":
                    events.append(json.loads(payload))
        return events

    def test_stream_route_happy(self) -> None:
        response = self._post(_happy_events)
        self.assertEqual(200, response.status_code)
        self.assertIn("text/event-stream", response.headers["content-type"])
        body = response.text
        self.assertTrue(body.rstrip().endswith("data: [DONE]"))
        events = self._data_events(body)
        self.assertEqual("progress", events[0]["type"])
        self.assertEqual("result", events[-1]["type"])
        self.assertEqual(3, events[-1]["verify"]["summary"]["total"])

    def test_stream_route_surfaces_error_no_result(self) -> None:
        def dying_steps():
            yield {"type": "progress", "phase": "extracting"}
            raise RuntimeError("boom")

        response = self._post(dying_steps)
        self.assertEqual(200, response.status_code)
        body = response.text
        self.assertTrue(body.rstrip().endswith("data: [DONE]"))
        events = self._data_events(body)
        types = [e["type"] for e in events]
        self.assertIn("error", types)
        self.assertNotIn("result", types)


if __name__ == "__main__":
    unittest.main()
