"""Tests for the grounding seam itself (Cachet extraction P1).

The verify tests mock the seam (services.grounding.ground / ground_stream) to
pin verify's mapping, so they do NOT exercise the seam's forwarding. This file
closes that gap: it patches the engine UNDER the seam (services.grounding._tutor)
and pins the PURE INTERPOSITION contract, so a seam that dropped a kwarg,
reshaped or mutated the envelope, double-called the engine, invoked a callback
itself, swallowed an exception, eagerly drained the stream, or dropped a stream
event would FAIL here even though every verify test (which mocks the seam) would
still pass. See ADR-0011 P1 and docs/plans/cachet-extraction-2026-06-05.md.
"""

from __future__ import annotations

import unittest
from unittest import mock

from services import grounding


class GroundForwardingTests(unittest.TestCase):
    def test_ground_is_a_call_once_passthrough(self) -> None:
        envelope = {"claims": [{"text": "c"}], "provider": "claude", "error": None}
        expected = {"claims": [{"text": "c"}], "provider": "claude", "error": None}
        conn, payload = object(), object()
        lse = mock.Mock(name="log_study_event")
        fre = mock.Mock(name="fetch_recent_events")

        with mock.patch.object(
            grounding._tutor, "grounded_tutor_envelope", return_value=envelope
        ) as engine:
            result = grounding.ground(conn, payload, log_study_event=lse, fetch_recent_events=fre)

        # the engine is called exactly once, every argument forwarded verbatim
        engine.assert_called_once_with(conn, payload, log_study_event=lse, fetch_recent_events=fre)
        # the engine's object is returned unchanged: same identity AND same content
        # (the content check catches an in-place mutation that identity alone would miss)
        self.assertIs(envelope, result)
        self.assertEqual(expected, result)
        # the seam does not invoke the callbacks itself; it forwards them to the engine
        lse.assert_not_called()
        fre.assert_not_called()

    def test_ground_propagates_engine_exceptions(self) -> None:
        boom = RuntimeError("engine failed")
        with mock.patch.object(grounding._tutor, "grounded_tutor_envelope", side_effect=boom):
            with self.assertRaises(RuntimeError) as ctx:
                grounding.ground(
                    object(),
                    object(),
                    log_study_event=lambda *a, **k: None,
                    fetch_recent_events=lambda *a, **k: [],
                )
        self.assertIs(boom, ctx.exception)


class GroundStreamForwardingTests(unittest.TestCase):
    @staticmethod
    def _events():
        return [
            {"type": "progress", "phase": "extracting"},
            {"type": "claims", "claims": [{"text": "c"}], "unsupported_spans": []},
            {"type": "result", "envelope": {"claims": [], "error": None}},
        ]

    def test_ground_stream_relays_every_event_in_order_unchanged(self) -> None:
        events = self._events()
        expected = self._events()
        conn, payload = object(), object()
        lse = mock.Mock(name="log_study_event")
        fre = mock.Mock(name="fetch_recent_events")
        engine = mock.Mock(return_value=iter(events))

        with mock.patch.object(grounding._tutor, "grounded_tutor_envelope_steps", engine):
            relayed = list(
                grounding.ground_stream(conn, payload, log_study_event=lse, fetch_recent_events=fre)
            )

        engine.assert_called_once_with(conn, payload, log_study_event=lse, fetch_recent_events=fre)
        # every event relayed, in order, same objects and same content (no drop or reshape)
        self.assertEqual(len(expected), len(relayed))
        self.assertEqual(expected, relayed)
        for got, original in zip(relayed, events):
            self.assertIs(got, original)
        lse.assert_not_called()
        fre.assert_not_called()

    def test_ground_stream_is_lazy_not_eagerly_drained(self) -> None:
        started = []

        def engine_steps(*a, **k):
            started.append("body-entered")
            yield {"type": "progress"}
            yield {"type": "result"}

        with mock.patch.object(
            grounding._tutor, "grounded_tutor_envelope_steps", side_effect=engine_steps
        ):
            stream = grounding.ground_stream(
                object(),
                object(),
                log_study_event=lambda *a, **k: None,
                fetch_recent_events=lambda *a, **k: [],
            )
            # the seam returned a lazy stream: the engine generator body has not run yet
            self.assertEqual([], started)
            iterator = iter(stream)
            first = next(iterator)
            self.assertEqual("progress", first["type"])
            self.assertEqual(["body-entered"], started)

    def test_ground_stream_propagates_engine_exceptions_mid_stream(self) -> None:
        def dying_steps(*a, **k):
            yield {"type": "progress"}
            raise RuntimeError("engine exploded mid-stream")

        with mock.patch.object(
            grounding._tutor, "grounded_tutor_envelope_steps", side_effect=dying_steps
        ):
            stream = grounding.ground_stream(
                object(),
                object(),
                log_study_event=lambda *a, **k: None,
                fetch_recent_events=lambda *a, **k: [],
            )
            collected = []
            with self.assertRaises(RuntimeError):
                for event in stream:
                    collected.append(event)
        # the events before the failure were relayed; no swallowing
        self.assertEqual([{"type": "progress"}], collected)


if __name__ == "__main__":
    unittest.main()
