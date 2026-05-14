"""Study-coach suggestion synthesis.

V1 (Phase 1, this file): one rule, end-to-end.
  Rule "free_block_overdue_srs": if there's a free block ≥ 60 minutes
  in the next 24 hours AND there's at least one overdue SRS card,
  emit one suggestion. Render as a `study_block` in the user's day.

  Reason text: "60-min gap and N cards overdue."

  Score: 1.0 (single rule means no ranking needed yet; preserved for
  Phase 2's multi-rule pipeline).

Phase 2 hooks (sketched, intentionally NOT implemented):
  Rule "deadline_imminent": parse event summaries with the existing
  Library subject taxonomy to detect "X midterm" / "Y exam" patterns,
  back-solve from due_at, propose a 3-session study plan anchored in
  the matching subject's strongest weak concept.

  Rule "low_recent_review": detect subjects where SRS hasn't been
  practiced in N days; suggest a short refresh block.

  Rule "gap_between_classes": when two events are <2h apart and the
  user is on campus (location overlap), suggest a tight focused
  micro-session.

Each future rule is a function that takes the same `CoachInputs`
dataclass and returns a list of candidate suggestions; `synthesize`
will rank them via `score()` once we have multiple. The reason_code
CHECK constraint in schema.sql already lists all four codes so
adding the new rules in Phase 2 is a code-only change, no migration.

Why this layering matters: the v1 rule is 30 lines. Putting all four
rules together in this file keeps "what does the coach actually do"
discoverable, and the scoring function gets to compare across rules
without cross-file imports. Resist the urge to split prematurely.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app_logging import get_logger
from services.calendar import repository


LOGGER = get_logger("planning.coach")


# Free-block threshold for the v1 rule. Anything shorter than this
# isn't worth the context-switch cost for a study session.
MIN_FREE_BLOCK_MINUTES = 60

# Look-ahead window for the v1 rule. Suggestions for "study Wednesday"
# made on Friday lose the user's trust; cap at 24h ahead.
LOOKAHEAD_HOURS = 24

# Coach Phase 2 first holistic loop: rebalance_on_miss.
# Threshold above which the user is treated as "falling behind." Below
# this, the routine free_block_overdue_srs rule is enough and surfacing
# a rebalance suggestion would feel like nagging.
CATCHUP_OVERDUE_THRESHOLD = 5

# Catchup blocks are longer than routine review blocks. A user behind
# on 10+ cards needs depth, not another 60-min nudge.
CATCHUP_BLOCK_MINUTES = 90

# Base score for rebalance suggestions. Sits comfortably above
# free_block_overdue_srs (1.0) so when both fire the rebalance ranks
# first. Scaling factor below adds up to +1.0 based on backlog size.
REBALANCE_BASE_SCORE = 2.5
REBALANCE_BACKLOG_DIVISOR = 10.0


@dataclass
class CandidateSuggestion:
    """Pre-persistence shape — what each rule emits.

    Once `synthesize` decides which to keep, these get persisted via
    `repository.insert_suggestion`.
    """

    kind: str  # 'study_block' | 'review_block' | 'catchup'
    start_at: str  # ISO 8601 UTC
    end_at: str  # ISO 8601 UTC
    reason_code: str  # must match schema CHECK
    reason_text: str  # user-facing, follows Ship 7 voice rules
    score: float  # higher = more important
    due_at: Optional[str] = None
    doc_id: Optional[str] = None
    source_event_id: Optional[str] = None


@dataclass
class FreeBlock:
    """A gap in the user's schedule, in UTC ISO 8601."""

    start_at: str
    end_at: str
    minutes: int


