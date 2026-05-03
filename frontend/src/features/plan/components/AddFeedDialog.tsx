import { useState } from "preact/hooks";
import type { JSX } from "preact";

import { Button, Dialog, Icon, Input, Stack, Text } from "@/design-system";
import type { CalendarFeedCreatedResponse } from "../api/calendarApi";
import styles from "./AddFeedDialog.module.css";

interface AddFeedDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (input: { label: string; url: string; color: string }) => Promise<CalendarFeedCreatedResponse>;
}

/**
 * "Add a calendar feed" flow. Three steps inside one dialog:
 *
 *   1. User pastes the URL + chooses a label + (optional) picks a color
 *   2. Submit → backend validates, persists, runs initial sync
 *   3. Show the result inline:
 *        - On success: "Imported N events from this feed."
 *        - On parse / fetch error: surface the masked error so the
 *          user can fix the URL or try a different export format.
 *
 * The submit response includes a masked URL echo. The raw feed URL
 * stays in the local secret store and is never displayed after submit.
 */
export function AddFeedDialog({ open, onClose, onSubmit }: AddFeedDialogProps) {
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [color, setColor] = useState(DEFAULT_COLORS[0]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<
    | { kind: "ok"; response: CalendarFeedCreatedResponse }
    | { kind: "error"; message: string }
    | null
  >(null);

  const handleSubmit = async (
    event: JSX.TargetedEvent<HTMLFormElement, Event>
  ) => {
    event.preventDefault();
    if (submitting) return;
    if (!label.trim() || !url.trim()) return;

    setSubmitting(true);
    setResult(null);
    try {
      const response = await onSubmit({
        label: label.trim(),
        url: url.trim(),
        color,
      });
      setResult({ kind: "ok", response });
    } catch (caught) {
      // ApiError surfaces { detail: { reason, message } } from our
      // backend; fall back to .message if shape differs.
      const detail = (caught as { body?: { detail?: { message?: string } } }).body?.detail
        ?.message;
      setResult({
        kind: "error",
        message: detail || (caught as Error).message || "Could not add feed.",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    if (submitting) return;
    setLabel("");
    setUrl("");
    setColor(DEFAULT_COLORS[0]);
    setResult(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} title="Add a calendar feed">
      <form onSubmit={handleSubmit} className={styles.form}>
        <Input
          label="Name"
          placeholder="e.g. ESCP Blackboard"
          value={label}
          onInput={(e) => setLabel((e.currentTarget as HTMLInputElement).value)}
          autoFocus
          required
        />
        <Input
          label="iCal URL"
          placeholder="https://learn.escp.eu/webapps/calendar/icalendar/..."
          helpText="Find this in your calendar provider's 'Get external link' or 'Subscribe' settings."
          value={url}
          onInput={(e) => setUrl((e.currentTarget as HTMLInputElement).value)}
          required
        />
        <fieldset className={styles.colorField}>
          <legend className={styles.colorLegend}>Color</legend>
          <div className={styles.colorRow}>
            {DEFAULT_COLORS.map((option) => (
              <button
                key={option}
                type="button"
                aria-label={`Color ${option}`}
                aria-pressed={color === option}
                className={[
                  styles.colorChip,
                  color === option ? styles.colorChipActive : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                style={{ background: option }}
                onClick={() => setColor(option)}
              />
            ))}
          </div>
        </fieldset>

        {result?.kind === "ok" ? (
          <div className={styles.resultOk}>
            <Text weight="semibold">
              Imported {result.response.feed.consecutive_failures === 0
                ? "successfully."
                : "with errors — see below."}
            </Text>
            <Text tone="tertiary" variant="caption">
              Stored as: {result.response.raw_url_echo}
            </Text>
            {result.response.feed.last_error ? (
              <Text tone="danger">{result.response.feed.last_error}</Text>
            ) : null}
          </div>
        ) : null}

        {result?.kind === "error" ? (
          <div className={styles.resultError}>
            <Text weight="semibold" tone="danger">
              Could not add this feed.
            </Text>
            <Text tone="secondary">{result.message}</Text>
          </div>
        ) : null}

        <Stack direction="horizontal" gap={2}>
          <Button
            type="submit"
            disabled={submitting || !label.trim() || !url.trim()}
            isLoading={submitting}
            leadingIcon={<Icon name="plus" size={14} />}
          >
            Add feed
          </Button>
          <Button type="button" variant="ghost" onClick={handleClose}>
            {result?.kind === "ok" ? "Done" : "Cancel"}
          </Button>
        </Stack>
      </form>
    </Dialog>
  );
}

// Same palette as WeekTimeGrid's fallback. Picked for distinguishability
// across themes without needing a color picker primitive.
const DEFAULT_COLORS = [
  "oklch(0.74 0.13 200)",
  "oklch(0.74 0.14 30)",
  "oklch(0.70 0.18 320)",
  "oklch(0.74 0.16 140)",
  "oklch(0.72 0.15 60)",
  "oklch(0.70 0.18 280)",
];
