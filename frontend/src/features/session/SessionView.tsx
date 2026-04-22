import { useCallback, useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";

import { Icon } from "@/design-system";
import { ApiError } from "@/services/api/client";
import {
  library,
  sessions,
  type ActiveSessionSummary,
  type SessionCompletionResult,
  type SubjectSummary
} from "@/services/api/endpoints";
import { navigateTo, setActiveSession } from "@/app/shell/useAppShell";

import { ModeTile, type ModeTileData } from "./components/ModeTile";
import { NotesWorkspace } from "./components/NotesWorkspace";
import { TimerRing } from "./components/TimerRing";
import styles from "./SessionView.module.css";

/**
 * Session engine — Enter deep work.
 *
 * Three top-level states:
 *   1. setup      — no active session: render mode tiles + setup form
 *   2. active     — session running: timer ring + mode-specific body
 *   3. completed  — just-ended: mastery summary with revision recs
 *
 * State is server-sourced. We fetch /api/sessions/active on mount and on
 * window focus; if one is active we land in state 2 automatically,
 * matching what the Dashboard shows. The completion state is local-only
 * (ephemeral) and follows directly from the user pressing End; it does
 * NOT persist across refresh.
 *
 * Mode mapping to backend:
 *   pomodoro    → focus_sprint
 *   flowtime    → mixed
 *   notes       → focus_sprint  (UI branches, backend doesn't care)
 *   flashcards  → retrieval_practice
 *
 * The frontend mode identifier is kept separate from the backend mode
 * because "notes" is a UI concern, not a scheduler concern.
 */

type UiMode = "pomodoro" | "flowtime" | "notes" | "flashcards";

const MODES: ModeTileData[] = [
  { id: "pomodoro", label: "Pomodoro", description: "Timed focus with a clear end", icon: "study" },
  { id: "flowtime", label: "Flowtime", description: "Open-ended, stop when ready", icon: "sparkle" },
  { id: "notes", label: "Notes", description: "Writing-first with AI expand", icon: "doc" },
  { id: "flashcards", label: "Flashcards", description: "Spaced repetition review", icon: "ask" }
];

const DURATIONS = [15, 25, 45, 60];

const UI_TO_BACKEND_MODE: Record<UiMode, string> = {
  pomodoro: "focus_sprint",
  flowtime: "mixed",
  notes: "focus_sprint",
  flashcards: "retrieval_practice"
};

/** Persist the ui-mode by stashing it in the objective prefix — backend
 *  doesn't know about "notes" vs "pomodoro" UI distinction. We could add
 *  a column but that's a migration for a single bit of frontend state.
 *  Round-tripped on active-session reload. Prefix is invisible to the
 *  user because we strip it in the UI. */
const UI_MODE_PREFIX = "[ui:";

function encodeObjective(uiMode: UiMode, objective: string): string {
  return `${UI_MODE_PREFIX}${uiMode}] ${objective}`;
}

function decodeObjective(stored: string | null | undefined): {
  uiMode: UiMode | null;
  text: string;
} {
  if (!stored) return { uiMode: null, text: "" };
  const match = stored.match(/^\[ui:(pomodoro|flowtime|notes|flashcards)\]\s*(.*)$/);
  if (match) {
    return { uiMode: match[1] as UiMode, text: match[2] };
  }
  return { uiMode: null, text: stored };
}

export function SessionView() {
  const [active, setActive] = useState<ActiveSessionSummary | null>(null);
  const [completion, setCompletion] = useState<SessionCompletionResult | null>(null);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);

  // Setup form state — only relevant when no session is active.
  const [selectedMode, setSelectedMode] = useState<UiMode>("pomodoro");
  const [duration, setDuration] = useState<number>(25);
  const [objective, setObjective] = useState("");
  const [subject, setSubject] = useState<string>("");
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const refreshActive = useCallback(async () => {
    try {
      const data = await sessions.active();
      setActive(data.active_session);
      // Mirror into the global signal so palette + sidebar agree with
      // whatever this view just decided.
      if (data.active_session) {
        setActiveSession({
          id: data.active_session.id,
          objective: (data.active_session.objective || "").replace(
            /^\[ui:[a-z]+\]\s*/,
            ""
          )
        });
      } else {
        setActiveSession(null);
      }
    } catch {
      // Intentionally swallow — network error shouldn't block the setup
      // flow. User will see stale state until next refresh.
    }
  }, []);

  const refreshSubjects = useCallback(async () => {
    try {
      const data = await library.subjects();
      setSubjects(data.subjects);
    } catch {
      setSubjects([]);
    }
  }, []);

  useEffect(() => {
    void refreshActive();
    void refreshSubjects();
    const onFocus = () => void refreshActive();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshActive, refreshSubjects]);

  // If the active session was started via this view, decode the UI-mode
  // prefix so the rendered body matches what the user picked.
  const activeDecoded = useMemo(() => decodeObjective(active?.objective), [active]);
  const activeUiMode: UiMode = useMemo(() => {
    if (!active) return selectedMode;
    // Backend mode is a reasonable fallback when no prefix is present
    // (session started outside this view).
    if (activeDecoded.uiMode) return activeDecoded.uiMode;
    if (active.mode === "retrieval_practice") return "flashcards";
    if (active.mode === "mixed") return "flowtime";
    return "pomodoro";
  }, [active, activeDecoded, selectedMode]);

  const begin = async (event?: JSX.TargetedEvent<HTMLFormElement, Event>) => {
    event?.preventDefault();
    if (starting) return;
    const cleanObjective = objective.trim();
    if (!cleanObjective) {
      setStartError("Give the session an objective before starting.");
      return;
    }
    setStarting(true);
    setStartError(null);
    try {
      await sessions.start({
        objective: encodeObjective(selectedMode, cleanObjective),
        mode: UI_TO_BACKEND_MODE[selectedMode],
        duration_minutes: selectedMode === "flowtime" || selectedMode === "flashcards" ? 0 : duration,
        source_scope: subject ? [subject] : undefined
      });
      setCompletion(null);
      setCompletionError(null);
      await refreshActive();
    } catch (caught) {
      setStartError((caught as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const endSession = async () => {
    if (!active || ending) return;
    setEnding(true);
    setCompletionError(null);
    try {
      const result = await sessions.complete(active.id);
      setCompletion(result);
      setActive(null);
      setActiveSession(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        // Already ended (another tab). Treat as silent completion.
        setActive(null);
        setActiveSession(null);
      } else {
        setCompletionError(
          caught instanceof Error
            ? caught.message
            : "Could not end session. Try again."
        );
      }
    } finally {
      setEnding(false);
    }
  };

  return (
    <div className={styles.wrap}>
      <Header />
      {completion ? (
        <CompletionPanel
          result={completion}
          onDismiss={() => setCompletion(null)}
          onStartAnother={() => setCompletion(null)}
        />
      ) : null}
      {active ? (
        <ActiveBody
          active={active}
          uiMode={activeUiMode}
          decodedObjective={activeDecoded.text || active.objective}
          ending={ending}
          error={completionError}
          onEnd={() => void endSession()}
        />
      ) : (
        <SetupForm
          subjects={subjects}
          selectedMode={selectedMode}
          onSelectMode={setSelectedMode}
          duration={duration}
          onDuration={setDuration}
          objective={objective}
          onObjective={setObjective}
          subject={subject}
          onSubject={setSubject}
          starting={starting}
          error={startError}
          onBegin={(event) => void begin(event)}
        />
      )}
    </div>
  );
}

// ---------- Header ----------

function Header() {
  return (
    <header className={styles.header}>
      <span className={styles.eyebrow}>Session engine</span>
      <h1 className={styles.title}>Enter deep work</h1>
      <p className={styles.subtitle}>
        Pick a mode, set an objective, and start. Einstein tracks the session
        and surfaces mastery deltas when you end.
      </p>
    </header>
  );
}

// ---------- Setup form ----------

interface SetupFormProps {
  subjects: SubjectSummary[];
  selectedMode: UiMode;
  onSelectMode: (mode: UiMode) => void;
  duration: number;
  onDuration: (minutes: number) => void;
  objective: string;
  onObjective: (value: string) => void;
  subject: string;
  onSubject: (value: string) => void;
  starting: boolean;
  error: string | null;
  onBegin: (event: JSX.TargetedEvent<HTMLFormElement, Event>) => void;
}

function SetupForm({
  subjects,
  selectedMode,
  onSelectMode,
  duration,
  onDuration,
  objective,
  onObjective,
  subject,
  onSubject,
  starting,
  error,
  onBegin
}: SetupFormProps) {
  const showDuration = selectedMode === "pomodoro" || selectedMode === "notes";
  return (
    <form onSubmit={onBegin} className={styles.setup}>
      <section>
        <h2 className={styles.sectionHeading}>Choose a mode</h2>
        <div className={styles.modeGrid}>
          {MODES.map((mode) => (
            <ModeTile
              key={mode.id}
              mode={mode}
              selected={selectedMode === mode.id}
              onSelect={() => onSelectMode(mode.id as UiMode)}
            />
          ))}
        </div>
      </section>

      <section>
        <h2 className={styles.sectionHeading}>Session setup</h2>
        <div className={styles.setupGrid}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Subject (optional)</span>
            <select
              className={styles.select}
              value={subject}
              onChange={(event) =>
                onSubject((event.currentTarget as HTMLSelectElement).value)
              }
            >
              <option value="">No subject scope</option>
              {subjects.map((s) => (
                <option key={s.subject_name} value={s.subject_name}>
                  {s.subject_name} ({s.source_count})
                </option>
              ))}
            </select>
          </label>
          {showDuration && (
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Focus duration</span>
              <div className={styles.durationRow}>
                {DURATIONS.map((minutes) => (
                  <button
                    key={minutes}
                    type="button"
                    className={[
                      styles.durationChip,
                      minutes === duration ? styles.durationChipSelected : ""
                    ].join(" ")}
                    onClick={() => onDuration(minutes)}
                  >
                    {minutes}
                    <span className={styles.durationUnit}>m</span>
                  </button>
                ))}
              </div>
            </label>
          )}
          <label className={[styles.field, styles.fieldWide].join(" ")}>
            <span className={styles.fieldLabel}>Objective</span>
            <input
              type="text"
              className={styles.input}
              value={objective}
              onInput={(event) =>
                onObjective((event.currentTarget as HTMLInputElement).value)
              }
              placeholder="e.g. Cover chapter 7 — bond valuation"
            />
          </label>
        </div>
      </section>

      {error && <div className={styles.formError}>{error}</div>}

      <div className={styles.setupFooter}>
        <button
          type="submit"
          className={styles.primaryBtn}
          disabled={starting || objective.trim().length === 0}
        >
          {starting ? "Starting…" : "Begin session"}
          <Icon name="arrow-right" size={14} />
        </button>
      </div>
    </form>
  );
}

// ---------- Active body ----------

interface ActiveBodyProps {
  active: ActiveSessionSummary;
  uiMode: UiMode;
  decodedObjective: string;
  ending: boolean;
  error: string | null;
  onEnd: () => void;
}

function ActiveBody({
  active,
  uiMode,
  decodedObjective,
  ending,
  error,
  onEnd
}: ActiveBodyProps) {
  const timerMode = uiMode === "pomodoro" ? "countdown" : "countup";
  const targetMinutes = active.duration_minutes > 0 ? active.duration_minutes : 25;
  const modeLabel =
    uiMode === "pomodoro"
      ? "focus"
      : uiMode === "flowtime"
      ? "flow"
      : uiMode === "notes"
      ? "writing"
      : "review";

  return (
    <div className={styles.active}>
      <div className={styles.activeHero}>
        <TimerRing
          startedAt={active.started_at}
          targetMinutes={targetMinutes}
          mode={timerMode}
          modeLabel={modeLabel}
        />
        <div className={styles.activeInfo}>
          <span className={styles.activeEyebrow}>Active session</span>
          <h2 className={styles.activeObjective}>{decodedObjective || "Deep work"}</h2>
          <span className={styles.activeMeta}>
            {uiMode} · {active.duration_minutes > 0 ? `planned ${active.duration_minutes} min` : "open-ended"}
          </span>
          <div className={styles.activeControls}>
            <button
              type="button"
              className={styles.endBtn}
              onClick={onEnd}
              disabled={ending}
            >
              {ending ? "Ending…" : "End session"}
            </button>
          </div>
          {error && <div className={styles.inlineError}>{error}</div>}
        </div>
      </div>

      {uiMode === "notes" && (
        <NotesWorkspace sessionId={active.id} sessionObjective={decodedObjective} />
      )}

      {uiMode === "flashcards" && <FlashcardsPanel />}
    </div>
  );
}

function FlashcardsPanel() {
  return (
    <div className={styles.flashcardsPanel}>
      <div className={styles.flashcardsEyebrow}>Flashcards mode</div>
      <p className={styles.flashcardsCopy}>
        Jump into the SRS review queue. Session time keeps running in the
        background; come back here to end when you're done.
      </p>
      <button
        type="button"
        className={styles.secondaryBtn}
        onClick={() => navigateTo("/study")}
      >
        Open review queue
        <Icon name="arrow-right" size={14} />
      </button>
    </div>
  );
}

// ---------- Completion panel ----------

interface CompletionPanelProps {
  result: SessionCompletionResult;
  onDismiss: () => void;
  onStartAnother: () => void;
}

function CompletionPanel({ result, onDismiss, onStartAnother }: CompletionPanelProps) {
  const deltaPct = Math.round(result.mastery_delta * 100);
  const deltaLabel = deltaPct === 0 ? "±0%" : deltaPct > 0 ? `+${deltaPct}%` : `${deltaPct}%`;
  return (
    <section className={styles.completion} aria-label="Session complete">
      <header className={styles.completionHeader}>
        <span className={styles.eyebrow}>Session complete</span>
        <span
          className={[
            styles.deltaChip,
            deltaPct >= 0 ? styles.deltaChipPos : styles.deltaChipNeg
          ].join(" ")}
        >
          Mastery {deltaLabel}
        </span>
      </header>
      <p className={styles.completionLine}>{result.revision_recommendation}</p>
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
      <div className={styles.completionFooter}>
        <button type="button" className={styles.primaryBtn} onClick={onStartAnother}>
          Start another session
        </button>
        <button type="button" className={styles.secondaryBtn} onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </section>
  );
}
