"""Study-coach suggestion synthesis.

V1 (Phase 1, this file): one rule, end-to-end.
  Rule "free_block_overdue_srs": if there's a free block ≥ 60 minutes
  in the next 24 hours AND there's at least one overdue SRS card,
  emit one suggestion. Render as a `study_block` in the user's day.

  Reason text: "60-min gap and N cards overdue."

  Score: 1.0 (single rule means no ranking needed yet; preserved for
  Phase 2's multi-rule pipeline).

Phase 2 ships in waves; each rule is its own commit:

  Rule "deadline_imminent" (shipped 940966bf / fb2dc9fc): parses
  calendar event summaries for midterm/final/exam/quiz, anchors a
  60-min study_block at the first free window before the deadline,
  scores by urgency in four buckets (3.0/2.5/2.0/1.5).

  Rule "low_recent_review" (shipped b12359d2 / 87b94897): emits one
  review_block when at least MIN_STALE_CARDS cards have
  last_review < now - REVIEW_STALE_DAYS AND are not currently
  overdue. Partition with the v1 free_block_overdue_srs rule is
  intentional (this rule covers proactive refresh, v1 covers
  reactive catchup).

  Rule "gap_between_classes" (shipped this commit): when two
  adjacent calendar events at the same location are 30-120 minutes
  apart, anchor a catchup micro-session at the first event's end
  with duration `gap - GAP_TRANSITION_BUFFER_MINUTES` capped at
  GAP_MAX_SESSION_MINUTES. Score 1.2.

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
import re
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

# Look-ahead window for the deadline-imminent rule. Phase 2 v1 keeps a
# two-week horizon: longer than v1's 24h (so a midterm next Monday
# surfaces on Thursday) but short enough that the "imminent" framing
# stays honest. Beyond 14d the calendar feed sync hasn't reliably
# expanded recurrences either.
DEADLINE_LOOKAHEAD_DAYS = 14

# Word-boundary, case-insensitive match against the four strongest
# academic-deadline signals. Kept narrow on purpose: false positives
# ("driver's exam", "Cup Final") erode trust faster than missed
# matches. The user can dismiss; a noisy panel is worse than a quiet
# one.
DEADLINE_KEYWORD_PATTERN = re.compile(r"\b(midterm|final|exam|quiz)\b", re.IGNORECASE)

# Staleness threshold for the proactive-refresh rule. Cards last
# reviewed before now - REVIEW_STALE_DAYS qualify as "abandoned" when
# they aren't already overdue. Seven days matches a common SRS
# weekly-touch rhythm; the v1 free_block_overdue_srs rule already
# handles cards that crossed the due_date threshold, so the
# low_recent_review rule's filter excludes overdue cards to avoid
# double-firing on the same population.
REVIEW_STALE_DAYS = 7

# Minimum stale-card count below which the low_recent_review rule
# stays quiet. A single forgotten card isn't worth a panel slot;
# pushing the threshold prevents the suggestion from feeling chatty
# for users who only have a handful of cards.
MIN_STALE_CARDS = 5

# Bounds for the gap_between_classes rule. Gaps shorter than the lower
# bound aren't worth a context switch; gaps at or above the upper bound
# are big enough that the user probably already has plans (lunch, study
# at home, etc.) so the suggestion would feel presumptuous.
GAP_MIN_MINUTES = 30
GAP_MAX_MINUTES = 120

# Buffer subtracted from the suggested micro-session's duration so the
# user has time to pack up + walk + settle. The remaining session is
# capped at 30 minutes because the rule is about focused micro-work,
# not a full study block.
GAP_TRANSITION_BUFFER_MINUTES = 5
GAP_MAX_SESSION_MINUTES = 30


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
        _rule_deadline_imminent,
        _rule_low_recent_review,
        _rule_gap_between_classes,
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
    them), and only insert new ones whose (kind, start_at,
    reason_code) tuple isn't already represented in the pending set.
    Past-start_at pending suggestions are expired by the caller
    before this runs.

    The `reason_code` component of the dedupe key is load-bearing
    now that Phase 2 ships `low_recent_review`: both that rule and
    the v1 `free_block_overdue_srs` emit `kind="review_block"` at
    `_find_free_blocks(...)[0]`, so two rules can produce candidates
    with the same `(kind, start_at)` but different reason_codes.
    Dedupe on the triple keeps each rule's distinct signal visible
    on subsequent refreshes; dedupe on the pair would silently
    swallow whichever rule landed second.
    """
    repository.expire_past_pending_suggestions(conn, user_id=user_id)

    existing = repository.list_active_suggestions(conn, user_id=user_id)
    existing_keys = {(s.kind, s.start_at, s.reason_code) for s in existing}

    candidates = synthesize_suggestions(conn, user_id=user_id)
    for candidate in candidates:
        key = (candidate.kind, candidate.start_at, candidate.reason_code)
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


