import type { JSX } from "preact";
import { useState } from "preact/hooks";

import { Button, Dialog, Icon, Input, Stack, Text } from "@/design-system";

import type { CalendarFeedCreatedResponse, CalendarIcsUploadResponse } from "../api/calendarApi";

import styles from "./AddFeedDialog.module.css";

interface AddFeedDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (input: { label: string; url: string; color: string }) => Promise<CalendarFeedCreatedResponse>;
  onUploadIcs: (input: { label: string; file: File; color: string }) => Promise<CalendarIcsUploadResponse>;
}

type AddMode = "url" | "file";
type AddResult =
  | { kind: "ok"; response: CalendarFeedCreatedResponse | CalendarIcsUploadResponse }
  | { kind: "error"; message: string }
  | null;

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
export function AddFeedDialog({ open, onClose, onSubmit, onUploadIcs }: AddFeedDialogProps) {
  const [mode, setMode] = useState<AddMode>("url");
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  // DEFAULT_COLORS is a non-empty const array; [0] is always defined,
  // hence the `!` (noUncheckedIndexedAccess widens to `string | undefined`).
  const [color, setColor] = useState(DEFAULT_COLORS[0]!);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AddResult>(null);

  const handleSubmit = async (
    event: JSX.TargetedEvent<HTMLFormElement, Event>
  ) => {
    event.preventDefault();
    if (submitting) return;
    if (!label.trim()) return;
    if (mode === "url" && !url.trim()) return;
    if (mode === "file" && !file) return;

    setSubmitting(true);
    setResult(null);
    try {
      const response =
        mode === "file" && file
          ? await onUploadIcs({
              label: label.trim(),
              file,
              color,
            })
          : await onSubmit({
              label: label.trim(),
              url: url.trim(),
              color,
            });
      setResult({ kind: "ok", response });
    } catch (caught) {
      // ApiError surfaces { detail: { reason, message } } from our
      // backend; fall back to .message if shape differs.
      const body = (caught as { body?: { detail?: unknown } }).body;
      const detail =
        typeof body?.detail === "string"
          ? body.detail
          : typeof body?.detail === "object" && body.detail && "message" in body.detail
            ? String((body.detail as { message?: unknown }).message ?? "")
            : "";
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
    setMode("url");
    setLabel("");
    setUrl("");
    setFile(null);
    setColor(DEFAULT_COLORS[0]!);
    setResult(null);
    onClose();
  };

  const canSubmit = label.trim() && (mode === "url" ? url.trim() : file);
  const uploadedCount =
    result?.kind === "ok" && "items_seen" in result.response ? result.response.items_seen : null;

  return (
    <Dialog open={open} onClose={handleClose} title="Add calendar">
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.modeRow} role="tablist" aria-label="Calendar import type">
          <button
            type="button"
            className={[styles.modeButton, mode === "url" ? styles.modeButtonActive : ""]
              .filter(Boolean)
              .join(" ")}
            aria-pressed={mode === "url"}
            onClick={() => {
              setMode("url");
              setResult(null);
            }}
          >
            iCal URL
          </button>
          <button
            type="button"
            className={[styles.modeButton, mode === "file" ? styles.modeButtonActive : ""]
              .filter(Boolean)
              .join(" ")}
            aria-pressed={mode === "file"}
            onClick={() => {
              setMode("file");
              setResult(null);
            }}
          >
            ICS file
          </button>
        </div>

        <Input
          label="Name"
          placeholder={mode === "file" ? "e.g. Apple Calendar" : "e.g. ESCP Blackboard"}
          value={label}
          onInput={(e) => setLabel((e.currentTarget as HTMLInputElement).value)}
          // Modal-on-open auto-focus pattern — first field of a form the
          // user explicitly opened. Standard dialog UX.
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus
          required
        />
        {mode === "url" ? (
          <Input
            label="iCal URL"
            placeholder="https://learn.escp.eu/webapps/calendar/icalendar/..."
            helpText="Find this in your calendar provider's 'Get external link' or 'Subscribe' settings."
            value={url}
            onInput={(e) => setUrl((e.currentTarget as HTMLInputElement).value)}
            required
          />
        ) : (
          <label className={styles.fileField}>
            <span className={styles.fileLabel}>ICS file</span>
            <input
              className={styles.fileInput}
              type="file"
              accept=".ics,text/calendar"
              required
              onChange={(event) => {
                const selected = (event.currentTarget as HTMLInputElement).files?.[0] ?? null;
                setFile(selected);
                setResult(null);
              }}
            />
            <span className={styles.fileHelp}>
              Export from Apple Calendar, then choose the resulting .ics file.
            </span>
          </label>
        )}
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
              Imported {uploadedCount !== null
                ? `${uploadedCount} event${uploadedCount === 1 ? "" : "s"}.`
                : result.response.feed.consecutive_failures === 0
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
            disabled={submitting || !canSubmit}
            isLoading={submitting}
            leadingIcon={<Icon name="plus" size={14} />}
          >
            {mode === "file" ? "Import file" : "Add feed"}
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
