import { useMemo, useState } from "preact/hooks";

import { Button, Dialog, Stack, Text, showToast, toast } from "@/design-system";

import type { CalendarFeed } from "./api/calendarApi";
import type { PlanEvent } from "./api/planApi";
import { AddFeedDialog } from "./components/AddFeedDialog";
import { DeadlineRail } from "./components/DeadlineRail";
import { EmptyPlanState } from "./components/EmptyPlanState";
import { EventDetailDialog } from "./components/EventDetailDialog";
import { FeedList } from "./components/FeedList";
import { WeekTimeGrid } from "./components/WeekTimeGrid";
import { usePlan } from "./hooks/usePlan";
import styles from "./PlanView.module.css";
import {
  browserTimeZone,
  formatWeekRange,
  shiftDaysLocal,
  todayMidnightLocal,
} from "./utils/timezone";

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
    uploadIcsFile,
    removeFeed,
    syncFeed,
    acceptSuggestion,
    dismissSuggestion,
    restoreSuggestion,
  } = usePlan();

  const [addOpen, setAddOpen] = useState(false);

  // Week navigation. weekStart is always midnight-local on a Monday-or-
  // today-equivalent anchor; the WeekTimeGrid renders 7 days from there.
  // Today by default; arrows shift by 7 days.
  const [weekStart, setWeekStart] = useState<Date>(() => todayMidnightLocal());
  const weekLabel = useMemo(
    () => formatWeekRange(weekStart.toISOString()),
    [weekStart],
  );
  const isThisWeek = useMemo(() => {
    const today = todayMidnightLocal();
    return weekStart.getTime() === today.getTime();
  }, [weekStart]);

  // Click-to-view event detail.
  const [selectedEvent, setSelectedEvent] = useState<PlanEvent | null>(null);

  // Feed delete confirmation. Replaced the previous window.confirm()
  // call with the design-system Dialog primitive so the experience
  // matches the Library delete flow and respects the dark theme.
  const [feedToDelete, setFeedToDelete] = useState<CalendarFeed | null>(null);
  const [deleteFeedLoading, setDeleteFeedLoading] = useState(false);

  const handleSync = async (feedId: string) => {
    try {
      const result = await syncFeed(feedId);
      if (result.status === "error") {
        toast.error("Sync didn't complete", result.error || "Re-run the sync, or check the feed URL.");
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

  const handleDelete = (feed: CalendarFeed) => {
    setFeedToDelete(feed);
  };

  const handleConfirmDeleteFeed = async () => {
    if (!feedToDelete) return;
    setDeleteFeedLoading(true);
    try {
      await removeFeed(feedToDelete.id);
      toast.info(`Removed "${feedToDelete.label}"`);
      setFeedToDelete(null);
    } catch (caught) {
      toast.error("Could not remove feed", (caught as Error).message);
    } finally {
      setDeleteFeedLoading(false);
    }
  };

  const handleCloseDeleteDialog = () => {
    if (deleteFeedLoading) return;
    setFeedToDelete(null);
  };

  const handleDismissSuggestion = async (id: string) => {
    try {
      await dismissSuggestion(id);
      showToast({
        title: "Suggestion dismissed",
        kind: "info",
        durationMs: 5000,
        action: {
          label: "Undo",
          onClick: () => {
            void restoreSuggestion(id)
              .then(() => toast.success("Suggestion restored"))
              .catch((caught) => toast.error("Could not restore", (caught as Error).message));
          },
        },
      });
    } catch (caught) {
      toast.error("Could not dismiss", (caught as Error).message);
    }
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
            <span className={styles.eyebrow}>Plan</span>
            <span className={styles.tzPill} title="Times shown in your local time zone">
              {browserTimeZone()}
            </span>
            {isFreshening ? (
              <span className={styles.freshening}>Refreshing in background…</span>
            ) : null}
          </Stack>
          <h1 className={styles.heading}>Your week, source-grounded.</h1>
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

      {feeds.length > 0 ? <DeadlineRail /> : null}

      {feeds.length === 0 && !loading ? (
        <EmptyPlanState onAddFeed={() => setAddOpen(true)} />
      ) : (
        <>
          <Stack
            direction="horizontal"
            gap={2}
            align="center"
            justify="between"
            className={styles.weekToolbar}
          >
            <Stack direction="horizontal" gap={2} align="center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setWeekStart((w) => shiftDaysLocal(w, -7))}
                aria-label="Previous week"
              >
                ‹
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setWeekStart((w) => shiftDaysLocal(w, 7))}
                aria-label="Next week"
              >
                ›
              </Button>
              <Button
                variant={isThisWeek ? "ghost" : "secondary"}
                size="sm"
                onClick={() => setWeekStart(todayMidnightLocal())}
                disabled={isThisWeek}
              >
                Today
              </Button>
            </Stack>
            <Text variant="caption" tone="secondary">{weekLabel}</Text>
          </Stack>
          <WeekTimeGrid
            events={events}
            suggestions={suggestions}
            feeds={feeds}
            onAcceptSuggestion={handleAcceptSuggestion}
            onDismissSuggestion={handleDismissSuggestion}
            onSelectEvent={setSelectedEvent}
            weekStart={weekStart}
          />
        </>
      )}

      <AddFeedDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSubmit={addFeed}
        onUploadIcs={uploadIcsFile}
      />

      <EventDetailDialog
        event={selectedEvent}
        feeds={feeds}
        onClose={() => setSelectedEvent(null)}
      />

      <Dialog
        actions={
          <Stack direction="horizontal" gap={2}>
            <Button onClick={handleCloseDeleteDialog} variant="ghost">
              Cancel
            </Button>
            <Button
              isLoading={deleteFeedLoading}
              onClick={() => void handleConfirmDeleteFeed()}
              variant="danger"
            >
              Remove feed
            </Button>
          </Stack>
        }
        description="Events from this feed will be cleared from your plan. The calendar source itself is unchanged."
        onClose={handleCloseDeleteDialog}
        open={feedToDelete !== null}
        title={feedToDelete ? `Remove "${feedToDelete.label}"?` : ""}
      >
        <Text tone="secondary">
          You can re-add the feed any time from the Add a feed dialog.
        </Text>
      </Dialog>
    </div>
  );
}