def _rule_deadline_imminent(conn: sqlite3.Connection, *, user_id: str) -> List[CandidateSuggestion]:
    """Phase 2 rule. One suggestion per upcoming calendar event whose
    summary names an academic deadline (`midterm` / `final` / `exam`
    / `quiz`, case-insensitive, word-boundary). Anchors the suggested
    study block to the chronologically first free 60-min window
    between now and the deadline. Skips the event if no free block
    fits.

    Scoring buckets (higher rises above the v1
    `free_block_overdue_srs` baseline of 1.0):
      ≤ 24h  -> 3.0  (urgent)
      ≤ 72h  -> 2.5  (this week)
      ≤ 168h -> 2.0  (next week)
      ≤ 14d  -> 1.5  (early heads-up)

    Reason text examples:
      "Calculus midterm tomorrow."        (≤ 36h)
      "Spanish final in 4 days."          (otherwise)

    Phase 2 v1 deliberately omits the longer-arc "3-session study
    plan" sketched in the module docstring; one anchored block per
    deadline keeps the surface small and avoids stepping on the
    `low_recent_review` plug point that lands next.

    Known v1 limitation (rule layer is fine; downstream caller is
    the one to fix later): the rule itself emits one candidate per
    deadline event, but `refresh_active_suggestions` dedupes by
    `(kind, start_at)`. Two deadline events whose first-free-block
    lands on the same minute will, on a later refresh after one
    has already persisted, see the second silently dropped. The
    rule layer is correct (a fresh-context test asserts both
    candidates surface here); fixing the dedupe key to also
    include `source_event_id` is a behavior change to the refresh
    path and is deferred to its own PR.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=DEADLINE_LOOKAHEAD_DAYS)

    deadline_events = _find_deadline_events(
        conn,
        user_id=user_id,
        window_start=now,
        window_end=horizon,
    )
    if not deadline_events:
        return []

    candidates: List[CandidateSuggestion] = []
    for event in deadline_events:
        try:
            deadline_at = _parse_iso(event["start_at"])
        except ValueError:
            continue
        if deadline_at <= now or deadline_at > horizon:
            continue

        # Prefer the chronologically first free block so the user can
        # start preparing as soon as possible. Spaced practice beats
        # cramming; "study tonight" beats "study tomorrow night."
        free_blocks = _find_free_blocks(
            conn,
            window_start=now,
            window_end=deadline_at,
            min_minutes=MIN_FREE_BLOCK_MINUTES,
            user_id=user_id,
        )
        if not free_blocks:
            continue

        block = free_blocks[0]
        suggested_end = _iso_add_minutes(block.start_at, MIN_FREE_BLOCK_MINUTES)
        hours_until = (deadline_at - now).total_seconds() / 3600.0
        summary = (event["summary"] or "").strip()

        candidates.append(
            CandidateSuggestion(
                kind="study_block",
                start_at=block.start_at,
                end_at=suggested_end,
                reason_code="deadline_imminent",
                reason_text=_reason_text_for_deadline(summary, hours_until),
                due_at=event["start_at"],
                source_event_id=event["id"],
                score=_score_for_deadline(hours_until),
            )
        )

    return candidates


def _find_deadline_events(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    window_start: datetime,
    window_end: datetime,
) -> List[sqlite3.Row]:
    """Calendar events in [window_start, window_end) whose summary
    matches `DEADLINE_KEYWORD_PATTERN`. Cancelled events are
    excluded; all-day events are kept (a "Midterm Day" entry is a
    legitimate deadline anchor even if all_day=1).
    """
    start_iso = window_start.isoformat().replace("+00:00", "Z")
    end_iso = window_end.isoformat().replace("+00:00", "Z")

    rows = conn.execute(
        """
        SELECT id, summary, start_at FROM calendar_events
        WHERE user_id = ?
          AND status != 'cancelled'
          AND start_at >= ?
          AND start_at < ?
          AND summary IS NOT NULL
        ORDER BY start_at ASC
        """,
        (user_id, start_iso, end_iso),
    ).fetchall()

    return [row for row in rows if DEADLINE_KEYWORD_PATTERN.search(row["summary"])]


def _score_for_deadline(hours_until: float) -> float:
    """Higher score for sooner deadlines so the panel ranks an
    imminent exam above the `free_block_overdue_srs` baseline.
    """
    if hours_until <= 24:
        return 3.0
    if hours_until <= 72:
        return 2.5
    if hours_until <= 168:  # 7 days
        return 2.0
    return 1.5


def _reason_text_for_deadline(summary: str, hours_until: float) -> str:
    """User-facing copy. Three buckets keep the panel readable: hours
    for same-day, "tomorrow" for next-day, days for the rest.
    """
    if hours_until < 12:
        # round to nearest hour; clamp to >= 1 so we never say "in 0h"
        hours = max(1, int(hours_until + 0.5))
        return f"{summary} in {hours}h."
    if hours_until < 36:
        return f"{summary} tomorrow."
    days = max(2, int(hours_until / 24 + 0.5))
    return f"{summary} in {days} days."


def _rule_low_recent_review(conn: sqlite3.Connection, *, user_id: str) -> List[CandidateSuggestion]:
    """Phase 2 rule. Emits one `review_block` suggestion when at
    least `MIN_STALE_CARDS` cards have `last_review < now -
    REVIEW_STALE_DAYS` AND are not currently overdue. Anchors the
    block at the chronologically first free 60-min window in the
    next 24h.

    Partition rationale: the v1 `free_block_overdue_srs` rule
    already covers overdue cards. This rule covers the "abandoned
    but not yet stale" pattern, which is a distinct user signal
    (proactive refresh rather than reactive catchup).

    Score: 1.5. Above the v1 baseline of 1.0 so a panel that has
    both signals surfaces this first; below `deadline_imminent`'s
    bottom bucket of 1.5 by tying, then `deadline_imminent` lands
    earlier in the rules list so the sort-stable order keeps it
    visually above. (If tie-breaking ever needs to be explicit,
    bump this to 1.4.)

    Skips silently when:
      - No cards satisfy the staleness predicate.
      - No 60-min free block exists in the next 24h window.

    Same `(kind, start_at)` dedupe limitation as
    `_rule_deadline_imminent`; the rule layer emits one candidate,
    the downstream `refresh_active_suggestions` dedupes against
    existing pending suggestions with the same key.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=LOOKAHEAD_HOURS)

    stale_count = _count_stale_review_cards(conn)
    if stale_count < MIN_STALE_CARDS:
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

    block = free_blocks[0]
    suggested_end = _iso_add_minutes(block.start_at, MIN_FREE_BLOCK_MINUTES)

    return [
        CandidateSuggestion(
            kind="review_block",
            start_at=block.start_at,
            end_at=suggested_end,
            reason_code="low_recent_review",
            reason_text=(
                f"{stale_count} card{'s' if stale_count != 1 else ''} "
                f"haven't seen review in {REVIEW_STALE_DAYS}+ days."
            ),
            score=1.5,
        )
    ]


