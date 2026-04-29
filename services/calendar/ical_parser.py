"""Parse iCal bytes into canonical event dicts.

Two responsibilities:

1. Parse the raw ICS body via the `icalendar` library, which handles
   the full RFC 5545 grammar (VTIMEZONE, properties with parameters,
   line folding, escaping).

2. Expand recurrence rules across a bounded window (default 90 days
   ahead of "now"). RRULE expansion is the hardest part of iCal
   correctness — `recurring-ical-events` is the purpose-built library
   that handles EXDATE, RECURRENCE-ID overrides, and DTSTART changes
   correctly. Reimplementing this would be a 6-month project of its
   own.

Output shape: a list of plain dicts, one per occurrence, ready for
`repository.upsert_events()`. Each carries the `occurrence_key` we use
for dedup (uid + recurrence_id), so the upsert is naturally idempotent
across re-syncs of the same feed.

Time zone strategy: storage is always ISO 8601 UTC (the `Z` suffix).
The source TZID is preserved on the row so a future "show in event's
home TZ" toggle is possible without re-parsing the feed. Display TZ is
the browser's job.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from app_logging import get_logger


LOGGER = get_logger("calendar.ical_parser")


# How far ahead of "now" we expand recurring events. 90 days covers a
# typical academic period. A weekly RRULE with no UNTIL would otherwise
# expand to thousands of rows; bounding at 90 days keeps the row count
# bounded regardless of how aggressive the source RRULE is.
EXPANSION_WINDOW_DAYS = 90

# We also include a little history so events the user is "looking back
# at" still render. 30 days back is enough to cover "what did I do last
# month" without bloating the row count.
EXPANSION_LOOKBACK_DAYS = 30


@dataclass
class ParsedEvent:
    """One occurrence of one event, ready for repository upsert."""

    uid: str
    occurrence_key: str             # uid + recurrence_id for dedup
    recurrence_id: Optional[str]    # None on master / non-recurring
    summary: str
    start_at: str                   # ISO 8601 UTC
    end_at: str                     # ISO 8601 UTC
    timezone: Optional[str]         # source TZID
    all_day: bool
    location: Optional[str]
    categories: Optional[str]
    status: str                     # confirmed | cancelled | tentative
    rrule: Optional[str]            # only set on master (un-expanded) rows; None on expansions
    source_updated_at: Optional[str]
    source_hash: str
    raw: dict                        # full source for replay/debugging


class ICalParseError(Exception):
    """Raised when the iCal body fails parsing."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def parse_ics(body: bytes, *, now: Optional[datetime] = None) -> List[ParsedEvent]:
    """Parse an ICS body into expanded ParsedEvent occurrences.

    `now` is injectable for tests; defaults to UTC now.

    The function does not raise on individual malformed events — it
    skips them with a log line. Calendar feeds in the wild routinely
    contain a few stragglers that don't parse cleanly, and dropping
    one bad event shouldn't poison the whole sync.
    """

    # Imported here so a failure in the optional dep surfaces cleanly
    # at sync time rather than at module import time. icalendar is in
    # requirements.txt; recurring-ical-events too.
    try:
        import icalendar  # type: ignore
        import recurring_ical_events  # type: ignore
    except ImportError as exc:
        raise ICalParseError(
            reason="missing_dependency",
            detail=(
                "iCal parser dependencies are not installed. "
                "Run `pip install -r requirements.txt`."
            ),
        ) from exc

    try:
        cal = icalendar.Calendar.from_ical(body)
    except Exception as exc:
        raise ICalParseError(
            reason="malformed_ics",
            detail=f"Could not parse iCal body: {exc.__class__.__name__}",
        ) from exc

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    window_start = now - timedelta(days=EXPANSION_LOOKBACK_DAYS)
    window_end = now + timedelta(days=EXPANSION_WINDOW_DAYS)

    # Pre-filter the calendar: drop any VEVENT without DTSTART before
    # passing to recurring_ical_events. The library raises wholesale on
    # such components, but real-world feeds in the wild routinely
    # contain a stray malformed event — dropping one shouldn't poison
    # the rest of the sync. We rebuild a fresh Calendar that mirrors
    # the original except for the invalid VEVENTs.
    filtered_cal = _drop_invalid_vevents(icalendar, cal)

    try:
        # recurring_ical_events expands RRULEs, applies EXDATEs, and
        # honors RECURRENCE-ID overrides — the three things you have
        # to get right per RFC 5545 §3.8.5. We use the `between` API
        # so the result is already bounded to our window.
        occurrences = recurring_ical_events.of(filtered_cal).between(
            window_start, window_end
        )
    except Exception as exc:
        raise ICalParseError(
            reason="expansion_failed",
            detail=f"Recurrence expansion failed: {exc.__class__.__name__}",
        ) from exc

    parsed: List[ParsedEvent] = []
    skipped = 0

    for component in occurrences:
        try:
            parsed.append(_event_from_component(component))
        except Exception as exc:
            # Log and continue. One malformed event in a feed of 100
            # shouldn't block the other 99 from showing up.
            skipped += 1
            LOGGER.warning(
                "Skipping malformed iCal event: %s",
                exc.__class__.__name__,
            )

    if skipped:
        LOGGER.info(
            "Parsed %d events, skipped %d malformed",
            len(parsed),
            skipped,
        )

    return parsed


