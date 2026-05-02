import { useCallback, useEffect, useState } from "preact/hooks";

import { Badge, Button, Card, Icon, Spinner, Stack, Text } from "@/design-system";
import { study, type SrsDueCard, type SrsRating } from "@/services/api/endpoints";
import { friendlyError } from "@/services/api/errorMessages";
import { events } from "@/services/metrics/events";
import { useQuery } from "@/lib/query";

import { ManageCardsView } from "./ManageCardsView";
import styles from "./StudyView.module.css";

type Phase = "intro" | "front" | "back" | "done" | "error";
type Mode = "review" | "manage";

function useDueCardsQuery() {
  // Stable fetcher reference so the useQuery underlying createQuery doesn't
  // remount every render. Per-view identity; not shared across routes.
  const fetcher = useCallback(() => study.due(), []);
  return useQuery<{ cards: SrsDueCard[] }>(fetcher);
}

const RATINGS: Array<{ rating: SrsRating; label: string; tone: "danger" | "warning" | "success" | "info"; key: string }> = [
  { rating: "again", label: "Again", tone: "danger", key: "1" },
  { rating: "hard", label: "Hard", tone: "warning", key: "2" },
  { rating: "good", label: "Good", tone: "success", key: "3" },
  { rating: "easy", label: "Easy", tone: "info", key: "4" }
];

export function StudyView() {
  const { data, error, loading, refetch } = useDueCardsQuery();
  const [mode, setMode] = useState<Mode>("review");
  const [phase, setPhase] = useState<Phase>("intro");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  // When the user switches to Manage and back, we re-fetch due so any cards
  // they deleted disappear from the next review session.
  const enterManage = () => setMode("manage");
  const enterReview = () => {
    setMode("review");
    void refetch();
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

  const revealAnswer = () => {
    if (phase === "front") setPhase("back");
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
      if (phase === "front" && (event.code === "Space" || event.code === "Enter")) {
        event.preventDefault();
        revealAnswer();
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

  if (phase === "intro") {
    return (
      <div className={styles.wrap}>
        <Card padding="lg">
          <Stack className={styles.hero} gap={6}>
            <Stack gap={2}>
              <span className={styles.stateEyebrow}>
                {totalDue === 0
                  ? "Nothing due"
                  : `${totalDue} card${totalDue === 1 ? "" : "s"} due`}
              </span>
              <Text as="h1" className={styles.stateHeading}>
                {totalDue === 0 ? "You're caught up." : "Ready for review?"}
              </Text>
              <Text tone="secondary">
                {totalDue === 0
                  ? "No flashcards are due right now. Come back later or ingest more material in Library."
                  : "Answer each card, rate your recall, and the scheduler will space the next review."}
              </Text>
            </Stack>
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
  // Key the reveal body on phase+index so Preact remounts the animation
  // element on every card transition — keeps the reveal choreography
  // firing at the right time, even after a fast sequence.
  const revealKey = `reveal-${currentIndex}-${phase}`;

  return (
    <div className={styles.wrap}>
      <Stack gap={4}>
        <Stack direction="horizontal" className={styles.progress}>
          <Text tone="tertiary" variant="caption">
            Card {currentIndex + 1} of {total}
          </Text>
          <Text tone="tertiary" variant="caption">
            {completedCount} reviewed
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
        <Card padding="lg">
          <Stack gap={5}>
            <Stack gap={2}>
              <Text tone="tertiary" variant="caption">
                {currentCard.concept} · {currentCard.document_name}
              </Text>
              <Text as="p" variant="h1" weight="semibold">
                {currentCard.front}
              </Text>
            </Stack>
            {phase === "back" ? (
              <Stack gap={3} key={revealKey}>
                <div aria-hidden className={styles.revealDivider} />
                <Text as="p" className={styles.revealBody}>
                  {currentCard.back}
                </Text>
              </Stack>
            ) : null}
            <Stack direction="horizontal" gap={2} wrap>
              {phase === "front" ? (
                <Button
                  keyHint="Space"
                  leadingIcon={<Icon name="sparkle" />}
                  onClick={revealAnswer}
                >
                  Reveal the source-grounded answer
                </Button>
              ) : (
                RATINGS.map((r) => (
                  <Button
                    disabled={submitting}
                    key={r.rating}
                    onClick={() => void rateCard(r.rating)}
                    variant={r.rating === "good" ? "primary" : "secondary"}
                  >
                    <Badge tone={r.tone}>{r.key}</Badge>
                    &nbsp;{r.label}
                  </Button>
                ))
              )}
            </Stack>
          </Stack>
        </Card>
      </Stack>
    </div>
  );
}
