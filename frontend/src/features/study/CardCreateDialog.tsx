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
  /** Optional document linkage. Set by the Reader so the new card
   *  remembers which PDF it was authored from. */
  docId?: string;
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
export function CardCreateDialog({ open, activeSubject, docId, onClose, onCreated }: CardCreateDialogProps) {
  const frontId = useId();
  const backId = useId();
  // PR 5.1 (ADR 0002) — kind toggle. "qa" keeps the legacy two-textarea
  // shape. "cloze" collapses to a single textarea (the cloze source);
  // the back column is server-mirrored from front so the schema's
  // "both columns non-empty" invariant still holds.
  // PR 5.2 (ADR 0003) — "reverse" reuses the qa two-textarea layout
  // but submits to /api/srs/cards/pair, which creates both the
  // primary Q→A and the swapped A→Q twin in one transaction.
  const [kind, setKind] = useState<"qa" | "cloze" | "reverse">("qa");
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
      setKind("qa");
      setFront("");
      setBack("");
      setError(null);
    }
  }, [open]);

  const clozeMarkerOk = /\{\{c\d+::[^}]+\}\}/.test(front);
  const canSubmit =
    kind === "cloze"
      ? front.trim().length > 0 && clozeMarkerOk && !submitting
      : front.trim().length > 0 && back.trim().length > 0 && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      if (kind === "reverse") {
        const { primary, reverse } = await study.createCardPair({ front, back, docId });
        onCreated(primary);
        onCreated(reverse);
      } else {
        const payload =
          kind === "cloze"
            ? { front, back: front, kind: "cloze" as const, docId }
            : { front, back, kind: "qa" as const, docId };
        const { card } = await study.createCard(payload);
        onCreated(card);
      }
      onClose();
    } catch (err) {
      setError((err as Error).message || "Could not create the card. Save it again.");
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
          <Button
            disabled={!canSubmit}
            isLoading={submitting}
            keyHint="⌘↵"
            onClick={() => void handleSubmit()}
          >
            {kind === "reverse" ? "Create pair" : "Create card"}
          </Button>
        </Stack>
      }
      description={
        docId
          ? "This card will be linked to the source you're reading."
          : activeSubject
            ? `The card will appear under "All subjects". Subject linking is coming next.`
            : "A blank flashcard. Add the prompt on the front and the answer on the back."
      }
      onClose={onClose}
      open={open}
      title="New flashcard"
    >
      <Stack gap={4}>
        <div className={styles.kindPicker} role="group" aria-label="Card type">
          <Button
            variant={kind === "qa" ? "primary" : "ghost"}
            size="sm"
            onClick={() => setKind("qa")}
            aria-pressed={kind === "qa"}
          >
            Q &amp; A
          </Button>
          <Button
            variant={kind === "cloze" ? "primary" : "ghost"}
            size="sm"
            onClick={() => setKind("cloze")}
            aria-pressed={kind === "cloze"}
          >
            Cloze
          </Button>
          <Button
            variant={kind === "reverse" ? "primary" : "ghost"}
            size="sm"
            onClick={() => setKind("reverse")}
            aria-pressed={kind === "reverse"}
          >
            Reverse pair
          </Button>
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor={frontId}>
            {kind === "cloze"
              ? "Cloze sentence"
              : kind === "reverse"
                ? "Term"
                : "Front"}
            <Text tone="tertiary" variant="caption">
              {kind === "cloze"
                ? "Wrap the blanked term in {{c1::term}}. Both faces render the same sentence."
                : kind === "reverse"
                  ? "The first half of the pair. We'll also create the swapped card automatically."
                  : "The question or prompt. Enter moves to the back."}
            </Text>
          </label>
          <textarea
            className={styles.textarea}
            id={frontId}
            onInput={(e) => setFront((e.currentTarget as HTMLTextAreaElement).value)}
            onKeyDown={handleFrontKeyDown}
            placeholder={
              kind === "cloze"
                ? "e.g. The mitochondrion is the {{c1::powerhouse}} of the cell."
                : "e.g. What is the difference between a coupon rate and a yield?"
            }
            rows={kind === "cloze" ? 5 : 3}
            value={front}
          />
          {kind === "cloze" && front.trim().length > 0 && !clozeMarkerOk ? (
            <Text tone="tertiary" variant="caption">
              Add a {`{{c1::term}}`} marker around the word you want hidden.
            </Text>
          ) : null}
        </div>

        {kind === "qa" || kind === "reverse" ? (
          <div className={styles.field}>
            <label className={styles.label} htmlFor={backId}>
              {kind === "reverse" ? "Definition" : "Back"}
              <Text tone="tertiary" variant="caption">
                {kind === "reverse"
                  ? "The second half of the pair. Cmd+Enter to save both cards."
                  : "The answer you want to recall. Cmd+Enter to save."}
              </Text>
            </label>
            <textarea
              className={styles.textarea}
              id={backId}
              onInput={(e) => setBack((e.currentTarget as HTMLTextAreaElement).value)}
              onKeyDown={handleBackKeyDown}
              placeholder={
                kind === "reverse"
                  ? "e.g. The interest rate paid on a bond's face value."
                  : "e.g. The coupon rate is fixed at issuance; the yield reflects the current market price."
              }
              ref={backRef}
              rows={5}
              value={back}
            />
          </div>
        ) : null}

        {error ? (
          <Text role="alert" tone="danger" variant="caption">
            {error}
          </Text>
        ) : null}
      </Stack>
    </Dialog>
  );
}
