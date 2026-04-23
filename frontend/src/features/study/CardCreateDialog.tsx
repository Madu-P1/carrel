import { useEffect, useId, useRef, useState } from "preact/hooks";

import { Button, Dialog, Stack, Text } from "@/design-system";
import { study, type SrsCard } from "@/services/api/endpoints";

import styles from "./CardCreateDialog.module.css";

interface CardCreateDialogProps {
  open: boolean;
  /** Subject the Manage view is currently filtering by, if any. Shown in the
   *  dialog as context but not sent to the server — v1 creates orphan cards;
   *  a later iteration will let users pick a concept under this subject. */
  activeSubject: string | null;
  onClose: () => void;
  onCreated: (card: SrsCard) => void;
}

/**
 * "New card" dialog for the Manage Cards view.
 *
 * v1 intentionally ships without a concept/subject picker:
 *   - The server allows orphan cards (concept_id null) and list_cards now
 *     LEFT JOINs so they surface in the "All subjects" filter.
 *   - A concept picker needs an /api/srs/concepts endpoint and a subject-
 *     filtered dropdown that is its own UX question (search? grouped?
 *     "create new" affordance?). Parking that for a follow-up so the
 *     simplest useful thing ships first.
 *
 * Enter in the Front field drops to Back; ⌘Enter submits from either field.
 * Esc is handled by the Dialog primitive itself.
 */
export function CardCreateDialog({ open, activeSubject, onClose, onCreated }: CardCreateDialogProps) {
  const frontId = useId();
  const backId = useId();
  const [front, setFront] = useState("");
  const [back, setBack] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const backRef = useRef<HTMLTextAreaElement | null>(null);

  // Reset form every time the dialog opens so reopening after a success
  // doesn't show the previous card's text. Closing doesn't reset — the
  // user may want to reopen and retry after fixing a connectivity error.
  useEffect(() => {
    if (open) {
      setFront("");
      setBack("");
      setError(null);
    }
  }, [open]);

  const canSubmit = front.trim().length > 0 && back.trim().length > 0 && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const { card } = await study.createCard({ front, back });
      onCreated(card);
      onClose();
    } catch (err) {
      setError((err as Error).message || "Could not create the card. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  // Key bindings:
  //   Enter on Front → move focus to Back (no submit, avoids accidental saves
  //     from muscle-memory typists).
  //   ⌘Enter / Ctrl+Enter on either field → submit.
  const handleFrontKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !(e.metaKey || e.ctrlKey) && !e.shiftKey) {
      e.preventDefault();
      backRef.current?.focus();
      return;
    }
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const handleBackKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  return (
    <Dialog
      actions={
        <Stack direction="horizontal" gap={2}>
          <Button onClick={onClose} variant="secondary">
            Cancel
          </Button>
          <Button disabled={!canSubmit} isLoading={submitting} onClick={() => void handleSubmit()}>
            Create card
          </Button>
        </Stack>
      }
      description={
        activeSubject
          ? `The card will appear under "All subjects". Subject linking is coming next.`
          : "A blank flashcard. Add the prompt on the front and the answer on the back."
      }
      onClose={onClose}
      open={open}
      title="New flashcard"
    >
      <Stack gap={4}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor={frontId}>
            Front
            <Text tone="tertiary" variant="caption">
              The question or prompt. Enter moves to the back.
            </Text>
          </label>
          <textarea
            className={styles.textarea}
            id={frontId}
            onInput={(e) => setFront((e.currentTarget as HTMLTextAreaElement).value)}
            onKeyDown={handleFrontKeyDown}
            placeholder="e.g. What is the difference between a coupon rate and a yield?"
            rows={3}
            value={front}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor={backId}>
            Back
            <Text tone="tertiary" variant="caption">
              The answer you want to recall. Cmd+Enter to save.
            </Text>
          </label>
          <textarea
            className={styles.textarea}
            id={backId}
            onInput={(e) => setBack((e.currentTarget as HTMLTextAreaElement).value)}
            onKeyDown={handleBackKeyDown}
            placeholder="e.g. The coupon rate is fixed at issuance; the yield reflects the current market price."
            ref={backRef}
            rows={5}
            value={back}
          />
        </div>

        {error ? (
          <Text role="alert" tone="danger" variant="caption">
            {error}
          </Text>
        ) : null}
      </Stack>
    </Dialog>
  );
}
