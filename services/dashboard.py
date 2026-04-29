"""Dashboard aggregation.

Single endpoint that returns everything the Dashboard view needs in one
round trip: greeting context, streak + week + session stats, a
heuristically-chosen "Next Best Action," and the counts the quick-action
grid renders ("35 cards due", etc.).

Keeping this in a dedicated service module because the query set spans
study_events, sessions, srs_cards, and documents — putting it in any one
of the existing service files would bloat it and muddle ownership. The
module has no writes; every function is a pure read.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict


# ---------- helpers ----------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _start_of_today_utc(now: datetime | None = None) -> datetime:
    now = now or _now_utc()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_this_week_utc(now: datetime | None = None) -> datetime:
    """ISO week — Monday is day 0. Aligns with how most study tools count
    weekly totals ("this week" = since Monday)."""
    now = now or _now_utc()
    start_today = _start_of_today_utc(now)
    return start_today - timedelta(days=now.weekday())


def _time_of_day(now: datetime | None = None) -> str:
    now = now or _now_utc()
    hour = now.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"


# ---------- individual metrics ----------


def _streak_days(conn: sqlite3.Connection) -> int:
    """Consecutive days ending today on which at least one study_event
    was recorded. Breaks on the first missing day going backward.

    Definition of "studied today" is any row in study_events with
    created_at >= start-of-today. If today has no events but yesterday
    does, the streak has already broken (the user must show up today to
    keep the chain alive). If today has events, we walk backward day by
    day counting consecutive days with activity.
    """
    # Dates (YYYY-MM-DD) on which any study_event happened, distinct,
    # newest first. SQLite's DATE() on a DATETIME column returns the
    # date portion in local time — we use that as "a day of study."
    rows = conn.execute(
        """
        SELECT DISTINCT DATE(created_at) AS d
        FROM study_events
        ORDER BY d DESC
        """
    ).fetchall()
    if not rows:
        return 0
    today = _start_of_today_utc().strftime("%Y-%m-%d")
    study_days = [r["d"] for r in rows]
    if study_days[0] != today:
        # User hasn't studied today — streak is already broken for the
        # purpose of "current streak." Show 0.
        return 0
    streak = 1
    cursor = _start_of_today_utc()
    for day_str in study_days[1:]:
        cursor = cursor - timedelta(days=1)
        expected = cursor.strftime("%Y-%m-%d")
        if day_str != expected:
            break
        streak += 1
    return streak


def _minutes_this_week(conn: sqlite3.Connection) -> float:
    """Sum of study_events.duration_seconds since the start of this ISO
    week, converted to minutes. Rounded to one decimal for UI display."""
    week_start = _start_of_this_week_utc().isoformat(sep=" ", timespec="seconds")
    row = conn.execute(
        """
        SELECT COALESCE(SUM(duration_seconds), 0) AS s
        FROM study_events
        WHERE created_at >= ?
        """,
        (week_start,),
    ).fetchone()
    seconds = float(row["s"] if row else 0.0)
    return round(seconds / 60.0, 1)


def _week_minutes_by_day(conn: sqlite3.Connection) -> list[float]:
    """Minutes studied per day for the last 7 days, oldest → newest.

    Always returns exactly 7 floats so the frontend sparkline never has to
    defend against variable lengths. Day buckets align with local calendar
    days (same as the streak calculation) so a user who studies daily sees
    a sparkline with seven bars, not six-point-something.

    The window is a rolling 7 days ending TODAY, not the current ISO week.
    Rationale: the sparkline answers "how active was I lately?" which feels
    wrong if it resets to empty every Monday morning.
    """
    # Row per study_event with its local date, filtered to the rolling window.
    start = _start_of_today_utc() - timedelta(days=6)
    start_iso = start.isoformat(sep=" ", timespec="seconds")
    rows = conn.execute(
        """
        SELECT DATE(created_at) AS d, COALESCE(SUM(duration_seconds), 0) AS s
        FROM study_events
        WHERE created_at >= ?
        GROUP BY DATE(created_at)
        """,
        (start_iso,),
    ).fetchall()
    by_day: Dict[str, float] = {row["d"]: float(row["s"]) for row in rows}

    buckets: list[float] = []
    cursor = start
    for _ in range(7):
        key = cursor.strftime("%Y-%m-%d")
        seconds = by_day.get(key, 0.0)
        buckets.append(round(seconds / 60.0, 1))
        cursor = cursor + timedelta(days=1)
    return buckets


# Abandonment threshold. A session still marked `active` but started more
# than this many hours ago is dormant — the user closed the app, crashed,
# or forgot about it. We don't mutate the row (history stays intact); we
# just stop surfacing it as "currently running." The UI presents a clean
# dashboard and the user can start fresh. 12h is long enough to cover a
# legitimate "I left my laptop open during lunch" case, short enough that
# yesterday's forgotten session doesn't greet you today.
ACTIVE_SESSION_MAX_AGE_HOURS = 12


def _active_session(conn: sqlite3.Connection) -> Dict[str, Any] | None:
    """Return the currently-active session row, if any.

    "Active" means:
      - `status = 'active'`, AND
      - `started_at` is within the last ACTIVE_SESSION_MAX_AGE_HOURS.

    A row can be status='active' forever if the client never hits the
    complete endpoint (app crash, force-quit, etc.). Without the age
    filter, the dashboard would resurface abandoned sessions from days
    ago and keep a 96-hour timer running. The filter is per-read; rows
    are left alone on disk.

    Defensive against multiple eligible rows: picks the most recent by
    started_at. Schema doesn't enforce uniqueness.
    """
    cutoff = _now_utc() - timedelta(hours=ACTIVE_SESSION_MAX_AGE_HOURS)
    cutoff_iso = cutoff.isoformat(sep=" ", timespec="seconds")
    row = conn.execute(
        """
        SELECT id, objective, mode, duration_minutes, started_at
        FROM sessions
        WHERE status = 'active'
          AND started_at IS NOT NULL
          AND started_at >= ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (cutoff_iso,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "objective": row["objective"],
        "mode": row["mode"],
        "duration_minutes": int(row["duration_minutes"] or 0),
        "started_at": row["started_at"],
    }


