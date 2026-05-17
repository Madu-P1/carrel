"""Unit tests for ``log_study_event`` resilience to write-lock contention.

Pinning the fix for docs/issues/2026-05-14-sqlite-write-lock-during-ingestion.md.
The user's tutor query returned HTTP 500 because log_study_event raised
sqlite3.OperationalError("database is locked") while a big-PDF ingestion
held the writer lock. Telemetry is fire-and-forget by contract; a write
failure here must NEVER propagate to the user-visible response.
"""

import logging
import sqlite3
from unittest.mock import MagicMock

import pytest

from services.app_state import log_study_event


@pytest.fixture
def app_state_caplog(caplog):
    """caplog with the `einstein` logger's propagation re-enabled.

    `app_logging.configure_backend_logging()` sets
    `logging.getLogger("einstein").propagate = False` so production logs
    don't double-emit through the root logger. pytest's `caplog`
    attaches its capture handler to the root logger, so once
    `configure_backend_logging` has run in ANY test in the same process
    (which happens whenever the backend boots), `caplog` stops seeing
    records emitted under `einstein.*`. This fixture flips propagation
    back on for the duration of one test and restores it afterward,
    making the assertions order-independent in the full suite.
    """
    einstein_logger = logging.getLogger("einstein")
    original = einstein_logger.propagate
    einstein_logger.propagate = True
    try:
        yield caplog
    finally:
        einstein_logger.propagate = original


class TestLogStudyEventResilience:
    def test_happy_path_writes_and_commits(self):
        # Sanity: the well-behaved path still issues exactly one INSERT
        # and one COMMIT. Telemetry must work when nothing is wrong.
        conn = MagicMock(spec=sqlite3.Connection)
        log_study_event(conn, "tutor_grounded_answer", doc_id="d1", payload={"k": "v"})
        conn.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_database_locked_during_execute_swallowed(self, app_state_caplog):
        caplog = app_state_caplog
        # The actual failure mode from 2026-05-13: another writer holds the
        # lock, busy_timeout exceeded, OperationalError raised. Pre-fix
        # this propagated as a 500 from /api/tutor/query. Post-fix it
        # becomes a logged warning and the user gets their tutor answer.
        conn = MagicMock(spec=sqlite3.Connection)
        conn.execute.side_effect = sqlite3.OperationalError("database is locked")
        with caplog.at_level(logging.WARNING, logger="einstein.app_state"):
            log_study_event(conn, "tutor_grounded_answer", doc_id="d1")
        # No exception propagated. Now check the warning fired with the
        # structured event name so observability is preserved.
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "expected a WARNING log when telemetry write was dropped"
        assert any("telemetry_dropped" in r.message for r in warnings)

    def test_database_locked_during_commit_swallowed(self):
        # The lock can also be lost between execute() and commit() —
        # the execute writes to the WAL but commit needs the writer
        # lock to fsync. Same contract: swallow + warn, never raise.
        conn = MagicMock(spec=sqlite3.Connection)
        conn.commit.side_effect = sqlite3.OperationalError("database is locked")
        # No raise — that's the whole point of this test.
        log_study_event(conn, "test_event")

    def test_non_operational_error_still_raises(self):
        # We intentionally only swallow OperationalError. A programming
        # error (TypeError, AttributeError) signals a real bug and MUST
        # still surface. Otherwise we'd paper over future regressions.
        conn = MagicMock(spec=sqlite3.Connection)
        conn.execute.side_effect = TypeError("oops, programming error")
        with pytest.raises(TypeError):
            log_study_event(conn, "test_event")

    def test_warning_includes_diagnostic_context(self, app_state_caplog):
        caplog = app_state_caplog
        # When telemetry drops, we should be able to tell from the log
        # WHAT was dropped (event_type, doc_id) and WHY (the OperationalError
        # message). Otherwise debugging future contention becomes guesswork.
        conn = MagicMock(spec=sqlite3.Connection)
        conn.execute.side_effect = sqlite3.OperationalError("database is locked")
        with caplog.at_level(logging.WARNING, logger="einstein.app_state"):
            log_study_event(
                conn,
                "tutor_grounded_answer",
                doc_id="doc-abc",
                concept_id="concept-xyz",
                payload={"trace_id": "trc-123"},
            )
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings
        msg = warnings[0].message
        # Structured logger emits these as kwargs on the LogRecord;
        # the formatted message contains the bare event name. Check both
        # directions so the test stays useful regardless of formatter.
        assert "telemetry_dropped" in msg
        # Carrel's structured logger (app_logging.log_event) stashes kwargs
        # under record.context — not as flat LogRecord attributes — so the
        # JSON formatter can serialize them as one object. Verify there.
        ctx = getattr(warnings[0], "context", {})
        assert ctx.get("event_type") == "tutor_grounded_answer"
        assert ctx.get("doc_id") == "doc-abc"
        assert ctx.get("concept_id") == "concept-xyz"
        assert ctx.get("reason") == "sqlite_operational_error"
        assert "database is locked" in str(ctx.get("error", ""))
