import { useState } from "preact/hooks";

import { Badge, Stack, Text, toast } from "@/design-system";
import { browserTimeZone } from "./utils/timezone";
import { AddFeedDialog } from "./components/AddFeedDialog";
import { EmptyPlanState } from "./components/EmptyPlanState";
import { FeedList } from "./components/FeedList";
import { WeekTimeGrid } from "./components/WeekTimeGrid";
import { usePlan } from "./hooks/usePlan";
import type { CalendarFeed } from "./api/calendarApi";
import styles from "./PlanView.module.css";

/**
 * Plan home — the cockpit-style view of the user's week with the
 * coach's suggestions overlaid in their proposed time slots.
 *
 * Layout:
 *   [ eyebrow + heading + TZ pill + freshening hint ]
 *   [ FeedList ]                          ← always visible (compact)
 *   [ WeekTimeGrid OR EmptyPlanState ]    ← grid when feeds; empty otherwise
 *
 * The WeekTimeGrid is the primary view — events placed at their actual
 * time of day so free blocks (where coach suggestions land) read
 * visually obvious. Empty-state collapses the heavy time grid in
 * favor of an inviting "connect a calendar" card.
 */
export function PlanView() {
  const {
    events,
    suggestions,
    feeds,
    isFreshening,
    loading,
    error,
    addFeed,
    removeFeed,
    syncFeed,
    acceptSuggestion,
    dismissSuggestion,
    // restoreSuggestion is wired in the hook + backend; the UI hook for
    // it is the toast-action-button which the Toast primitive doesn't
    // expose yet. Reach for it when that lands.
  } = usePlan();

  const [addOpen, setAddOpen] = useState(false);

  const handleSync = async (feedId: string) => {
    try {
      const result = await syncFeed(feedId);
      if (result.status === "error") {
        toast.error("Sync didn't complete", result.error || "Try again or check the URL.");
      } else if (result.status === "not_modified") {
        toast.info("No changes since last sync");
      } else {
        toast.success(
          "Synced",
          `${result.items_seen} event${result.items_seen === 1 ? "" : "s"} pulled.`
        );
      }
    } catch (caught) {
      toast.error("Sync failed", (caught as Error).message);
    }
  };

  const handleDelete = async (feed: CalendarFeed) => {
    if (
      !window.confirm(
        `Remove "${feed.label}"? Events from this feed will be cleared from your plan.`
      )
    ) {
      return;
    }
    try {
      await removeFeed(feed.id);
      toast.info(`Removed "${feed.label}"`);
    } catch (caught) {
      toast.error("Could not remove feed", (caught as Error).message);
    }
  };

  const handleDismissSuggestion = async (id: string) => {
    await dismissSuggestion(id);
    // Toast primitive doesn't accept action buttons today; the undo
    // affordance is wired through /api/plan/suggestions/{id}/restore
    // and ready for a follow-up that adds an action prop to Toast.
    // Until then: a clean info confirmation.
    toast.info("Suggestion dismissed");
  };

  const handleAcceptSuggestion = async (id: string) => {
    try {
      await acceptSuggestion(id);
      toast.success("Scheduled", "Coach suggestion added to your plan.");
    } catch (caught) {
      toast.error("Could not accept", (caught as Error).message);
    }
  };

  if (error) {
    return (
      <div className={styles.wrap}>
        <div className={styles.errorCard}>
          <strong>Could not load your plan.</strong>
          <Text tone="secondary">{error}</Text>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <Stack gap={2}>
          <Stack direction="horizontal" gap={2} align="center">
            <Badge tone="info">Plan</Badge>
            <span className={styles.tzPill} title="Times shown in your local time zone">
              {browserTimeZone()}
            </span>
            {isFreshening ? (
              <span className={styles.freshening}>Refreshing in background…</span>
            ) : null}
          </Stack>
          <Text as="h2" variant="display" weight="bold">
            Your week, source-grounded.
          </Text>
          <Text tone="secondary">
            Your calendar plus the tutor's read of where to focus.
            Scheduled study blocks appear inline at the time the coach proposes.
          </Text>
        </Stack>
      </header>

      <FeedList
        feeds={feeds}
        isFreshening={isFreshening}
        onSync={handleSync}
        onDelete={handleDelete}
        onAddFeed={() => setAddOpen(true)}
      />

      {feeds.length === 0 && !loading ? (
        <EmptyPlanState onAddFeed={() => setAddOpen(true)} />
      ) : (
        <WeekTimeGrid
          events={events}
          suggestions={suggestions}
          feeds={feeds}
          onAcceptSuggestion={handleAcceptSuggestion}
          onDismissSuggestion={handleDismissSuggestion}
        />
      )}

      <AddFeedDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSubmit={addFeed}
      />
    </div>
  );
}
