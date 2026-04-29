"""Tests for services/calendar/ical_parser.py.

Synthetic ICS fixtures cover the four shapes the parser MUST get right:
  - simple timed event
  - all-day event (DTSTART;VALUE=DATE)
  - RRULE with EXDATE (recurrence + exception removal)
  - RECURRENCE-ID (single-occurrence override of a recurring series)

Parsing real-world feeds is left to integration testing; these unit
tests pin the per-occurrence shape so we don't regress the
expansion + dedup logic.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.calendar.ical_parser import parse_ics


def _ics(body: str) -> bytes:
    """Wrap a VEVENT body in the minimum VCALENDAR envelope."""
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//einstein-test//\r\n"
        f"{body}\r\n"
        "END:VCALENDAR\r\n"
    ).encode("utf-8")


# Anchor "now" so tests are deterministic regardless of when run.
NOW = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)


class ParseSimpleTests(unittest.TestCase):
    def test_one_timed_event(self) -> None:
        ics = _ics(
            "BEGIN:VEVENT\r\n"
            "UID:simple-1@example\r\n"
            "DTSTART:20260430T140000Z\r\n"
            "DTEND:20260430T150000Z\r\n"
            "SUMMARY:Corporate Finance Lecture\r\n"
            "LOCATION:Room 401\r\n"
            "END:VEVENT"
        )
        events = parse_ics(ics, now=NOW)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.uid, "simple-1@example")
        self.assertEqual(ev.summary, "Corporate Finance Lecture")
        self.assertEqual(ev.location, "Room 401")
        self.assertFalse(ev.all_day)
        self.assertEqual(ev.status, "confirmed")
        self.assertTrue(ev.start_at.endswith("Z"))
        self.assertTrue(ev.end_at.endswith("Z"))

    def test_all_day_event(self) -> None:
        ics = _ics(
            "BEGIN:VEVENT\r\n"
            "UID:allday-1@example\r\n"
            "DTSTART;VALUE=DATE:20260501\r\n"
            "DTEND;VALUE=DATE:20260502\r\n"
            "SUMMARY:Public Holiday\r\n"
            "END:VEVENT"
        )
        events = parse_ics(ics, now=NOW)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].all_day)


class ParseRecurrenceTests(unittest.TestCase):
    def test_rrule_with_exdate_drops_the_exception(self) -> None:
        ics = _ics(
            "BEGIN:VEVENT\r\n"
            "UID:weekly-1@example\r\n"
            "DTSTART:20260430T140000Z\r\n"
            "DTEND:20260430T150000Z\r\n"
            "RRULE:FREQ=WEEKLY;COUNT=3\r\n"
            "EXDATE:20260507T140000Z\r\n"
            "SUMMARY:Weekly Class\r\n"
            "END:VEVENT"
        )
        events = parse_ics(ics, now=NOW)
        # COUNT=3 minus one EXDATE = 2 occurrences in the window.
        self.assertEqual(len(events), 2)
        # Each occurrence has a distinct occurrence_key.
        keys = {ev.occurrence_key for ev in events}
        self.assertEqual(len(keys), 2)
        # All share the same UID.
        self.assertEqual({ev.uid for ev in events}, {"weekly-1@example"})

    def test_recurrence_id_override(self) -> None:
        # Master + override: master defines the series, override
        # changes the summary on one occurrence.
        ics = _ics(
            "BEGIN:VEVENT\r\n"
            "UID:weekly-2@example\r\n"
            "DTSTART:20260430T140000Z\r\n"
            "DTEND:20260430T150000Z\r\n"
            "RRULE:FREQ=WEEKLY;COUNT=3\r\n"
            "SUMMARY:Weekly Class\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:weekly-2@example\r\n"
            "RECURRENCE-ID:20260507T140000Z\r\n"
            "DTSTART:20260507T160000Z\r\n"
            "DTEND:20260507T170000Z\r\n"
            "SUMMARY:Weekly Class (rescheduled)\r\n"
            "END:VEVENT"
        )
        events = parse_ics(ics, now=NOW)
        self.assertEqual(len(events), 3)
        rescheduled = [e for e in events if "rescheduled" in e.summary]
        self.assertEqual(len(rescheduled), 1)


class ParseStatusTests(unittest.TestCase):
    def test_cancelled_status_preserved(self) -> None:
        ics = _ics(
            "BEGIN:VEVENT\r\n"
            "UID:x-1@example\r\n"
            "DTSTART:20260430T140000Z\r\n"
            "DTEND:20260430T150000Z\r\n"
            "SUMMARY:Cancelled\r\n"
            "STATUS:CANCELLED\r\n"
            "END:VEVENT"
        )
        events = parse_ics(ics, now=NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, "cancelled")

    def test_tentative_status_preserved(self) -> None:
        ics = _ics(
            "BEGIN:VEVENT\r\n"
            "UID:t-1@example\r\n"
            "DTSTART:20260430T140000Z\r\n"
            "DTEND:20260430T150000Z\r\n"
            "SUMMARY:Maybe\r\n"
            "STATUS:TENTATIVE\r\n"
            "END:VEVENT"
        )
        events = parse_ics(ics, now=NOW)
        self.assertEqual(events[0].status, "tentative")


class ParseSafetyTests(unittest.TestCase):
    def test_skips_malformed_event_keeps_others(self) -> None:
        # First event is missing DTSTART (required); second is fine.
        ics = _ics(
            "BEGIN:VEVENT\r\n"
            "UID:bad@example\r\n"
            "SUMMARY:No DTSTART\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:good@example\r\n"
            "DTSTART:20260430T140000Z\r\n"
            "DTEND:20260430T150000Z\r\n"
            "SUMMARY:Has DTSTART\r\n"
            "END:VEVENT"
        )
        events = parse_ics(ics, now=NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].uid, "good@example")


if __name__ == "__main__":
    unittest.main()
