"""Best-time-to-study insertion engine.

The user's question: "I have an exam Friday and a paper due next
Wednesday. When should I actually sit down and study?"

This module answers it. Given:
  - The user's calendar (free vs busy intervals from local + remote feeds)
  - Detected deadlines (calendar events + overdue SRS aggregate)
  - A constant "good times to study" prior (afternoon > evening > morning > night)

…produce a ranked list of suggested study sessions with:
  - When (start_at, end_at)
  - Why (which deadline it's anchored to, or "no deadline — review block")
  - How urgent (score in [0, 1])

The score combines three factors:

  urgency_factor = 1 / (days_until_deadline + 1)
    Sigmoid-ish: a deadline 3 days away is much more urgent than 30
    days. Bounded so deadlines further than the lookahead still
    contribute non-zero.

  fit_factor = a Gaussian-ish bump centred on local 3 PM
    Real students study best in the afternoon. We can't know each
    user's chronotype without preferences UI, so the prior is fixed
    until we have data to fit a curve. Overnight blocks (1–6 AM)
    score near zero so the coach never suggests "study at 4 AM."

  size_factor = sigmoid(block_minutes / 60)
    A 30 min block is okay, 60+ is great, beyond 90 there's no
    benefit (the user will plateau).

Final score = urgency_factor * fit_factor * size_factor, then
normalized to [0, 1] across the candidate set.

Phase 3 hooks not implemented yet:
  - Per-user chronotype learning from session.start_at history
  - Avoid stacking study blocks back-to-back across days the user
    declined yesterday's suggestion
  - Cross-deadline coordination ("you have two exams; spread prep")
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from services.planning.deadlines import Deadline, detect_upcoming_deadlines

# Insertion engine looks 14 days ahead by default. Tighter than
# the deadline horizon (30d) because suggestions further than two
# weeks have low signal — calendar churn invalidates them anyway.
INSERTION_LOOKAHEAD_DAYS = 14

# Min block size we'll suggest. Below 30 minutes the context-switch
# cost dominates; the user opens the app, doesn't reach flow,
# session ends. 30 is the floor.
MIN_BLOCK_MINUTES = 30

# Default suggested session duration. We propose this within a free
# block — even a 4-hour gap should yield a 60-min session, not a
# 4-hour one.
DEFAULT_SESSION_MINUTES = 60

# Max number of insertions we surface per refresh. The dashboard
# can render 3 cards comfortably; more becomes noise.
MAX_INSERTIONS = 3


@dataclass
class FreeBlock:
    start_at: str
    end_at: str
    minutes: int


@dataclass
class StudySessionInsertion:
    """One suggestion, ranked. The dashboard renders these as cards."""
    start_at: str            # ISO 8601 UTC — where to put the session
    end_at: str
    duration_minutes: int
    score: float             # 0..1, higher = better
    reason_text: str         # "Bio midterm in 2 days. 60-min gap at 3 PM."
    reason_code: str         # 'deadline_imminent' | 'free_block_overdue_srs' | 'free_block'
    deadline_label: str | None
    deadline_at: str | None
    source_event_id: str | None


def best_study_session_insertions(
    conn: sqlite3.Connection,
    *,
    user_id: str = "local",
    now: datetime | None = None,
    user_timezone: str = "UTC",
    max_results: int = MAX_INSERTIONS,
) -> list[StudySessionInsertion]:
    """Rank the best K times to insert a study session.

    `user_timezone` controls the time-of-day fit calculation — 3 PM
    feels great in the user's local TZ, not UTC. Default UTC keeps
    the scoring deterministic for tests.
    """
    now = now or datetime.now(UTC)
    horizon = now + timedelta(days=INSERTION_LOOKAHEAD_DAYS)

    free_blocks = _find_free_blocks(
        conn, user_id=user_id,
        window_start=now, window_end=horizon,
        min_minutes=MIN_BLOCK_MINUTES,
    )
    if not free_blocks:
        return []

    deadlines = detect_upcoming_deadlines(conn, user_id=user_id, now=now)
    tz = _resolve_timezone(user_timezone)

    candidates: list[StudySessionInsertion] = []
    for block in free_blocks:
        # Trim each free block to a session-sized window starting at
        # the block's start. Anchoring to the start (vs middle) keeps
        # suggestions on natural hour boundaries (events end on the
        # hour, so the first session starts on the hour).
        session_minutes = min(DEFAULT_SESSION_MINUTES, block.minutes)
        if session_minutes < MIN_BLOCK_MINUTES:
            continue
        end_at = _iso_add_minutes(block.start_at, session_minutes)

        anchored = _best_deadline_for_block(block.start_at, deadlines, now=now)
        urgency = _urgency_factor(anchored, now=now)
        fit = _time_of_day_fit(block.start_at, tz=tz)
        size = _size_factor(session_minutes)
        raw_score = urgency * fit * size

        candidates.append(
            StudySessionInsertion(
                start_at=block.start_at,
                end_at=end_at,
                duration_minutes=session_minutes,
                score=raw_score,
                reason_text=_compose_reason(anchored, session_minutes, block.start_at, tz),
                reason_code=_reason_code(anchored),
                deadline_label=anchored.label if anchored else None,
                deadline_at=anchored.deadline_at if anchored else None,
                source_event_id=anchored.event_id if anchored else None,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    top = candidates[:max_results]

    # Normalize scores so the top suggestion is 1.0. Easier to render
    # a confidence bar / radial when scores are bounded.
    if top:
        max_score = top[0].score or 1.0
        for c in top:
            c.score = round(c.score / max_score, 4) if max_score > 0 else 0.0
    return top


# ---------------------------------------------------------------------
# Scoring components
# ---------------------------------------------------------------------

def _urgency_factor(deadline: Deadline | None, *, now: datetime) -> float:
    """Higher when a deadline is closer; floor 0.2 so non-deadline
    suggestions still surface (the user has free time + maybe overdue
    cards is a perfectly good reason on its own).
    """
    if deadline is None:
        return 0.2
    if deadline.source == "srs_overdue":
        # Overdue is "today"; treat as moderately urgent always.
        return 0.7 if deadline.severity == "high" else 0.5
    days = max(0.0, deadline.days_until)
    factor = 1.0 / (days + 1.0)
    # Severity bumps from the deadline detector: high=midterm in <3d
    if deadline.severity == "high":
        factor = min(1.0, factor * 1.4)
    elif deadline.severity == "low":
        factor *= 0.7
    return max(0.2, min(1.0, factor))


def _time_of_day_fit(iso_at: str, *, tz: ZoneInfo) -> float:
    """Gaussian centred on 15:00 local with sigma 4h. Output in [0, 1]."""
    dt = _parse_iso(iso_at).astimezone(tz)
    hour = dt.hour + dt.minute / 60.0
    centre = 15.0
    sigma = 4.0
    score = math.exp(-((hour - centre) ** 2) / (2 * sigma * sigma))
    # Floor near-zero hours so 4 AM still gets ~0 (don't propose).
    return max(0.05, score)


def _size_factor(minutes: int) -> float:
    """Sigmoid: 30 min ~= 0.27, 60 min ~= 0.50, 90 min ~= 0.73, 120 ~= 0.88."""
    return 1.0 / (1.0 + math.exp(-(minutes - 60) / 20.0))


# ---------------------------------------------------------------------
# Free-block discovery (UTC-clean, all-day events excluded)
# ---------------------------------------------------------------------

def _find_free_blocks(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    window_start: datetime,
    window_end: datetime,
    min_minutes: int,
) -> list[FreeBlock]:
    start_iso = window_start.isoformat().replace("+00:00", "Z")
    end_iso = window_end.isoformat().replace("+00:00", "Z")
    rows = conn.execute(
        """
        SELECT start_at, end_at FROM calendar_events
        WHERE user_id = ?
          AND status != 'cancelled'
          AND all_day = 0
          AND start_at < ?
          AND end_at > ?
        ORDER BY start_at ASC
        """,
        (user_id, end_iso, start_iso),
    ).fetchall()

    busy: list[tuple[datetime, datetime]] = []
    for r in rows:
        try:
            s = _parse_iso(r["start_at"])
            e = _parse_iso(r["end_at"])
        except ValueError:
            continue
        s = max(s, window_start)
        e = min(e, window_end)
        if e > s:
            busy.append((s, e))
    busy.sort()

    merged: list[tuple[datetime, datetime]] = []
    for s, e in busy:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    free: list[FreeBlock] = []
    cursor = window_start
    for s, e in merged:
        if s > cursor:
            minutes = int((s - cursor).total_seconds() // 60)
            if minutes >= min_minutes:
                free.append(FreeBlock(
                    start_at=cursor.isoformat().replace("+00:00", "Z"),
                    end_at=s.isoformat().replace("+00:00", "Z"),
                    minutes=minutes,
                ))
        cursor = max(cursor, e)
    if cursor < window_end:
        minutes = int((window_end - cursor).total_seconds() // 60)
        if minutes >= min_minutes:
            free.append(FreeBlock(
                start_at=cursor.isoformat().replace("+00:00", "Z"),
                end_at=window_end.isoformat().replace("+00:00", "Z"),
                minutes=minutes,
            ))
    return free


# ---------------------------------------------------------------------
# Deadline anchoring
# ---------------------------------------------------------------------

def _best_deadline_for_block(
    block_start_iso: str, deadlines: list[Deadline], *, now: datetime,
) -> Deadline | None:
    """Pick the deadline this block should be anchored to.

    Rule: prefer the soonest deadline that's after the block. If
    nothing's after the block (block is past the last deadline) and
    there's overdue SRS, anchor to that. Otherwise None.
    """
    block_dt = _parse_iso(block_start_iso)
    upcoming = [
        d for d in deadlines
        if d.source == "calendar_event" and _parse_iso(d.deadline_at) > block_dt
    ]
    if upcoming:
        upcoming.sort(key=lambda d: d.deadline_at)
        return upcoming[0]
    overdue = next((d for d in deadlines if d.source == "srs_overdue"), None)
    return overdue


def _compose_reason(
    deadline: Deadline | None, minutes: int, block_start_iso: str, tz: ZoneInfo,
) -> str:
    """User-facing one-liner. Voice rules: no jargon, no exclamation,
    name the deadline if there is one, name the slot if not.
    """
    local_dt = _parse_iso(block_start_iso).astimezone(tz)
    when = local_dt.strftime("%a %b %-d, %-I:%M %p")
    if deadline is None:
        return f"{minutes}-min open block at {when}."
    if deadline.source == "srs_overdue":
        return f"{deadline.label}. {minutes}-min slot at {when}."
    days = max(0, int(round(deadline.days_until)))
    when_clause = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
    return f"{deadline.label} {when_clause}. {minutes}-min slot at {when}."


def _reason_code(deadline: Deadline | None) -> str:
    if deadline is None:
        return "free_block"
    if deadline.source == "srs_overdue":
        return "free_block_overdue_srs"
    return "deadline_imminent"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _resolve_timezone(name: str) -> ZoneInfo:
    """Fall through to UTC on unknown TZ — never crash on a typo from
    the frontend. The fit calculation just becomes UTC-relative which
    is wrong but not broken.
    """
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _iso_add_minutes(iso: str, minutes: int) -> str:
    dt = _parse_iso(iso) + timedelta(minutes=minutes)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