def _sessions_today(conn: sqlite3.Connection) -> int:
    """How many Session rows started today. Uses sessions.started_at so
    planned-but-unstarted sessions don't inflate the count."""
    today_start = _start_of_today_utc().isoformat(sep=" ", timespec="seconds")
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM sessions
        WHERE started_at IS NOT NULL AND started_at >= ?
        """,
        (today_start,),
    ).fetchone()
    return int(row["n"] if row else 0)


def _due_card_count(conn: sqlite3.Connection) -> int:
    today = _start_of_today_utc().strftime("%Y-%m-%d")
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM srs_cards
        WHERE due_date IS NULL OR due_date <= ?
        """,
        (today,),
    ).fetchone()
    return int(row["n"] if row else 0)


def _source_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()
    return int(row["n"] if row else 0)


def _last_studied_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MAX(created_at) AS ts FROM study_events"
    ).fetchone()
    return row["ts"] if row and row["ts"] else None


# Threshold for "weak" — concepts at or below this mastery score are
# surfaced on the dashboard rail. 0.7 is intentional: mastery_engine
# computes mastery as recall*0.6 + transfer*0.4, so 0.7 means the user
# is consistently below the band the engine considers "fluent" but
# above the floor of "haven't started."
WEAK_CONCEPT_MASTERY_CEILING = 0.7
WEAK_CONCEPT_LIMIT = 5


