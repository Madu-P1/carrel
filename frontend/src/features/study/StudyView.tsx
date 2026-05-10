import { useCallback, useEffect, useMemo, useState } from "preact/hooks";

import { Button, Card, Icon, Spinner, Stack, Text } from "@/design-system";
import {
  study,
  type SrsDueCard,
  type SrsRating,
  type SrsSubjectSummary,
} from "@/services/api/endpoints";
import { friendlyError } from "@/services/api/errorMessages";
import { events } from "@/services/metrics/events";
import { useQuery } from "@/lib/query";

import { FlipCard } from "./components/FlipCard";
import { RatingRow } from "./components/RatingRow";
import { SrsSubjectScopePill } from "./components/SrsSubjectScopePill";
import { StudyFocusOverlay } from "./components/StudyFocusOverlay";
import { ManageCardsView } from "./ManageCardsView";
import styles from "./StudyView.module.css";

type Phase = "intro" | "front" | "back" | "done" | "error";
type Mode = "review" | "manage";

const SUBJECT_SCOPE_STORAGE_KEY = "carrel.study.subjectScope";

function _readPersistedSubjectScope(): string | null {
  try {
    const value = window.localStorage.getItem(SUBJECT_SCOPE_STORAGE_KEY);
    return value && value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

function _persistSubjectScope(value: string | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(SUBJECT_SCOPE_STORAGE_KEY);
    } else {
      window.localStorage.setItem(SUBJECT_SCOPE_STORAGE_KEY, value);
    }
  } catch {
    /* localStorage unavailable (private mode etc.); scope just doesn't persist. */
  }
}

function useDueCardsQuery(subject: string | null) {
  // The fetcher closes over the current subject so the query
  // automatically refetches with the new filter when subject changes.
  // useCallback keeps the closure identity stable per-subject.
  const fetcher = useCallback(
    () => study.due({ subject: subject ?? undefined }),
    [subject],
  );
  return useQuery<{ cards: SrsDueCard[] }>(fetcher);
}

function useSrsSubjectsQuery() {
  const fetcher = useCallback(() => study.subjects(), []);
  return useQuery<{ subjects: SrsSubjectSummary[] }>(fetcher);
}

const RATINGS: Array<{ rating: SrsRating; label: string; key: string }> = [
  { rating: "again", label: "Again", key: "1" },
  { rating: "hard", label: "Hard", key: "2" },
  { rating: "good", label: "Good", key: "3" },
  { rating: "easy", label: "Easy", key: "4" }
];

const FOCUS_MODE_STORAGE_KEY = "carrel.study.focusMode";

