import { useCallback, useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";

import { Button, Icon, Stack, Text } from "@/design-system";
import { ApiError } from "@/services/api/client";
import {
  documents as documentsApi,
  library,
  sessions,
  study as studyApi,
  type ActiveSessionSummary,
  type DocumentRow,
  type SessionCompletionResult,
  type SrsSubjectSummary,
  type SubjectSummary,
} from "@/services/api/endpoints";
import { navigateTo, setActiveSession } from "@/app/shell/useAppShell";

import {
  ScopePill,
  type AskScopeValue,
} from "@/features/ask/components/ScopePill";

import { DurationChips } from "./components/DurationChips";
import { ModeCard, type ModeCardData } from "./components/ModeCard";
import { NotesWorkspace } from "./components/NotesWorkspace";
import { TimerRing } from "./components/TimerRing";
import styles from "./SessionView.module.css";

/**
 * Session engine — the cockpit.
 *
 * Three top-level states:
 *   1. setup      — no active session: render mode cards + setup grid
 *   2. active     — session running: timer ring + mode-specific body
 *   3. completed  — just-ended: mastery summary with revision recs
 *
 * Premium UI ship 4 rebuilt the setup branch: 2-column ModeCard grid,
 * 12-column controls grid, segmented DurationChips, ScopePill replaces
 * the native subject <select>, and a single size-lg primary CTA at the
 * bottom. Active + completed branches are unchanged for now (Ship 5
 * picks up Answer feed; the active body lives in its own ship).
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

const MODES: ModeCardData[] = [
  {
    id: "pomodoro",
    title: "Pomodoro",
    purpose: "Timed focus with a clear end.",
    iconName: "study",
  },
  {
    id: "flowtime",
    title: "Flowtime",
    purpose: "Open-ended. Stop when you're ready.",
    iconName: "sparkle",
  },
  {
    id: "notes",
    title: "Notes",
    purpose: "Writing-first; expand the draft from your sources.",
    iconName: "doc",
  },
  {
    id: "flashcards",
    title: "Flashcards",
    purpose: "Spaced repetition through what's due.",
    iconName: "ask",
  },
];

const DURATIONS = [15, 25, 45, 60];

const UI_TO_BACKEND_MODE: Record<UiMode, string> = {
  pomodoro: "focus_sprint",
  flowtime: "mixed",
  notes: "focus_sprint",
  flashcards: "retrieval_practice",
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

/**
 * ScopePill emits an AskScopeValue. The session start endpoint expects
 * `source_scope: string[] | undefined` — a list of subject names.
 *
 * Mapping:
 *   library          → undefined (no scope filter)
 *   subject(name)    → [name]
 *   document(docId)  → undefined for now (the backend filters by subject
 *                      not by docId; document scope still scopes the
 *                      retrieval correctly inside the active session
 *                      because the picker exposes the docTitle and the
 *                      tutor passes it through Ask). When backend gains
 *                      doc-level session scope, this returns [docId].
 */
function scopeToSourceList(scope: AskScopeValue): string[] | undefined {
  if (scope.kind === "subject" && scope.subjectName) {
    return [scope.subjectName];
  }
  return undefined;
}

/** SubjectSummary → SrsSubjectSummary adapter. ScopePill is shaped
 *  around the SRS view of subjects (card_count, due_count). For session
 *  setup we want the same picker UX but seeded from the broader
 *  library.subjects() list (every subject with sources, even if it has
 *  no cards yet). The adapter coerces shapes; due_count is unknown here
 *  and reads as 0, which the picker just doesn't display in our path. */
function subjectsForScope(
  librarySubjects: SubjectSummary[]
): SrsSubjectSummary[] {
  return librarySubjects
    .filter((s) => s.source_count > 0)
    .map((s) => ({
      subject_name: s.subject_name,
      card_count: s.flashcard_count ?? 0,
      due_count: 0,
    }));
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
  const [scope, setScope] = useState<AskScopeValue>({
    kind: "library",
    readiness: "ready",
  });
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [docs, setDocs] = useState<DocumentRow[]>([]);
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
          ),
        });
      } else {
        setActiveSession(null);
      }
    } catch {
      // Intentionally swallow — network error shouldn't block the setup
      // flow. User will see stale state until next refresh.
    }
  }, []);

  const refreshCorpus = useCallback(async () => {
    // Fetch library subjects + documents in parallel for the ScopePill.
    // Failures fall back to empty lists so the rest of the setup form
    // still works.
    try {
      const [subjectsRes, docsRes] = await Promise.all([
        library.subjects(),
        documentsApi.list().catch(() => [] as DocumentRow[]),
      ]);
      setSubjects(subjectsRes.subjects);
      setDocs(docsRes);
    } catch {
      setSubjects([]);
      setDocs([]);
    }
    // study.subjects() exists too but we prefer library.subjects() since
    // it covers every subject with sources, not only those with SRS cards.
    void studyApi;
  }, []);

  useEffect(() => {
    void refreshActive();
    void refreshCorpus();
    const onFocus = () => void refreshActive();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshActive, refreshCorpus]);

  // If the active session was started via this view, decode the UI-mode
  // prefix so the rendered body matches what the user picked.
  const activeDecoded = useMemo(() => decodeObjective(active?.objective), [active]);
  const activeUiMode: UiMode = useMemo(() => {
    if (!active) return selectedMode;
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
      setStartError("Tell us what you'd like to learn before starting.");
      return;
    }
    setStarting(true);
    setStartError(null);
    try {
      await sessions.start({
        objective: encodeObjective(selectedMode, cleanObjective),
        mode: UI_TO_BACKEND_MODE[selectedMode],
        duration_minutes:
          selectedMode === "flowtime" || selectedMode === "flashcards"
            ? 0
            : duration,
        source_scope: scopeToSourceList(scope),
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
            : "Could not end the session. Retry the end action."
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
          documents={docs}
          selectedMode={selectedMode}
          onSelectMode={setSelectedMode}
          duration={duration}
          onDuration={setDuration}
          objective={objective}
          onObjective={setObjective}
          scope={scope}
          onScope={setScope}
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
      <h1 className={styles.title}>Set the focus.</h1>
      <p className={styles.subtitle}>
        Pick the depth, set the corpus, name the objective. Carrel
        tracks the session and surfaces mastery deltas when you end.
      </p>
    </header>
  );
}

// ---------- Setup form ----------

interface SetupFormProps {
  subjects: SubjectSummary[];
  documents: DocumentRow[];
  selectedMode: UiMode;
  onSelectMode: (mode: UiMode) => void;
  duration: number;
  onDuration: (minutes: number) => void;
  objective: string;
  onObjective: (value: string) => void;
  scope: AskScopeValue;
  onScope: (next: AskScopeValue) => void;
  starting: boolean;
  error: string | null;
  onBegin: (event: JSX.TargetedEvent<HTMLFormElement, Event>) => void;
}

function SetupForm({
  subjects,
  documents,
  selectedMode,
  onSelectMode,
  duration,
  onDuration,
  objective,
  onObjective,
  scope,
  onScope,
  starting,
  error,
  onBegin,
}: SetupFormProps) {
  const showDuration = selectedMode === "pomodoro" || selectedMode === "notes";
  const scopeSubjects = useMemo(() => subjectsForScope(subjects), [subjects]);

  /*
   * Keyboard navigation for the ModeCard radiogroup.
   * WAI-ARIA radio group pattern: ArrowLeft/Right cycle, Home/End jump
   * to ends. Roving tabindex lives on the cards themselves (`tabIndex={
   * selected ? 0 : -1 }` in ModeCard). Here we move BOTH the value AND
   * focus so the visual ring follows the selection.
   */
  const handleModeKeyDown = (event: KeyboardEvent) => {
    const key = event.key;
    if (
      key !== "ArrowRight" &&
      key !== "ArrowLeft" &&
      key !== "Home" &&
      key !== "End"
    ) {
      return;
    }
    event.preventDefault();
    const idx = MODES.findIndex((m) => m.id === selectedMode);
    if (idx < 0) return;
    let nextIdx = idx;
    if (key === "ArrowRight") nextIdx = (idx + 1) % MODES.length;
    else if (key === "ArrowLeft")
      nextIdx = (idx - 1 + MODES.length) % MODES.length;
    else if (key === "Home") nextIdx = 0;
    else if (key === "End") nextIdx = MODES.length - 1;
    const next = MODES[nextIdx];
    onSelectMode(next.id as UiMode);
    // Move focus to the newly selected card so the focus ring tracks
    // the value. Cards expose role=radio so we can target them by role.
    const target = event.currentTarget as HTMLDivElement;
    const buttons = target.querySelectorAll<HTMLButtonElement>("[role=\"radio\"]");
    buttons?.[nextIdx]?.focus();
  };

  return (
    <form onSubmit={onBegin} className={styles.setup}>
      {/* --- Mode card grid ---------------------------------------------- */}
      <section className={styles.modeSection}>
        <span className={styles.sectionLabel}>Pick the depth</span>
        <div
          role="radiogroup"
          aria-label="Session mode"
          className={styles.modeGrid}
          onKeyDown={handleModeKeyDown}
        >
          {MODES.map((mode) => (
            <ModeCard
              key={mode.id}
              mode={mode}
              selected={selectedMode === mode.id}
              onSelect={() => onSelectMode(mode.id as UiMode)}
            />
          ))}
        </div>
      </section>

      {/* --- 12-col controls grid ---------------------------------------- */}
      <section className={styles.controls}>
        <div className={styles.controlRow}>
          <span className={styles.fieldLabel}>Set the corpus</span>
          <ScopePill
            value={scope}
            onChange={onScope}
            documents={documents}
            subjects={scopeSubjects}
          />
        </div>

        {showDuration ? (
          <div className={styles.controlRow}>
            <span className={styles.fieldLabel}>Set the timer</span>
            <DurationChips
              value={duration}
              options={DURATIONS}
              onChange={onDuration}
            />
          </div>
        ) : null}

        <label className={styles.objectiveRow}>
          <span className={styles.fieldLabel}>What would you like to learn?</span>
          <input
            type="text"
            className={styles.objectiveInput}
            value={objective}
            onInput={(event) =>
              onObjective((event.currentTarget as HTMLInputElement).value)
            }
            placeholder="e.g. Cover chapter 7 — bond valuation"
            autoComplete="off"
          />
        </label>
      </section>

      {error ? (
        <div className={styles.formError} role="alert">
          {error}
        </div>
      ) : null}

      {/* --- CTA row ------------------------------------------------------ */}
      <div className={styles.ctaRow}>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          className={styles.ctaButton}
          disabled={starting || objective.trim().length === 0}
          isLoading={starting}
        >
          <span className={styles.ctaLabel}>
            {starting ? "Starting…" : "Start focused study session"}
          </span>
          {!starting ? (
            <Icon name="arrow-right" size={14} />
          ) : null}
        </Button>
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
  onEnd,
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
          <h2 className={styles.activeObjective}>
            {decodedObjective || "Deep work"}
          </h2>
          <span className={styles.activeMeta}>
            {uiMode} · {active.duration_minutes > 0
              ? `planned ${active.duration_minutes} min`
              : "open-ended"}
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
          {error ? <div className={styles.inlineError}>{error}</div> : null}
        </div>
      </div>

      {uiMode === "notes" ? (
        <NotesWorkspace sessionId={active.id} sessionObjective={decodedObjective} />
      ) : null}

      {uiMode === "flashcards" ? <FlashcardsPanel /> : null}
    </div>
  );
}

function FlashcardsPanel() {
  return (
    <div className={styles.flashcardsPanel}>
      <Stack gap={2}>
        <Text className={styles.flashcardsEyebrow} tone="tertiary">
          Flashcards mode
        </Text>
        <p className={styles.flashcardsCopy}>
          Jump into the SRS review queue. Session time keeps running in the
          background; come back here to end when you're done.
        </p>
        <Button
          onClick={() => navigateTo("/study")}
          variant="secondary"
        >
          <span>Open review queue</span>
          <Icon name="arrow-right" size={14} />
        </Button>
      </Stack>
    </div>
  );
}

// ---------- Completion panel ----------

interface CompletionPanelProps {
  result: SessionCompletionResult;
  onDismiss: () => void;
  onStartAnother: () => void;
}

function CompletionPanel({
  result,
  onDismiss,
  onStartAnother,
}: CompletionPanelProps) {
  const deltaPct = Math.round(result.mastery_delta * 100);
  const deltaLabel =
    deltaPct === 0 ? "±0%" : deltaPct > 0 ? `+${deltaPct}%` : `${deltaPct}%`;
  // Three-way tone, not two. Treating ±0% as "positive" produced a
  // triumphant green chip on sessions where the user made no progress —
  // a tone clash with the actual number. A neutral chip communicates
  // "session done, no movement" honestly.
  const deltaChipClass =
    deltaPct > 0
      ? styles.deltaChipPos
      : deltaPct < 0
        ? styles.deltaChipNeg
        : styles.deltaChipNeutral;
  return (
    <section className={styles.completion} aria-label="Session complete">
      <header className={styles.completionHeader}>
        <span className={styles.eyebrow}>Session complete</span>
        <span className={[styles.deltaChip, deltaChipClass].join(" ")}>
          Mastery {deltaLabel}
        </span>
      </header>
      <p className={styles.completionLine}>{result.revision_recommendation}</p>
      {result.weak_concepts.length > 0 ? (
        <div className={styles.chipRow}>
          {result.weak_concepts.map((concept) => (
            <span key={concept} className={styles.weakChip}>
              {concept}
            </span>
          ))}
        </div>
      ) : null}
      {result.stretch_question ? (
        <p className={styles.stretch}>
          <span className={styles.stretchLabel}>Stretch · </span>
          {result.stretch_question}
        </p>
      ) : null}
      <div className={styles.completionFooter}>
        <Button onClick={onStartAnother} variant="primary">
          Start another session
        </Button>
        <Button onClick={onDismiss} variant="ghost">
          Dismiss
        </Button>
      </div>
    </section>
  );
}
