import { useState } from "preact/hooks";

import { Button, Dialog, Input, Stack, Text, toast } from "@/design-system";

import { planApi } from "../api/planApi";

interface AddDeadlineDialogProps {
  open: boolean;
  onClose: () => void;
  /** Called after a successful create so the parent can refetch the
   *  deadline rail (we don't pass the new id; the rail re-fetches as a
   *  whole rather than mutating its cache). */
  onAdded: () => void;
}

/**
 * Add a deadline directly: a label and a date-time. Bypasses the
 * "must be on the calendar" requirement; the backend lazy-creates a
 * per-user manual feed and writes the deadline there, so the existing
 * detector + coach pick it up unchanged.
 *
 * Uses native <input type="datetime-local"> for the date+time picker.
 * Reasons:
 *   - Already styled for the dark theme via the design system.
 *   - Returns a string in the user's local time zone with no
 *     dependency on a date-picker library.
 *   - We convert to UTC ISO 8601 before posting.
 */
export function AddDeadlineDialog({ open, onClose, onAdded }: AddDeadlineDialogProps) {
  const [label, setLabel] = useState("");
  const [whenLocal, setWhenLocal] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setLabel("");
    setWhenLocal("");
    setSubmitting(false);
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    const trimmedLabel = label.trim();
    if (!trimmedLabel || !whenLocal) {
      toast.error("Both fields required", "Add a label and a date.");
      return;
    }
    // <input type="datetime-local"> returns a naive local string like
    // "2026-05-09T17:30". new Date() interprets it in the user's local
    // tz; toISOString() then gives the UTC equivalent the backend wants.
    const utcIso = new Date(whenLocal).toISOString();
    setSubmitting(true);
    try {
      await planApi.createManualDeadline(trimmedLabel, utcIso);
      toast.success("Deadline added", `${trimmedLabel} now in your plan.`);
      onAdded();
      reset();
      onClose();
    } catch (caught) {
      toast.error("Could not add deadline", (caught as Error).message);
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      actions={
        <Stack direction="horizontal" gap={2}>
          <Button onClick={handleClose} variant="ghost">
            Cancel
          </Button>
          <Button
            isLoading={submitting}
            onClick={() => void handleSubmit()}
            variant="primary"
          >
            Add deadline
          </Button>
        </Stack>
      }
      description="The coach will start scheduling study time toward this deadline immediately."
      onClose={handleClose}
      open={open}
      title="Add a deadline"
    >
      <Stack gap={3}>
        <Stack gap={1}>
          <Text variant="caption" tone="tertiary">
            What's due?
          </Text>
          <Input
            autoFocus
            onInput={(e) =>
              setLabel((e.currentTarget as HTMLInputElement).value)
            }
            placeholder="Bio midterm"
            value={label}
          />
        </Stack>
        <Stack gap={1}>
          <Text variant="caption" tone="tertiary">
            When?
          </Text>
          <Input
            onInput={(e) =>
              setWhenLocal((e.currentTarget as HTMLInputElement).value)
            }
            type="datetime-local"
            value={whenLocal}
          />
        </Stack>
      </Stack>
    </Dialog>
  );
}