def synthesize_suggestions(
    conn: sqlite3.Connection, *, user_id: str = "local"
) -> List[CandidateSuggestion]:
    """Run all enabled rules against the current state and return
    candidates ordered by score (highest first).

    Phase 1 ships only `_rule_free_block_overdue_srs`. The four-rule
    list is intentionally written this way so Phase 2's additions are
    a one-line change here, not a refactor.
    """
    rules = [
        _rule_free_block_overdue_srs,
        _rule_rebalance_on_miss,
        # Phase 2 plug points still pending:
        # _rule_deadline_imminent,
        # _rule_low_recent_review,
        # _rule_gap_between_classes,
    ]
    candidates: List[CandidateSuggestion] = []
    for rule in rules:
        try:
            candidates.extend(rule(conn, user_id=user_id))
        except Exception as exc:
            # A misbehaving rule should not blank the whole panel.
            LOGGER.warning(
                "Coach rule %s raised %s; skipping",
                rule.__name__,
                exc.__class__.__name__,
            )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def refresh_active_suggestions(
    conn: sqlite3.Connection, *, user_id: str = "local"
) -> List[repository.SuggestionRow]:
    """Idempotent refresh of the user's active suggestion set.

    Called from GET /api/plan after expiring past-due pending ones.
    Strategy: keep already-pending suggestions (so an open dialog or a
    suggestion the user is mid-decision on doesn't disappear under
    them), and only insert new ones whose (kind, start_at) tuple
    isn't already represented in the pending set. Past-start_at
    pending suggestions are expired by the caller before this runs.
    """
    repository.expire_past_pending_suggestions(conn, user_id=user_id)

    existing = repository.list_active_suggestions(conn, user_id=user_id)
    existing_keys = {(s.kind, s.start_at) for s in existing}

    candidates = synthesize_suggestions(conn, user_id=user_id)
    for candidate in candidates:
        key = (candidate.kind, candidate.start_at)
        if key in existing_keys:
            continue
        repository.insert_suggestion(
            conn,
            kind=candidate.kind,
            start_at=candidate.start_at,
            end_at=candidate.end_at,
            reason_code=candidate.reason_code,
            reason_text=candidate.reason_text,
            due_at=candidate.due_at,
            doc_id=candidate.doc_id,
            source_event_id=candidate.source_event_id,
            score=candidate.score,
            user_id=user_id,
        )

    return repository.list_active_suggestions(conn, user_id=user_id)


# ---------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------


def _rule_free_block_overdue_srs(
    conn: sqlite3.Connection, *, user_id: str
) -> List[CandidateSuggestion]:
    """V1 stub. One suggestion if both conditions hold:
      - At least one overdue SRS card
      - At least one free block ≥ 60 min in the next 24h

    Picks the FIRST qualifying free block (chronologically nearest)
    so the user sees "study tonight" not "study tomorrow afternoon"
    when both are options. Phase 2's deadline-aware rule will own the
    "what's the BEST time" question; v1 keeps it simple.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=LOOKAHEAD_HOURS)

    overdue = _count_overdue_srs(conn)
    if overdue == 0:
        return []

    free_blocks = _find_free_blocks(
        conn,
        window_start=now,
        window_end=horizon,
        min_minutes=MIN_FREE_BLOCK_MINUTES,
        user_id=user_id,
    )
    if not free_blocks:
        return []

    # Cap suggested duration at 60 min — short, tractable session, not
    # the whole free block. If the user wants more they can extend.
    block = free_blocks[0]
    suggested_end = _iso_add_minutes(block.start_at, MIN_FREE_BLOCK_MINUTES)

    return [
        CandidateSuggestion(
            kind="review_block",
            start_at=block.start_at,
            end_at=suggested_end,
            reason_code="free_block_overdue_srs",
            reason_text=(
                f"{MIN_FREE_BLOCK_MINUTES}-min gap and "
                f"{overdue} card{'s' if overdue != 1 else ''} overdue."
            ),
            score=1.0,
        )
    ]


def _rule_rebalance_on_miss(
    conn: sqlite3.Connection, *, user_id: str
) -> List[CandidateSuggestion]:
    """Coach Phase 2, first holistic loop.

    Senses a study-state signal (overdue SRS count beyond a "falling
    behind" threshold), reasons about available capacity in the next
    24h, acts by surfacing an urgent catchup block longer than the
    routine review_block suggestion.

    Below CATCHUP_OVERDUE_THRESHOLD cards overdue, _rule_free_block_overdue_srs
    handles it. Above, this rule overrides with a catchup-kind suggestion
    that scores comfortably above the routine rule so it ranks first
    when both fire.

    Score: REBALANCE_BASE_SCORE plus a backlog factor up to +1.0 so
    deeper backlogs surface more urgently within rebalance suggestions
    themselves. The factor is capped so a runaway backlog can't dominate
    other rules (deadline_imminent, when shipped, will outrank both).
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=LOOKAHEAD_HOURS)

    overdue = _count_overdue_srs(conn)
    if overdue <= CATCHUP_OVERDUE_THRESHOLD:
        return []

    free_blocks = _find_free_blocks(
        conn,
        window_start=now,
        window_end=horizon,
        min_minutes=CATCHUP_BLOCK_MINUTES,
        user_id=user_id,
    )
    if not free_blocks:
        return []

    block = free_blocks[0]
    suggested_end = _iso_add_minutes(block.start_at, CATCHUP_BLOCK_MINUTES)

    backlog_factor = min(
        (overdue - CATCHUP_OVERDUE_THRESHOLD) / REBALANCE_BACKLOG_DIVISOR,
        1.0,
    )
    score = REBALANCE_BASE_SCORE + backlog_factor

    return [
        CandidateSuggestion(
            kind="catchup",
            start_at=block.start_at,
            end_at=suggested_end,
            reason_code="rebalance_on_miss",
            reason_text=(
                f"{overdue} cards overdue. "
                f"Block {CATCHUP_BLOCK_MINUTES} minutes today to catch up."
            ),
            score=score,
        )
    ]


