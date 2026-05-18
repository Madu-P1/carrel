import { useState } from "preact/hooks";

import { Icon } from "@/design-system";
import { notes } from "@/services/api/endpoints";

import styles from "./NoteComposer.module.css";

interface NoteComposerProps {
  docId: string;
  documentName?: string;
  /** Called after a note saves successfully so the parent can refetch
   *  the notes list — write + view live in the same tab. */
  onSaved: () => void;
}

/**
 * Doc-bound note composer for the Reader's Notes tab. Title + body, plus
 * Save (persists to /api/notes bound to doc_id) and Expand with AI
 * (rewrites the body into structured markdown via /api/notes/expand).
 *
 * Not auto-saved by design: the user decides when a draft is worth
 * keeping. Relocated here from the session view, which had no business
 * owning note-writing.
 */
export function NoteComposer({ docId, documentName, onSaved }: NoteComposerProps) {
  const [title, setTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [expanding, setExpanding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const textareaId = `note-composer-body-${docId}`;
  const titleId = `note-composer-title-${docId}`;

  const resolvedTitle = () => title.trim() || documentName || "Note";

  const saveNote = async () => {
    const content = draft.trim();
    if (!content || saving) return;
    setSaving(true);
    setStatus(null);
    try {
      await notes.save({
        title: resolvedTitle(),
        content,
        doc_id: docId,
        note_type: "reader_note"
      });
      setStatus({ kind: "ok", text: "Saved." });
      setTitle("");
      setDraft("");
      onSaved();
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
      const { expanded_markdown } = await notes.expand({ title: resolvedTitle(), content });
      setDraft(expanded_markdown);
      setStatus({ kind: "ok", text: "Expanded. Review and save when ready." });
    } catch (caught) {
      setStatus({ kind: "err", text: (caught as Error).message });
    } finally {
      setExpanding(false);
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.eyebrow}>
        <span>New note</span>
        <span className={styles.eyebrowMeta}>saved to this source · not auto-saved</span>
      </div>
      <label htmlFor={titleId} className={styles.srOnly}>
        Note title
      </label>
      <input
        id={titleId}
        className={styles.titleInput}
        value={title}
        onInput={(event) => setTitle((event.currentTarget as HTMLInputElement).value)}
        placeholder={documentName ? `Title (defaults to "${documentName}")` : "Title (optional)"}
      />
      <label htmlFor={textareaId} className={styles.srOnly}>
        Note body
      </label>
      <textarea
        id={textareaId}
        className={styles.textarea}
        value={draft}
        onInput={(event) => setDraft((event.currentTarget as HTMLTextAreaElement).value)}
        placeholder="Write what you're learning. Press Expand to grow the draft from your sources."
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
          {expanding ? "Expanding…" : "Expand the draft"}
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
