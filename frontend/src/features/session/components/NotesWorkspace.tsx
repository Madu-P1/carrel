import { useState } from "preact/hooks";

import { Icon } from "@/design-system";
import { notes } from "@/services/api/endpoints";

import styles from "./NotesWorkspace.module.css";

interface NotesWorkspaceProps {
  sessionId: string;
  sessionObjective: string;
}

/**
 * Notes mode content. Textarea for the user to write in, plus two actions:
 *   - Save note    → persists to /api/notes with session_id bound
 *   - Expand with AI → calls /api/notes/expand; response replaces the
 *                      textarea content with structured markdown
 *                      (summary + key ideas + organized notes + review
 *                       prompts)
 *
 * Explicitly ephemeral by design — the textarea does NOT auto-save. The
 * user decides when what they've written is worth saving. This beats a
 * "you lost your draft" surprise any day.
 *
 * Error states: inline below the textarea; no toasts, per the brief.
 */
export function NotesWorkspace({ sessionId, sessionObjective }: NotesWorkspaceProps) {
  const [draft, setDraft] = useState("");
  const [expanding, setExpanding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const saveNote = async () => {
    const content = draft.trim();
    if (!content || saving) return;
    setSaving(true);
    setStatus(null);
    try {
      const title = sessionObjective || "Session note";
      await notes.save({ title, content, session_id: sessionId });
      setStatus({ kind: "ok", text: "Saved." });
    } catch (caught) {
      setStatus({ kind: "err", text: (caught as Error).message });
    } finally {
      setSaving(false);
    }
  };

  const expandWithAi = async () => {
    const content = draft.trim();
    if (!content || expanding) return;
    setExpanding(true);
    setStatus(null);
    try {
      const title = sessionObjective || "Session note";
      const { expanded_markdown } = await notes.expand({ title, content });
      setDraft(expanded_markdown);
      setStatus({ kind: "ok", text: "Expanded — review and save when ready." });
    } catch (caught) {
      setStatus({ kind: "err", text: (caught as Error).message });
    } finally {
      setExpanding(false);
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.eyebrow}>
        <span>Notes</span>
        <span className={styles.eyebrowMeta}>session-bound · not auto-saved</span>
      </div>
      <textarea
        className={styles.textarea}
        value={draft}
        onInput={(event) =>
          setDraft((event.currentTarget as HTMLTextAreaElement).value)
        }
        placeholder="Write what you're learning. Einstein can expand or organize your notes with AI."
        aria-label="Session notes"
      />
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.saveButton}
          onClick={() => void saveNote()}
          disabled={!draft.trim() || saving}
        >
          {saving ? "Saving…" : "Save note"}
        </button>
        <button
          type="button"
          className={styles.expandButton}
          onClick={() => void expandWithAi()}
          disabled={!draft.trim() || expanding}
        >
          <Icon name="sparkle" size={14} />
          {expanding ? "Expanding…" : "Expand with AI"}
        </button>
        {status && (
          <span
            className={[
              styles.status,
              status.kind === "err" ? styles.statusErr : styles.statusOk
            ].join(" ")}
          >
            {status.text}
          </span>
        )}
      </div>
    </div>
  );
}