def _count_overdue_srs(conn: sqlite3.Connection) -> int:
    """Number of cards whose due_date is on or before today.

    Mirrors `services/study.py::fetch_due_cards` predicates. We only
    need the count for the v1 rule; the rule emits a `review_block`
    suggestion that takes the user into the existing /study flow.
    """
    today_iso = datetime.now(timezone.utc).date().isoformat()
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM srs_cards
        WHERE due_date IS NULL OR due_date <= ?
        """,
        (today_iso,),
    ).fetchone()
    return int(row["n"]) if row else 0


def _find_free_blocks(
    conn: sqlite3.Connection,
    *,
    window_start: datetime,
    window_end: datetime,
    min_minutes: int,
    user_id: str,
) -> List[FreeBlock]:
    """Compute free intervals ≥ min_minutes inside [window_start, window_end).

    "Free" = not overlapped by any non-cancelled, non-all-day calendar
    event. All-day events (lectures spanning the whole day, holidays
    marked as full-day) ARE excluded from free-time calculation — they
    don't actually block the user from doing focused work, just clutter
    the day-grid. Phase 2 may revisit this when we know more about how
    users mark "busy."
    """
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

    # Merge overlapping events into busy intervals, then invert against
    # the window to get free intervals.
    busy: List[tuple[datetime, datetime]] = []
    for r in rows:
        try:
            s = _parse_iso(r["start_at"])
            e = _parse_iso(r["end_at"])
        except ValueError:
            continue
        # Clip to window
        if e <= window_start:
            continue
        if s >= window_end:
            continue
        s = max(s, window_start)
        e = min(e, window_end)
        if e <= s:
            continue
        busy.append((s, e))

    busy.sort()
    merged: List[tuple[datetime, datetime]] = []
    for s, e in busy:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    free: List[FreeBlock] = []
    cursor = window_start
    for s, e in merged:
        if s > cursor:
            minutes = int((s - cursor).total_seconds() // 60)
            if minutes >= min_minutes:
                free.append(
                    FreeBlock(
                        start_at=cursor.isoformat().replace("+00:00", "Z"),
                        end_at=s.isoformat().replace("+00:00", "Z"),
                        minutes=minutes,
                    )
                )
        cursor = max(cursor, e)
    if cursor < window_end:
        minutes = int((window_end - cursor).total_seconds() // 60)
        if minutes >= min_minutes:
            free.append(
                FreeBlock(
                    start_at=cursor.isoformat().replace("+00:00", "Z"),
                    end_at=window_end.isoformat().replace("+00:00", "Z"),
                    minutes=minutes,
                )
            )

    return free


def _parse_iso(value: str) -> datetime:
    """Parse ISO 8601 (with optional `Z`) into a tz-aware datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso_add_minutes(iso: str, minutes: int) -> str:
    dt = _parse_iso(iso) + timedelta(minutes=minutes)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