def _count_stale_review_cards(conn: sqlite3.Connection) -> int:
    """Cards reviewed at least once but not in the last
    `REVIEW_STALE_DAYS` days AND not currently overdue.

    `last_review` is stored by `services.review_scheduler` as
    `datetime.now(timezone.utc).isoformat()` (with `+00:00` suffix,
    not `Z`), so the cutoff uses the same format for lexicographic
    comparison correctness.

    `due_date` is stored as a YYYY-MM-DD date string; `> today`
    excludes cards that have already crossed the due threshold
    (those belong to the v1 rule's domain).
    """
    now = datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=REVIEW_STALE_DAYS)).isoformat()
    today_iso = now.date().isoformat()
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM srs_cards
        WHERE last_review IS NOT NULL
          AND last_review < ?
          AND due_date IS NOT NULL
          AND due_date > ?
        """,
        (cutoff_iso, today_iso),
    ).fetchone()
    return int(row["n"]) if row else 0


def _rule_gap_between_classes(
    conn: sqlite3.Connection, *, user_id: str
) -> List[CandidateSuggestion]:
    """Phase 2 rule. When two upcoming calendar events at the same
    location are 30-120 minutes apart, emit a focused micro-session
    suggestion anchored at the first event's end. The "same location"
    proxy assumes the user is already on-site for both classes, so a
    brief session is friction-free.

    Suggested duration: `gap_minutes - GAP_TRANSITION_BUFFER_MINUTES`,
    capped at `GAP_MAX_SESSION_MINUTES`. The transition buffer leaves
    time to walk + settle into the next room; the cap keeps the
    session feel micro rather than block-sized.

    Score: 1.2. Above the v1 `free_block_overdue_srs` baseline of
    1.0 so a panel that sees both signals surfaces this first, but
    below `low_recent_review` (1.5) and `deadline_imminent` (1.5+)
    so urgent SRS / exam signals stay on top.

    Location comparison: case-insensitive whitespace-trim match. The
    user's calendar entries from one feed (e.g. Apple Calendar)
    usually format locations consistently. Substring or fuzzy match
    is a future PR if the false-negative rate from format drift
    proves real.

    Skips an event pair when:
      - Either event is cancelled.
      - Either event has a NULL or empty location.
      - The locations don't match after normalization.
      - The gap falls outside [GAP_MIN_MINUTES, GAP_MAX_MINUTES).
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=LOOKAHEAD_HOURS)
    pairs = _find_back_to_back_event_pairs(
        conn, user_id=user_id, window_start=now, window_end=horizon
    )

    candidates: List[CandidateSuggestion] = []
    for first, second, gap_minutes in pairs:
        session_minutes = min(gap_minutes - GAP_TRANSITION_BUFFER_MINUTES, GAP_MAX_SESSION_MINUTES)
        if session_minutes < GAP_TRANSITION_BUFFER_MINUTES:
            # Defensive: gap_minutes >= 30 and buffer = 5 means
            # session >= 25, so this branch is unreachable today.
            # Kept for forgiveness if either constant is ever
            # retuned.
            continue
        start_at = first["end_at"]
        end_at = _iso_add_minutes(start_at, session_minutes)
        location = (first["location"] or "").strip()
        candidates.append(
            CandidateSuggestion(
                kind="catchup",
                start_at=start_at,
                end_at=end_at,
                reason_code="gap_between_classes",
                reason_text=(f"{int(gap_minutes)}-min gap between {location} sessions."),
                source_event_id=first["id"],
                score=1.2,
            )
        )

    return candidates


