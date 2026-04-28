import { useEffect, useId, useMemo, useState } from "preact/hooks";

import { Button, Dialog, Icon, Input, Spinner, Stack, Text } from "@/design-system";
import {
  study,
  type CardAiDraftItem,
  type SrsCard
} from "@/services/api/endpoints";

import styles from "./CardAiDraftDialog.module.css";

interface CardAiDraftDialogProps {
  open: boolean;
  onClose: () => void;
  onCardsCreated: (cards: SrsCard[]) => void;
}

interface DraftState extends CardAiDraftItem {
  /** Stable id per draft so Preact can key into the list across edits. */
  draftId: string;
  /** User toggle — off excludes this draft from bulk save. Default on. */
  include: boolean;
}

type Phase =
  | { kind: "form"; error: string | null }
  | { kind: "generating" }
  | { kind: "review"; status: "ok" | "ai_disabled" | "ai_failed"; note: string | null }
  | { kind: "saving"; savedCount: number; totalToSave: number }
  | { kind: "done"; savedCount: number };

/**
 * "Generate with AI" workflow for the Manage Cards view.
 *
 * Flow:
 *   1. Form: topic (required) + optional context + count.
 *   2. Generate: POST /api/srs/cards/ai-draft, show spinner.
 *   3. Review: each draft is a row with editable front/back + include toggle.
 *      User can tune wording inline before saving.
 *   4. Saving: bulk POST /api/srs/cards, one per included draft (no new
 *      bulk endpoint needed — the list-level loop is fine at N≤10).
 *   5. Done: summary, Close.
 *
 * Dialog primitive handles focus-trap + Esc. We keep the phase machine
 * local so reopening the dialog always starts fresh at the form.
 */
export function CardAiDraftDialog({ open, onClose, onCardsCreated }: CardAiDraftDialogProps) {
  const [topic, setTopic] = useState("");
  const [context, setContext] = useState("");
  const [count, setCount] = useState(5);
  const [drafts, setDrafts] = useState<DraftState[]>([]);
  const [phase, setPhase] = useState<Phase>({ kind: "form", error: null });

  // Reset the whole machine each time the dialog opens so a previous run
  // doesn't leak across uses. The Dialog primitive handles initial focus
  // itself (first focusable element in its subtree), so we don't need a
  // manual focus call here.
  useEffect(() => {
    if (!open) return;
    setTopic("");
    setContext("");
    setCount(5);
    setDrafts([]);
    setPhase({ kind: "form", error: null });
  }, [open]);

  const canGenerate = topic.trim().length > 0 && phase.kind === "form";
  const includedDrafts = useMemo(() => drafts.filter((d) => d.include && d.front.trim() && d.back.trim()), [drafts]);

  const handleGenerate = async () => {
    if (!canGenerate) return;
    setPhase({ kind: "generating" });
    try {
      const response = await study.aiDraftCards({
        topic,
        context: context.trim() || undefined,
        count
      });
      if (response.status === "ai_disabled") {
        setPhase({
          kind: "review",
          status: "ai_disabled",
          note: "The model is turned off. Set EINSTEIN_AI_PROVIDER to claude or ollama in .env and restart the backend to use this."
        });
        setDrafts([]);
        return;
      }
      if (response.status !== "ok" || response.cards.length === 0) {
        setPhase({
          kind: "review",
          status: "ai_failed",
          note: response.error
            ? `The model couldn't draft cards (${response.error}). Try a more specific topic.`
            : "The model returned no usable drafts. Try a more specific topic."
        });
        setDrafts([]);
        return;
      }
      setDrafts(
        response.cards.map((c, i) => ({
          draftId: `draft-${i}-${Math.random().toString(36).slice(2, 8)}`,
          front: c.front,
          back: c.back,
          include: true
        }))
      );
      setPhase({ kind: "review", status: "ok", note: null });
    } catch (err) {
      setPhase({ kind: "form", error: (err as Error).message || "Generation failed." });
    }
  };

  const updateDraft = (id: string, patch: Partial<CardAiDraftItem>) => {
    setDrafts((prev) => prev.map((d) => (d.draftId === id ? { ...d, ...patch } : d)));
  };
  const toggleDraft = (id: string) => {
    setDrafts((prev) => prev.map((d) => (d.draftId === id ? { ...d, include: !d.include } : d)));
  };

  const handleSaveSelected = async () => {
    if (includedDrafts.length === 0) return;
    setPhase({ kind: "saving", savedCount: 0, totalToSave: includedDrafts.length });
    const created: SrsCard[] = [];
    // Save sequentially so the server doesn't see 10 parallel INSERTs and
    // so a failure partway through still surfaces the real created cards.
    // At N≤10 the serial latency cost is negligible.
    try {
      for (const draft of includedDrafts) {
        const { card } = await study.createCard({ front: draft.front, back: draft.back });
        created.push(card);
        setPhase((prev) =>
          prev.kind === "saving"
            ? { ...prev, savedCount: prev.savedCount + 1 }
            : prev
        );
      }
      onCardsCreated(created);
      setPhase({ kind: "done", savedCount: created.length });
    } catch (err) {
      // Partial success: surface the error but still report whatever did land.
      if (created.length > 0) onCardsCreated(created);
      setPhase({
        kind: "review",
        status: "ok",
        note: `Saved ${created.length} of ${includedDrafts.length}. ${(err as Error).message}`
      });
    }
  };

  return (
    <Dialog
      actions={renderActions({
        phase,
        canGenerate,
        includedCount: includedDrafts.length,
        draftsTotal: drafts.length,
        onClose,
        onGenerate: () => void handleGenerate(),
        onSave: () => void handleSaveSelected()
      })}
      description="Describe a topic. The model drafts a few cards; you edit and keep the ones you want."
      onClose={onClose}
      open={open}
      title="Draft flashcards from a topic"
    >
      {phase.kind === "form" || phase.kind === "generating" ? (
        <FormPane
          context={context}
          count={count}
          error={phase.kind === "form" ? phase.error : null}
          generating={phase.kind === "generating"}
          onContextChange={setContext}
          onCountChange={setCount}
          onTopicChange={setTopic}
          topic={topic}
        />
      ) : phase.kind === "review" ? (
        <ReviewPane
          drafts={drafts}
          note={phase.note}
          onToggle={toggleDraft}
          onUpdate={updateDraft}
          status={phase.status}
        />
      ) : phase.kind === "saving" ? (
        <SavingPane savedCount={phase.savedCount} totalToSave={phase.totalToSave} />
      ) : (
        <DonePane savedCount={phase.savedCount} />
      )}
    </Dialog>
  );
}

