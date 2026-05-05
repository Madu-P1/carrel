"""Deadline detection for the coach.

Carrel has two natural sources of study deadlines:

  1. Calendar events whose summary matches an exam-style keyword
     (midterm, exam, test, quiz, presentation, paper, due, deadline).
     The event's start_at is the deadline; we treat it as a hard
     "be-prepared-by" boundary the coach should plan around.

  2. SRS cards whose due_date is on or before today. These don't
     have a single deadline; they aggregate into "the user has N
     cards overdue, urgency rises with N." A high count is itself
     a deadline.

Both sources feed into `services/planning/insertion.py::best_study_session_insertions`
which ranks free blocks by a combination of urgency-to-deadline,
time-of-day fit, and block size.

Deliberately not in scope:
  - LLM extraction of deadlines from document content (slow, costly,
    hard to cite).
  - Recurring-class-pattern detection ("every Tuesday at 10 AM is
    Calc 101"). The user can already filter the WeekTimeGrid by feed
    color; the coach doesn't need to second-guess that.
  - Cross-doc "synthesis is due in 3 days" since synthesis isn't
    deadline-tracked today.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Match exam-style keywords as whole words. The list is deliberately
# small — broader matches like "review" would treat every study
# session the user already scheduled as a deadline event and create
# suggestion loops. These six are what real students put on their
# calendar with date-fixed urgency.
DEADLINE_KEYWORDS = re.compile(
    r"\b(midterm|exam|final|test|quiz|deadline)\b",
    re.IGNORECASE,
)

# Match user-self-scheduled study blocks. These are explicitly NOT
# deadlines — they're allocated prep time. The insertion engine uses
# them to discount urgency for deadlines the user has already prepared
# for, so we don't pile suggestions on top of a packed prep schedule.
#
# `study` matches "study", "studying", "study block", "study Bio", etc.
# `revision`/`revise` covers the British-English equivalent students
# often use ("Revise calculus").
STUDY_ALLOCATION_KEYWORDS = re.compile(
    r"\b(study|studying|revision|revise)\b",
    re.IGNORECASE,
)

# How far ahead we look for deadlines. 30 days is the right scale for
# a semester — past that, recommendations are guesses; before that,
# real prep work pays off.
DEADLINE_LOOKAHEAD_DAYS = 30


@dataclass
class Deadline:
    """A detected study-relevant date.

    `event_id` is None for aggregate sources (SRS overdue count); it
    points at a `calendar_events.id` for event-driven deadlines so the
    UI can deep-link.
    """
    label: str                  # "Bio midterm", "12 cards overdue"
    deadline_at: str            # ISO 8601 UTC
    days_until: float           # may be negative for past-due aggregates
    source: str                 # "calendar_event" | "srs_overdue"
    event_id: str | None = None
    severity: str = "normal"    # "low" | "normal" | "high"


def detect_upcoming_deadlines(
    conn: sqlite3.Connection, *, user_id: str = "local",
    now: datetime | None = None,
) -> list[Deadline]:
    """Pull every signal-bearing deadline within the next N days.

    Sorted by deadline_at ascending so the soonest is first. Ties go
    to higher-severity items so a "midterm tomorrow" beats a "12
    cards overdue" when both share a date.
    """
    now = now or datetime.now(UTC)
    horizon = now + timedelta(days=DEADLINE_LOOKAHEAD_DAYS)

    deadlines: list[Deadline] = []
    deadlines.extend(_calendar_event_deadlines(conn, user_id=user_id, now=now, horizon=horizon))
    overdue_aggregate = _srs_overdue_aggregate(conn, now=now)
    if overdue_aggregate is not None:
        deadlines.append(overdue_aggregate)

    deadlines.sort(
        key=lambda d: (d.deadline_at, _severity_rank(d.severity)),
    )
    return deadlines


def _severity_rank(severity: str) -> int:
    return {"high": 0, "normal": 1, "low": 2}.get(severity, 1)


def _calendar_event_deadlines(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    now: datetime,
    horizon: datetime,
) -> list[Deadline]:
    start_iso = now.isoformat().replace("+00:00", "Z")
    end_iso = horizon.isoformat().replace("+00:00", "Z")
    rows = conn.execute(
        """
        SELECT id, summary, start_at FROM calendar_events
        WHERE user_id = ?
          AND status != 'cancelled'
          AND start_at >= ?
          AND start_at <= ?
        ORDER BY start_at ASC
        """,
        (user_id, start_iso, end_iso),
    ).fetchall()

    out: list[Deadline] = []
    for row in rows:
        summary = (row["summary"] or "").strip()
        if not DEADLINE_KEYWORDS.search(summary):
            continue
        try:
            deadline_dt = _parse_iso(row["start_at"])
        except ValueError:
            continue
        days_until = max(0.0, (deadline_dt - now).total_seconds() / 86400)
        # < 3 days = high (cramming territory); 3-7 = normal; >7 = low
        if days_until <= 3:
            severity = "high"
        elif days_until <= 7:
            severity = "normal"
        else:
            severity = "low"
        out.append(
            Deadline(
                label=summary[:120],
                deadline_at=row["start_at"],
                days_until=days_until,
                source="calendar_event",
                event_id=row["id"],
                severity=severity,
            )
        )
    return out


def _srs_overdue_aggregate(
    conn: sqlite3.Connection, *, now: datetime
) -> Deadline | None:
    """Aggregate the user's overdue SRS pile into one deadline-shaped
    record. The "deadline" is today (now) since each card is already
    past-due; severity scales with count.
    """
    today_iso = now.date().isoformat()
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM srs_cards
        WHERE due_date IS NOT NULL AND due_date <= ?
        """,
        (today_iso,),
    ).fetchone()
    overdue = int(row["n"]) if row else 0
    if overdue == 0:
        return None
    # Severity bands tuned for student-scale workloads. >50 cards is
    # a "you've been away for 2+ weeks" backlog and deserves "high"
    # urgency; 5-50 is the normal weekly drift.
    if overdue >= 50:
        severity = "high"
    elif overdue >= 5:
        severity = "normal"
    else:
        severity = "low"
    return Deadline(
        label=f"{overdue} card{'s' if overdue != 1 else ''} overdue",
        deadline_at=now.isoformat().replace("+00:00", "Z"),
        days_until=0.0,
        source="srs_overdue",
        event_id=None,
        severity=severity,
    )


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