def _find_back_to_back_event_pairs(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    window_start: datetime,
    window_end: datetime,
) -> List[tuple[sqlite3.Row, sqlite3.Row, float]]:
    """Returns `(first, second, gap_minutes)` triples for non-
    cancelled, same-location event pairs whose between-gap is in
    `[GAP_MIN_MINUTES, GAP_MAX_MINUTES)`. Iterates events in
    chronological order and only checks the immediately-next event
    (single pass; O(n) instead of O(n^2) pairwise), which is the
    intended semantic anyway — "back to back" means adjacent in the
    user's schedule, not "any two events on the same day."
    """
    start_iso = window_start.isoformat().replace("+00:00", "Z")
    end_iso = window_end.isoformat().replace("+00:00", "Z")

    rows = list(
        conn.execute(
            """
            SELECT id, summary, start_at, end_at, location FROM calendar_events
            WHERE user_id = ?
              AND status != 'cancelled'
              AND start_at >= ?
              AND start_at < ?
              AND location IS NOT NULL
              AND TRIM(location) != ''
            ORDER BY start_at ASC
            """,
            (user_id, start_iso, end_iso),
        ).fetchall()
    )

    pairs: List[tuple[sqlite3.Row, sqlite3.Row, float]] = []
    for first, second in zip(rows, rows[1:]):
        if not _locations_match(first["location"], second["location"]):
            continue
        try:
            first_end = _parse_iso(first["end_at"])
            second_start = _parse_iso(second["start_at"])
        except ValueError:
            continue
        if second_start <= first_end:
            continue  # overlapping / immediately back-to-back; no gap to fill
        gap_minutes = (second_start - first_end).total_seconds() / 60.0
        if gap_minutes < GAP_MIN_MINUTES or gap_minutes >= GAP_MAX_MINUTES:
            continue
        pairs.append((first, second, gap_minutes))
    return pairs


def _locations_match(a: str | None, b: str | None) -> bool:
    """Case-insensitive whitespace-trim equality. Returns False when
    either input is None/empty after trim so callers can rely on
    "match implies non-empty location" downstream.
    """
    if a is None or b is None:
        return False
    aa = a.strip().lower()
    bb = b.strip().lower()
    if not aa or not bb:
        return False
    return aa == bb


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