def _weak_concepts(conn: sqlite3.Connection) -> list[Dict[str, Any]]:
    """The five concepts the user has actually studied AND is still
    failing on. The Dashboard's feedback-loop signal.

    Filters:
      - `last_tested IS NOT NULL` — concept must have been tested at
        least once. Mastery is 0 by default for fresh ingests; without
        this filter the rail would surface "weakest" concepts that the
        user has never seen, which isn't a struggle signal — it's a
        coverage gap. The Library home is for coverage gaps; this rail
        is for active struggle.
      - `mastery <= WEAK_CONCEPT_MASTERY_CEILING` — the concept hasn't
        cleared the fluency band yet.

    Order: lowest mastery first (worst struggle), with most recent
    last_tested as tiebreaker so a concept the user just failed on
    today comes up before one they failed on a week ago at the same
    mastery score.
    """
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.mastery, c.last_tested,
               d.id AS document_id, d.filename AS document_name,
               d.subject_name
        FROM concepts c
        JOIN documents d ON d.id = c.doc_id
        WHERE c.last_tested IS NOT NULL
          AND c.mastery <= ?
        ORDER BY c.mastery ASC, c.last_tested DESC
        LIMIT ?
        """,
        (WEAK_CONCEPT_MASTERY_CEILING, WEAK_CONCEPT_LIMIT),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "mastery": float(row["mastery"] or 0.0),
            "last_tested": row["last_tested"],
            "document_id": row["document_id"],
            "document_name": row["document_name"],
            "subject_name": row["subject_name"],
        }
        for row in rows
    ]


# ---------- next best action heuristic ----------


def _next_best_action(
    *,
    due_cards: int,
    source_count: int,
    sessions_today: int,
    last_studied_at: str | None,
) -> Dict[str, Any]:
    """Pick ONE concrete thing the user should do right now.

    Priority ladder (highest first):
      1. No sources yet → import something. Without material, nothing else
         works. Prime the library first.
      2. Cards due → review them. Spaced repetition is the highest-yield
         study activity when due.
      3. Haven't studied today → start a session. Keeps rhythm.
      4. Fresh-off-session → offer generative extension (ask tutor about
         what was just studied).
      5. Fallback → general "ask tutor" prompt.

    Each branch returns the same shape so the UI renders one card with a
    headline, a reason, a primary action, and an optional secondary.
    """
    if source_count == 0:
        return {
            "kind": "import",
            "eyebrow": "Start here",
            "title": "Add your first source",
            "reason": "The tutor, reader, and flashcards all work from your own materials — drop a PDF or notes into the Library to begin.",
            "primary": {"label": "Open Library", "path": "/library"},
            "secondary": None,
        }
    if due_cards > 0:
        return {
            "kind": "review",
            "eyebrow": "Next best action",
            "title": f"{due_cards} card{'s' if due_cards != 1 else ''} due",
            "reason": "Retrieval practice has the strongest evidence of any study activity when cards are due — keep the queue from compounding.",
            "primary": {"label": "Start review", "path": "/study"},
            "secondary": {"label": "Manage cards", "path": "/study?mode=manage"},
        }
    if sessions_today == 0:
        return {
            "kind": "session",
            "eyebrow": "Keep the rhythm",
            "title": "Start a focused session",
            "reason": "No session today yet. Twenty minutes of deep work beats a distracted hour.",
            "primary": {"label": "Begin session", "path": "/session"},
            "secondary": {"label": "Ask a question", "path": "/ask"},
        }
    return {
        "kind": "explore",
        "eyebrow": "Keep going",
        "title": "Ask something you're unsure about",
        "reason": "You've already started today. Pose a question about a concept that felt shaky — the tutor will cite your own sources.",
        "primary": {"label": "Ask the tutor", "path": "/ask"},
        "secondary": None,
    }


# ---------- public entry ----------


def build_dashboard_payload(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Top-level aggregation. Runs every metric, bundles them, returns a
    single dict the Dashboard view renders without further API calls."""
    streak = _streak_days(conn)
    week_minutes = _minutes_this_week(conn)
    week_by_day = _week_minutes_by_day(conn)
    sessions = _sessions_today(conn)
    due = _due_card_count(conn)
    sources = _source_count(conn)
    last_at = _last_studied_at(conn)
    active = _active_session(conn)
    weak = _weak_concepts(conn)

    now = _now_utc()
    return {
        "generated_at": now.isoformat(),
        "greeting": {
            "time_of_day": _time_of_day(now),
            "iso_date": now.strftime("%Y-%m-%d"),
            "display_date": now.strftime("%A, %B %-d"),
        },
        "stats": {
            "streak_days": streak,
            "streak_target_days": 30,
            "week_minutes": week_minutes,
            "week_minutes_by_day": week_by_day,
            "sessions_today": sessions,
            "due_cards": due,
            "source_count": sources,
            "last_studied_at": last_at,
        },
        "next_best_action": _next_best_action(
            due_cards=due,
            source_count=sources,
            sessions_today=sessions,
            last_studied_at=last_at,
        ),
        "active_session": active,
        # Carrel's analogue of IAF's bullet-priority feedback loop. The
        # mastery_engine writes recall/transfer-derived mastery onto each
        # concept after a session; this surfaces the bottom 5 the user
        # has actually tested as a "needs revisiting" rail. Closes the
        # loop: review outcome → mastery update → dashboard rail →
        # operator drills back into the source.
        "weak_concepts": weak,
    }