// Action buttons change per phase. Extracted so the Dialog render above
// stays legible.
function renderActions({
  phase,
  canGenerate,
  includedCount,
  draftsTotal,
  onClose,
  onGenerate,
  onSave
}: {
  phase: Phase;
  canGenerate: boolean;
  includedCount: number;
  draftsTotal: number;
  onClose: () => void;
  onGenerate: () => void;
  onSave: () => void;
}) {
  if (phase.kind === "form" || phase.kind === "generating") {
    return (
      <Stack direction="horizontal" gap={2}>
        <Button onClick={onClose} variant="secondary">Cancel</Button>
        <Button
          disabled={!canGenerate}
          isLoading={phase.kind === "generating"}
          onClick={onGenerate}
          leadingIcon={<Icon name="sparkle" />}
        >
          Generate drafts
        </Button>
      </Stack>
    );
  }
  if (phase.kind === "review") {
    const canSave = includedCount > 0 && phase.status === "ok";
    return (
      <Stack direction="horizontal" gap={2}>
        <Button onClick={onClose} variant="secondary">Cancel</Button>
        {draftsTotal > 0 ? (
          <Button onClick={onGenerate} variant="ghost" leadingIcon={<Icon name="sparkle" />}>
            Regenerate
          </Button>
        ) : null}
        <Button disabled={!canSave} onClick={onSave}>
          {canSave ? `Save ${includedCount} card${includedCount === 1 ? "" : "s"}` : "Save"}
        </Button>
      </Stack>
    );
  }
  if (phase.kind === "saving") {
    return (
      <Stack direction="horizontal" gap={2}>
        <Button disabled variant="secondary">Cancel</Button>
        <Button disabled isLoading>
          Saving {phase.savedCount} / {phase.totalToSave}
        </Button>
      </Stack>
    );
  }
  return (
    <Stack direction="horizontal" gap={2}>
      <Button onClick={onClose}>Close</Button>
    </Stack>
  );
}