def _drop_invalid_vevents(icalendar_module, cal):
    """Return a copy of `cal` with VEVENTs missing DTSTART removed.

    `recurring_ical_events.of(cal).between(...)` raises wholesale on
    components without DTSTART. We pre-filter so one malformed event
    in a 200-event feed doesn't blank the entire sync.

    Other components (VTIMEZONE, VTODO, top-level properties) are
    preserved verbatim — only VEVENTs without DTSTART are dropped.
    """
    out = icalendar_module.Calendar()
    # Copy the top-level properties (VERSION, PRODID, etc.) so the
    # rebuilt calendar is structurally valid.
    for key in cal.keys():
        out.add(key, cal[key])
    skipped = 0
    for component in cal.subcomponents:
        if component.name == "VEVENT" and "DTSTART" not in component:
            skipped += 1
            continue
        out.add_component(component)
    if skipped:
        LOGGER.info("Pre-filter dropped %d VEVENT(s) missing DTSTART", skipped)
    return out


def _event_from_component(component) -> ParsedEvent:
    """Convert a single icalendar VEVENT into our ParsedEvent shape."""

    uid = str(component.get("UID", "")).strip()
    if not uid:
        raise ValueError("event has no UID")

    summary = str(component.get("SUMMARY", "")).strip()
    location_raw = component.get("LOCATION")
    location = str(location_raw).strip() if location_raw else None

    # CATEGORIES can be a list, a single value, or absent. Normalize to
    # comma-separated string for storage; queries can split on demand.
    categories_raw = component.get("CATEGORIES")
    categories: Optional[str] = None
    if categories_raw:
        if hasattr(categories_raw, "to_ical"):
            cats = categories_raw.to_ical().decode("utf-8", errors="replace")
        else:
            cats = str(categories_raw)
        categories = ",".join(c.strip() for c in cats.split(",") if c.strip()) or None

    # iCal STATUS can be CONFIRMED, CANCELLED, TENTATIVE — we coerce to
    # lowercase to match our schema CHECK. Default to confirmed when
    # the property is absent.
    status_raw = str(component.get("STATUS", "CONFIRMED")).lower()
    status = status_raw if status_raw in ("confirmed", "cancelled", "tentative") else "confirmed"

    dtstart = component.get("DTSTART")
    dtend = component.get("DTEND")
    if not dtstart:
        raise ValueError("event missing DTSTART")

    start_dt = dtstart.dt
    end_dt = dtend.dt if dtend else None

    # Detect all-day events: iCal expresses them as DTSTART;VALUE=DATE
    # without a time component. The `dt` will be a date, not datetime.
    all_day = isinstance(start_dt, date) and not isinstance(start_dt, datetime)

    if all_day:
        # Render as midnight UTC on the local date. Keeps storage
        # uniform; the all_day flag tells the renderer to format
        # without a time.
        start_iso = datetime.combine(start_dt, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        if end_dt is None:
            end_iso = datetime.combine(start_dt + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).isoformat()
        elif isinstance(end_dt, date) and not isinstance(end_dt, datetime):
            end_iso = datetime.combine(end_dt, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        else:
            end_iso = _to_utc_iso(end_dt)
        tzid = None
    else:
        start_iso = _to_utc_iso(start_dt)
        end_iso = _to_utc_iso(end_dt) if end_dt else _to_utc_iso(start_dt + timedelta(hours=1))
        tzid = _extract_tzid(dtstart)

    # RECURRENCE-ID identifies an exception/override of a recurring
    # event. Used in occurrence_key so the override is upserted in the
    # same row as a fresh expansion would land.
    recurrence_id_prop = component.get("RECURRENCE-ID")
    recurrence_id: Optional[str] = None
    if recurrence_id_prop is not None:
        rec_dt = recurrence_id_prop.dt
        if isinstance(rec_dt, datetime):
            recurrence_id = _to_utc_iso(rec_dt)
        else:
            recurrence_id = rec_dt.isoformat()

    occurrence_key = f"{uid}::{recurrence_id or 'master'}::{start_iso}"

    rrule_raw = component.get("RRULE")
    rrule: Optional[str] = None
    if rrule_raw is not None and recurrence_id is None:
        # Keep the master's RRULE for replay/debugging. Expansions
        # don't carry it; only the master row does.
        rrule = rrule_raw.to_ical().decode("utf-8", errors="replace") if hasattr(rrule_raw, "to_ical") else str(rrule_raw)

    last_modified = component.get("LAST-MODIFIED")
    source_updated_at: Optional[str] = None
    if last_modified is not None:
        source_updated_at = _to_utc_iso(last_modified.dt)

    raw_dict = {
        "uid": uid,
        "summary": summary,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "all_day": all_day,
        "tzid": tzid,
        "status": status,
    }
    source_hash = hashlib.sha256(
        json.dumps(raw_dict, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return ParsedEvent(
        uid=uid,
        occurrence_key=occurrence_key,
        recurrence_id=recurrence_id,
        summary=summary,
        start_at=start_iso,
        end_at=end_iso,
        timezone=tzid,
        all_day=all_day,
        location=location,
        categories=categories,
        status=status,
        rrule=rrule,
        source_updated_at=source_updated_at,
        source_hash=source_hash,
        raw=raw_dict,
    )


def _to_utc_iso(dt: datetime) -> str:
    """Coerce any datetime to ISO 8601 UTC with the trailing Z.

    `icalendar` returns timezone-aware datetimes for events with a
    TZID. Naive datetimes are treated as UTC because that's what the
    spec implies for VEVENTs without a TZID and not ending in `Z`.
    """

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_tzid(prop) -> Optional[str]:
    """Pull the source TZID off an icalendar property if present."""

    try:
        params = getattr(prop, "params", None)
        if params and "TZID" in params:
            return str(params["TZID"])
    except Exception:
        pass

    dt = getattr(prop, "dt", None)
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return str(dt.tzinfo)
    return None