function _readFocusMode(): boolean {
  try {
    return window.localStorage.getItem(FOCUS_MODE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function _persistFocusMode(value: boolean): void {
  try {
    if (value) window.localStorage.setItem(FOCUS_MODE_STORAGE_KEY, "1");
    else window.localStorage.removeItem(FOCUS_MODE_STORAGE_KEY);
  } catch {
    /* private-mode tab; preference just doesn't persist. */
  }
}

export function StudyView() {
  // Subject scope persists across sessions so the user's "Biology only"
  // preference survives reloads. Read it once on mount; future changes
  // route through the setter, which writes through to localStorage.
  const [subjectScope, setSubjectScopeState] = useState<string | null>(() =>
    _readPersistedSubjectScope(),
  );
  const setSubjectScope = useCallback((next: string | null) => {
    setSubjectScopeState(next);
    _persistSubjectScope(next);
  }, []);
  const { data, error, loading, refetch } = useDueCardsQuery(subjectScope);
  const subjectsQuery = useSrsSubjectsQuery();
  const [mode, setMode] = useState<Mode>("review");
  const [phase, setPhase] = useState<Phase>("intro");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  // Focus mode persists across sessions on the same machine — same
  // pattern as subjectScope. Only takes effect during phase=front|back;
  // toggling on/off mid-session is harmless.
  const [focusMode, setFocusModeState] = useState<boolean>(() => _readFocusMode());
  const setFocusMode = useCallback((next: boolean) => {
    setFocusModeState(next);
    _persistFocusMode(next);
  }, []);

  // When the user switches to Manage and back, we re-fetch due so any cards
  // they deleted disappear from the next review session. Also refetch the
  // subjects roll-up so the chip counts stay honest after a delete.
  const enterManage = () => setMode("manage");
  const enterReview = () => {
    setMode("review");
    void refetch();
    void subjectsQuery.refetch();
  };

  const cards = data.value?.cards ?? [];
  const currentCard: SrsDueCard | undefined = cards[currentIndex];

  const startSession = async () => {
    setCompletedCount(0);
    setCurrentIndex(0);
    setLastError(null);
    await refetch();
    const count = data.value?.cards.length ?? 0;
    if (count > 0) {
      void events.track("srs.review_started", { card_count: count }, "study");
    }
    setPhase(count === 0 ? "done" : "front");
  };

  // Bidirectional flip: front <-> back. The original `revealAnswer` was
  // one-way (front → back) and `onFlip` was nulled after reveal so the
  // user could not flip back to re-read the question. PR 1 of the
  // flashcards-focus plan replaces the one-way reveal with a toggle.
  // Rating gating still keys off `phase === "back"`, so a flipped-then-
  // back-then-flipped card cannot be rated until the user reveals
  // again.
  const togglePhase = () => {
    if (phase === "front") setPhase("back");
    else if (phase === "back") setPhase("front");
  };

  const rateCard = async (rating: SrsRating) => {
    if (!currentCard || submitting) return;
    setSubmitting(true);
    setLastError(null);
    try {
      await study.review(currentCard.id, rating);
      const nextIndex = currentIndex + 1;
      const reviewedCount = completedCount + 1;
      setCompletedCount((c) => c + 1);
      if (nextIndex >= cards.length) {
        void events.track("srs.review_completed", {
          card_count: reviewedCount,
          last_rating: rating
        }, "study");
        setPhase("done");
      } else {
        setCurrentIndex(nextIndex);
        setPhase("front");
      }
    } catch (e) {
      setLastError((e as Error).message);
      setPhase("error");
    } finally {
      setSubmitting(false);
    }
  };

  // Keyboard shortcuts during a session. Gated on review mode because the
  // component has an early return for manage mode further up — without this
  // guard the effect would register a listener while Manage was on screen
  // and try to dispatch reveal/rate on cards that aren't mounted.
  useEffect(() => {
    if (mode !== "review") return;
    const handler = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      // Space / Enter toggle in either direction now (was front-only before
      // PR 1 of flashcards-focus). The bidirectional flip lets users re-read
      // the question without losing session position.
      if ((phase === "front" || phase === "back") && (event.code === "Space" || event.code === "Enter")) {
        // Skip the toggle when focus is already on a rating button — Space
        // there should activate the button, not flip the card behind it.
        const target = event.target as HTMLElement | null;
        if (target?.closest("[data-rating]")) return;
        event.preventDefault();
        togglePhase();
        return;
      }
      if (phase === "back") {
        const hit = RATINGS.find((r) => r.key === event.key);
        if (hit) {
          event.preventDefault();
          void rateCard(hit.rating);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, phase, currentIndex, cards.length]);

  // Subjects roll-up; memoised so identity is stable across renders
  // when the payload didn't change. Used both by the cleanup effect
  // below and the intro screen's pill.
  const subjectsQueryData = subjectsQuery.data.value;
  const subjectsList = useMemo(
    () => subjectsQueryData?.subjects ?? [],
    [subjectsQueryData],
  );

  // Defensive: if a previously-saved subject was deleted, drop the
  // stale scope. Runs in an effect (not render) so we don't violate
  // React/Preact's render purity. Lives above the early returns to
  // keep the hook call order stable per Rules of Hooks.
  useEffect(() => {
    if (!subjectScope || !subjectsQueryData) return;
    const stillExists = subjectsList.some((s) => s.subject_name === subjectScope);
    if (!stillExists) setSubjectScope(null);
  }, [subjectScope, subjectsList, subjectsQueryData, setSubjectScope]);

  // Render branch: Manage mode swaps the UI for card management. The early
  // return lives below the hooks so the hook call order stays stable across
  // mode changes (Rules of Hooks).
  if (mode === "manage") {
    return (
      <div className={styles.wrap}>
        <Stack gap={3}>
          <Stack direction="horizontal" gap={2}>
            <Button variant="ghost" onClick={enterReview} leadingIcon={<Icon name="chevron-left" />}>
              Back to review
            </Button>
          </Stack>
          <ManageCardsView />
        </Stack>
      </div>
    );
  }

  if (loading.value && !data.value) {
    return (
      <div className={styles.wrap}>
        <Stack align="center" gap={3}>
          <Spinner size={24} />
          <Text tone="secondary">Loading your review queue…</Text>
        </Stack>
      </div>
    );
  }

  if (error.value && phase !== "error") {
    const friendly = friendlyError(error.value, { surface: "Review queue" });
    return (
      <div className={styles.wrap}>
        <Card padding="lg">
          <Stack gap={3}>
            <span className={styles.stateEyebrow}>{friendly.title}</span>
            <Text as="h1" className={styles.stateHeading}>
              Couldn't load the review queue.
            </Text>
            <Text tone="secondary">{friendly.detail}</Text>
            {friendly.recovery ? (
              <Text tone="tertiary">{friendly.recovery}</Text>
            ) : null}
            <Button onClick={() => void refetch()}>Reload the queue</Button>
          </Stack>
        </Card>
      </div>
    );
  }

  const totalDue = cards.length;
  // The scoped due count is what the user is about to start. The
  // unfiltered total — used as the All option's count in the scope
  // pill — comes from the subjects roll-up.
  const allDueCount = subjectsList.reduce(
    (sum, subject) => sum + (subject.due_count ?? 0),
    0,
  );

  if (phase === "intro") {
    return (
      <div className={styles.wrap}>
        <Card padding="lg">
          <Stack className={styles.hero} gap={6}>
            <Stack gap={2}>
              <span className={styles.stateEyebrow}>
                {totalDue === 0
                  ? "Nothing due"
                  : `${totalDue} card${totalDue === 1 ? "" : "s"} due${subjectScope ? ` in ${subjectScope}` : ""}`}
              </span>
              <Text as="h1" className={styles.stateHeading}>
                {totalDue === 0 ? "You're caught up." : "Ready for review?"}
              </Text>
              <Text tone="secondary">
                {totalDue === 0
                  ? subjectScope
                    ? `No ${subjectScope} cards are due right now. Pick a different scope or come back later.`
                    : "No flashcards are due right now. Come back later or ingest more material in Library."
                  : "Answer each card, rate your recall, and the scheduler will space the next review."}
              </Text>
            </Stack>
            <div className={styles.scopeRow}>
              <SrsSubjectScopePill
                value={subjectScope}
                subjects={subjectsList}
                onChange={(next) => {
                  setSubjectScope(next);
                  void refetch();
                }}
                allDueCount={allDueCount}
              />
            </div>
            <Stack direction="horizontal" gap={3} wrap>
              <Button
                disabled={totalDue === 0}
                leadingIcon={<Icon name="study" />}
                onClick={() => void startSession()}
              >
                Start a session
              </Button>
              <Button leadingIcon={<Icon name="command" />} onClick={() => void refetch()} variant="secondary">
                Refresh queue
              </Button>
              <Button leadingIcon={<Icon name="library" />} onClick={enterManage} variant="ghost">
                Manage cards
              </Button>
              <Button
                leadingIcon={<Icon name="focus" />}
                onClick={() => setFocusMode(!focusMode)}
                variant="ghost"
              >
                {focusMode ? "Focus mode: on" : "Focus mode: off"}
              </Button>
            </Stack>
          </Stack>
        </Card>
      </div>
    );
  }

  if (phase === "done") {
    return (
      <div className={styles.wrap}>
        <Card padding="lg">
          <Stack gap={4}>
            <span className={styles.stateEyebrow}>Session complete</span>
            <Text as="h1" className={styles.stateHeading}>
              Reviewed {completedCount} card{completedCount === 1 ? "" : "s"}.
            </Text>
            <Text tone="secondary">
              The scheduler has updated each card's next review date based on your ratings.
            </Text>
            <Stack direction="horizontal" gap={3} wrap>
              <Button onClick={() => setPhase("intro")} variant="secondary">
                Back to review queue
              </Button>
              <Button onClick={() => void startSession()}>Start another session</Button>
            </Stack>
          </Stack>
        </Card>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className={styles.wrap}>
        <Card padding="lg">
          <Stack gap={3}>
            <span className={styles.stateEyebrow}>Review not recorded</span>
            <Text as="h1" className={styles.stateHeading}>
              The rating didn't reach the scheduler.
            </Text>
            <Text tone="secondary">{lastError ?? "Unknown error"}</Text>
            <Button onClick={() => setPhase(currentCard ? "back" : "intro")}>
              Re-rate this card
            </Button>
          </Stack>
        </Card>
      </div>
    );
  }

  if (!currentCard) {
    return null;
  }

  // Progress bar fills by completedCount across the batch. We use
  // completedCount (not currentIndex) so a rate-then-advance animates the
  // bar in the same beat as the card swap. Total-card count (not due count)
  // means the bar reaches 100% exactly when the "session complete" screen
  // takes over.
  const total = cards.length;
  const progressFraction = total === 0 ? 0 : completedCount / total;

  const cardSubject = currentCard.subject_name ?? subjectScope ?? null;

  // The card body is identical in standard mode and focus mode — only
  // the surrounding chrome differs. Keying on currentIndex re-mounts
  // the FlipCard between cards so the slide-in animation fires fresh
  // each transition.
  const flipBody = (
    <FlipCard
      key={`flip-${currentIndex}`}
      flipped={phase === "back"}
      onFlip={togglePhase}
      front={
        <div className={styles.cardFace}>
          <span className={styles.cardEyebrow}>
            {currentCard.concept} · {currentCard.document_name}
          </span>
          <Text as="p" variant="h1" weight="semibold" className={styles.cardQuestion}>
            {currentCard.front}
          </Text>
          <span className={styles.cardHint}>
            Press space or click to reveal
          </span>
        </div>
      }
      back={
        <div className={styles.cardFace}>
          <span className={styles.cardEyebrow}>
            {currentCard.concept} · {currentCard.document_name}
          </span>
          <Text as="p" className={styles.cardAnswer}>
            {currentCard.back}
          </Text>
        </div>
      }
    />
  );

  const ratingsRow =
    phase === "back" ? (
      <RatingRow
        ratings={RATINGS}
        submitting={submitting}
        onSelect={(rating) => void rateCard(rating)}
      />
    ) : null;

  const sessionContent = (
    <Stack gap={4}>
      {!focusMode ? (
        <>
          <Stack direction="horizontal" className={styles.progress}>
            <Text tone="tertiary" variant="caption">
              Card {currentIndex + 1} of {total}
            </Text>
            <Text tone="tertiary" variant="caption">
              {completedCount} reviewed
              {subjectScope ? ` · ${subjectScope}` : ""}
            </Text>
          </Stack>
          <div
            aria-label={`Session progress, ${completedCount} of ${total} cards reviewed`}
            aria-valuemax={total}
            aria-valuemin={0}
            aria-valuenow={completedCount}
            className={styles.progressBar}
            role="progressbar"
          >
            <div
              className={styles.progressBarFill}
              style={{ transform: `scaleX(${progressFraction})` }}
            />
          </div>
        </>
      ) : null}
      <div className={styles.cardArea}>{flipBody}</div>
      {ratingsRow}
      {!focusMode ? (
        <div className={styles.sessionFooter}>
          <Button
            variant="ghost"
            size="sm"
            leadingIcon={<Icon name="sparkle" size={12} />}
            onClick={() => setFocusMode(true)}
          >
            Focus mode
          </Button>
        </div>
      ) : null}
    </Stack>
  );

  if (focusMode) {
    return (
      <StudyFocusOverlay
        open={true}
        onClose={() => setFocusMode(false)}
        progress={`Card ${currentIndex + 1} of ${total}`}
        scope={cardSubject}
      >
        {sessionContent}
      </StudyFocusOverlay>
    );
  }

  return <div className={styles.wrap}>{sessionContent}</div>;
}
