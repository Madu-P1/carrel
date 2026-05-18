import { Button, Dialog, Stack, Text } from "@/design-system";

import type { CalendarFeed } from "../api/calendarApi";
import type { PlanEvent } from "../api/planApi";
import { formatTimeRange } from "../utils/timezone";

interface EventDetailDialogProps {
  /** Currently-selected event, or null when closed. The dialog is
   *  controlled — `event` drives both visibility and content so the
   *  parent doesn't have to coordinate two pieces of state. */
  event: PlanEvent | null;
  /** Lookup so we can show "Work calendar" instead of a raw feed_id. */
  feeds: CalendarFeed[];
  onClose: () => void;
}

/**
 * Read-only detail view for a calendar event.
 *
 * Phase 1 surfaces what we already store: title, time, location,
 * source feed, status. No edit affordance — events live in the
 * upstream Apple Calendar / Google Calendar / .ics file, not in
 * Carrel, so editing here would diverge from the source of truth.
 */
export function EventDetailDialog({ event, feeds, onClose }: EventDetailDialogProps) {
  const open = event !== null;
  const feed = event ? feeds.find((f) => f.id === event.feed_id) : null;
  const title = event?.summary?.trim() || "Untitled event";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={event ? formatTimeRange(event.start_at, event.end_at) : ""}
      actions={
        <Stack direction="horizontal" gap={2}>
          <Button onClick={onClose} variant="ghost">
            Close
          </Button>
        </Stack>
      }
    >
      {event ? (
        <Stack gap={3}>
          {event.location ? (
            <Stack gap={1}>
              <Text variant="caption" tone="secondary">Location</Text>
              <Text>{event.location}</Text>
            </Stack>
          ) : null}
          {feed ? (
            <Stack gap={1}>
              <Text variant="caption" tone="secondary">Source</Text>
              <Text>{feed.label}</Text>
            </Stack>
          ) : null}
          {event.status !== "confirmed" ? (
            <Stack gap={1}>
              <Text variant="caption" tone="secondary">Status</Text>
              <Text>{event.status === "tentative" ? "Tentative" : "Cancelled"}</Text>
            </Stack>
          ) : null}
          {event.timezone ? (
            <Stack gap={1}>
              <Text variant="caption" tone="secondary">Timezone</Text>
              <Text>{event.timezone}</Text>
            </Stack>
          ) : null}
        </Stack>
      ) : null}
    </Dialog>
  );
}