function FormPane({
  topic,
  context,
  count,
  error,
  generating,
  onTopicChange,
  onContextChange,
  onCountChange
}: {
  topic: string;
  context: string;
  count: number;
  error: string | null;
  generating: boolean;
  onTopicChange: (v: string) => void;
  onContextChange: (v: string) => void;
  onCountChange: (v: number) => void;
}) {
  // Ship 8 a11y audit: the optional-context textarea needs an associated
  // label so screen readers and the click-the-label-to-focus-the-field
  // affordance both work. The Input primitive handles this for the
  // Topic field automatically; this is the one custom field in the
  // dialog that needs explicit wiring.
  const contextId = useId();

  return (
    <Stack gap={4}>
      <Input
        aria-label="Topic"
        label="Topic"
        helpText="A specific subject or concept. More specific = better cards."
        onInput={(e) => onTopicChange((e.currentTarget as HTMLInputElement).value)}
        placeholder="e.g. Bond pricing and yield mechanics"
        value={topic}
      />

      <div className={styles.field}>
        <label className={styles.label} htmlFor={contextId}>
          Optional context
          <Text tone="tertiary" variant="caption">
            Paste notes or an excerpt here. Leave blank to use only the topic.
          </Text>
        </label>
        <textarea
          id={contextId}
          className={styles.textarea}
          onInput={(e) => onContextChange((e.currentTarget as HTMLTextAreaElement).value)}
          placeholder=""
          rows={4}
          value={context}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="card-ai-draft-count">
          How many drafts
          <Text tone="tertiary" variant="caption">
            Between 3 and 10. Fewer drafts = higher per-card quality.
          </Text>
        </label>
        <input
          className={styles.numberInput}
          id="card-ai-draft-count"
          max={10}
          min={3}
          onInput={(e) => {
            const v = Number.parseInt((e.currentTarget as HTMLInputElement).value, 10);
            if (!Number.isNaN(v)) onCountChange(Math.max(3, Math.min(10, v)));
          }}
          type="number"
          value={count}
        />
      </div>

      {error ? (
        <Text role="alert" tone="danger" variant="caption">{error}</Text>
      ) : null}

      {generating ? (
        <Stack direction="horizontal" gap={2} className={styles.workingRow}>
          <Spinner size={16} />
          <Text tone="secondary" variant="caption">
            Drafting {count} card{count === 1 ? "" : "s"}. This usually takes 10–20 seconds.
          </Text>
        </Stack>
      ) : null}
    </Stack>
  );
}

function ReviewPane({
  drafts,
  note,
  status,
  onToggle,
  onUpdate
}: {
  drafts: DraftState[];
  note: string | null;
  status: "ok" | "ai_disabled" | "ai_failed";
  onToggle: (id: string) => void;
  onUpdate: (id: string, patch: Partial<CardAiDraftItem>) => void;
}) {
  if (status !== "ok" || drafts.length === 0) {
    return (
      <Stack gap={3}>
        <Text tone="secondary">{note ?? "No drafts available."}</Text>
      </Stack>
    );
  }

  return (
    <Stack gap={3}>
      {note ? <Text tone="tertiary" variant="caption">{note}</Text> : null}
      <ul className={styles.draftsList}>
        {drafts.map((draft) => (
          <li
            className={[styles.draftItem, draft.include ? "" : styles.draftItemExcluded].filter(Boolean).join(" ")}
            key={draft.draftId}
          >
            <div className={styles.draftHeader}>
              <label className={styles.checkboxLabel}>
                <input
                  checked={draft.include}
                  onChange={() => onToggle(draft.draftId)}
                  type="checkbox"
                />
                <span>Include</span>
              </label>
            </div>
            <div className={styles.draftFields}>
              <label className={styles.draftFieldLabel}>
                <span>Front</span>
                <textarea
                  className={styles.draftTextarea}
                  disabled={!draft.include}
                  onInput={(e) => onUpdate(draft.draftId, { front: (e.currentTarget as HTMLTextAreaElement).value })}
                  rows={2}
                  value={draft.front}
                />
              </label>
              <label className={styles.draftFieldLabel}>
                <span>Back</span>
                <textarea
                  className={styles.draftTextarea}
                  disabled={!draft.include}
                  onInput={(e) => onUpdate(draft.draftId, { back: (e.currentTarget as HTMLTextAreaElement).value })}
                  rows={3}
                  value={draft.back}
                />
              </label>
            </div>
          </li>
        ))}
      </ul>
    </Stack>
  );
}

function SavingPane({ savedCount, totalToSave }: { savedCount: number; totalToSave: number }) {
  return (
    <Stack direction="horizontal" gap={3} className={styles.savingRow}>
      <Spinner size={16} />
      <Text tone="secondary">
        Saving card {savedCount + 1} of {totalToSave}…
      </Text>
    </Stack>
  );
}

function DonePane({ savedCount }: { savedCount: number }) {
  return (
    <Stack gap={2}>
      <Text as="p" weight="semibold">
        Added {savedCount} card{savedCount === 1 ? "" : "s"} to your library.
      </Text>
      <Text tone="secondary">
        They're queued for your next review session. Close this dialog to see them at the top of the list.
      </Text>
    </Stack>
  );
}
