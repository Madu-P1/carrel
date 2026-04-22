import { useCallback, useEffect, useRef, useState } from "preact/hooks";

import { Icon } from "@/design-system";
import { navigateTo, setActiveSession } from "@/app/shell/useAppShell";
import { ApiError } from "@/services/api/client";
import { parseIsoAsUtc } from "@/lib/time";
import {
  sessions,
  type ActiveSessionSummary,
  type SessionCompletionResult
} from "@/services/api/endpoints";

import styles from "./ActiveSessionCard.module.css";

interface ActiveSessionCardProps {
  active: ActiveSessionSummary | null;
  /** Called after any mutation (end session) so the parent can refetch
   *  the dashboard and the status card reconciles with server state. */
  onMutation: () => void;
}

type CardState =
  | { kind: "idle" }
  | { kind: "active"; session: ActiveSessionSummary }
  | { kind: "ending"; session: ActiveSessionSummary }
  | { kind: "completed"; result: SessionCompletionResult }
  | { kind: "error"; message: string };

/**
 * Status surface for the session engine. Deliberately scoped to "show
 * what's happening" + "let me end it" — the full Start form is follow-up
 * work, per the autoplan gate. When no session is active, this card
 * renders nothing (saves space; the Next Best Action above already
 * handles the "start something" prompt).
 *
 * States:
 *   - idle          → null render
 *   - active        → status chip with elapsed time + End button
 *   - ending        → End button in-flight
 *   - completed     → mastery summary (dismissible, ephemeral)
 *   - error         → inline retry after 404/5xx
 *
 * Elapsed time: client-side tick from `started_at`, anchored to server
 * time. Reduced-motion → text updates once per minute instead of per
 * second to avoid animation-like redraws.
 */
export function ActiveSessionCard({ active, onMutation }: ActiveSessionCardProps) {
  const [state, setState] = useState<CardState>(() =>
    active ? { kind: "active", session: active } : { kind: "idle" }
  );

  // Reconcile with server state when the parent refetches. Completed +
  // error states are local-only and don't get overridden until the user
  // dismisses them.
  useEffect(() => {
    setState((prev) => {
      if (prev.kind === "completed" || prev.kind === "error") return prev;
      return active ? { kind: "active", session: active } : { kind: "idle" };
    });
  }, [active]);

  const endSession = useCallback(async () => {
    if (state.kind !== "active") return;
    const session = state.session;
    setState({ kind: "ending", session });
    try {
      const result = await sessions.complete(session.id);
      setState({ kind: "completed", result });
      setActiveSession(null);
      onMutation();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        // Another tab or process already ended this session. Treat as
        // "already done," refetch, and slip back to idle silently.
        setState({ kind: "idle" });
        setActiveSession(null);
        onMutation();
        return;
      }
      setState({
        kind: "error",
        message:
          caught instanceof Error
            ? caught.message
            : "Could not end session. Try again."
      });
    }
  }, [state, onMutation]);

  const dismissCompletion = useCallback(() => setState({ kind: "idle" }), []);
  const retryEnd = useCallback(() => {
    if (active) setState({ kind: "active", session: active });
  }, [active]);

  if (state.kind === "idle") {
    return null;
  }

  if (state.kind === "completed") {
    return <CompletedSummary result={state.result} onDismiss={dismissCompletion} />;
  }

  if (state.kind === "error") {
    return (
      <div className={styles.wrap} role="alert">
        <div className={styles.errorBody}>
          <span className={styles.eyebrow}>Session error</span>
          <span className={styles.errorText}>{state.message}</span>
        </div>
        <button type="button" className={styles.endButton} onClick={retryEnd}>
          Try again
        </button>
      </div>
    );
  }

  const session = state.session;
  const isEnding = state.kind === "ending";
  // Strip the `[ui:mode]` prefix the Session view encodes into objective
  // so the dashboard reads cleanly regardless of where the session was
  // created. The prefix is opaque metadata, not user-facing copy.
  const displayObjective = (session.objective || "").replace(
    /^\[ui:(?:pomodoro|flowtime|notes|flashcards)\]\s*/,
    ""
  ) || "(no objective set)";
  return (
    <div className={styles.wrap} aria-label="Active session">
      <span className={styles.dot} aria-hidden />
      <button
        type="button"
        className={styles.bodyButton}
        onClick={() => navigateTo("/session")}
        aria-label="Open session view"
      >
        <div className={styles.topRow}>
          <span className={styles.eyebrow}>Active session</span>
          <Elapsed startedAt={session.started_at} targetMinutes={session.duration_minutes} />
        </div>
        <div className={styles.objective}>{displayObjective}</div>
        <div className={styles.mode}>
          {session.mode.replace(/_/g, " ")}
          {session.duration_minutes > 0 ? ` · planned ${session.duration_minutes} min` : ""}
        </div>
      </button>
      <button
        type="button"
        className={styles.endButton}
        onClick={() => void endSession()}
        disabled={isEnding}
      >
        {isEnding ? "Ending…" : "End session"}
      </button>
    </div>
  );
}

/** Elapsed time ticker. Reduced-motion respecters tick once per minute. */
function Elapsed({
  startedAt,
  targetMinutes
}: {
  startedAt: string;
  targetMinutes: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  const startedMs = useRef(parseIsoAsUtc(startedAt)).current;

  useEffect(() => {
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    const interval = reduced ? 60_000 : 1_000;
    const timer = window.setInterval(() => setNow(Date.now()), interval);
    return () => window.clearInterval(timer);
  }, []);

  if (!Number.isFinite(startedMs)) {
    return <span className={styles.elapsed}>—</span>;
  }
  const elapsedSec = Math.max(0, Math.floor((now - startedMs) / 1000));
  const overTarget = targetMinutes > 0 && elapsedSec > targetMinutes * 60;
  return (
    <span
      className={[styles.elapsed, overTarget ? styles.elapsedOver : ""].join(" ")}
    >
      {formatElapsed(elapsedSec)}
    </span>
  );
}

function formatElapsed(totalSec: number): string {
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

function CompletedSummary({
  result,
  onDismiss
}: {
  result: SessionCompletionResult;
  onDismiss: () => void;
}) {
  const deltaPct = Math.round(result.mastery_delta * 100);
  const deltaLabel = deltaPct === 0 ? "±0%" : deltaPct > 0 ? `+${deltaPct}%` : `${deltaPct}%`;
  return (
    <div className={styles.wrap} role="status" aria-label="Session complete">
      <div className={styles.completedBody}>
        <div className={styles.topRow}>
          <span className={styles.eyebrow}>Session complete</span>
          <span
            className={[
              styles.deltaChip,
              deltaPct >= 0 ? styles.deltaChipPos : styles.deltaChipNeg
            ].join(" ")}
          >
            Mastery {deltaLabel}
          </span>
        </div>
        <p className={styles.summaryLine}>{result.revision_recommendation}</p>
        {result.weak_concepts.length > 0 && (
          <div className={styles.chipRow}>
            {result.weak_concepts.map((concept) => (
              <span key={concept} className={styles.weakChip}>
                {concept}
              </span>
            ))}
          </div>
        )}
        {result.stretch_question && (
          <p className={styles.stretch}>
            <span className={styles.stretchLabel}>Stretch · </span>
            {result.stretch_question}
          </p>
        )}
      </div>
      <button
        type="button"
        className={styles.dismissButton}
        onClick={onDismiss}
        aria-label="Dismiss session summary"
      >
        <Icon name="x" size={14} />
      </button>
    </div>
  );
}
