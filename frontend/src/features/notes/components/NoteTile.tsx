import { useEffect, useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import {
  notes as notesApi,
  type NoteOrganizationSubject,
  type NoteRecord
} from "@/services/api/endpoints";

import { Ic } from "./NotesIcons";
import styles from "./NoteTile.module.css";

interface NoteTileProps {
  note: NoteRecord;
  subjects: NoteOrganizationSubject[];
  expanded: boolean;
  onExpand: (next: boolean) => void;
  onChanged: () => void;
}

/**
 * Stillwater note tile.
 *
 * Two modes:
 *   collapsed → serif title + 8-line clamped body preview + cite pill + ts
 *   expanded  → serif title + inline-editable textarea + cite pill + Saved indicator
 *
 * Autosave: on blur and on ⌘S. Debounced 800ms during typing matches the
 * Reader's NoteComposer pattern. Saving sends the existing upsert with
 * note_id so the row updates rather than duplicates.
 *
 * "Open in Reader" jumps to the source doc when note.doc_id is non-null.
 * "Move…" surfaces the inline subject-grouped folder <select> from the
 * footer.
 */
export function NoteTile({
  note,
  subjects,
  expanded,
  onExpand,
  onChanged
}: NoteTileProps) {
  const [body, setBody] = useState(note.content);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  const lastSavedBodyRef = useRef(note.content);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const tileRef = useRef<HTMLLIElement | null>(null);

  // Reset local state only when the underlying note IDENTITY changes
  // (selection switched to a different note rendered in the same
  // tile slot). Intentionally NOT depending on note.content — once
  // mounted, the textarea is the source of truth. A server echo of
  // our own save would otherwise overwrite the next keystrokes the
  // user typed while the round-trip was in flight.
  //
  // Workspace-note seed: a brand-new doc-less note arrives with
  // content="\n" (the server's min_length=1 placeholder). Clear the
  // body visually so the textarea starts at line 1 column 1. The
  // last-saved ref keeps the seed so a "blur without typing" save is
  // recognized as a no-op by the empty-coercion in flushSave.
  useEffect(() => {
    const isWorkspaceSeed = note.content === "\n";
    setBody(isWorkspaceSeed ? "" : note.content);
    lastSavedBodyRef.current = note.content;
    setSavedAt(null);
    setSaveError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note.id]);

  // Focus the textarea when we expand. Empty notes (just-created from
  // "+ New note") get focus on the body so the user can type
  // immediately. Also scroll the tile into view — a workspace note
  // created from "+ New note" lands under "Unfiled" (alphabetically
  // last) and is otherwise off-screen at the bottom of the page.
  useEffect(() => {
    if (expanded && textareaRef.current) {
      textareaRef.current.focus();
      const len = textareaRef.current.value.length;
      textareaRef.current.setSelectionRange(len, len);
    }
    if (expanded && tileRef.current) {
      const reduce =
        typeof window !== "undefined" &&
        window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      tileRef.current.scrollIntoView({
        block: "center",
        behavior: reduce ? "auto" : "smooth"
      });
    }
  }, [expanded]);

  const flushSave = async (override?: string) => {
    // Empty body never goes to the server — coerce to "\n" so the row
    // stays valid against content.min_length=1. The user deletes a
    // note via the dedicated delete action (Phase B), not by clearing
    // the textarea.
    let next = override ?? body;
    if (next === "") next = "\n";
    if (next === lastSavedBodyRef.current) return;
    setSaving(true);
    setSaveError(null);
    try {
      await notesApi.save({
        title: note.title || "Untitled note",
        content: next,
        doc_id: note.doc_id ?? undefined,
        concept_id: note.concept_id ?? undefined,
        folder_id: note.folder_id,
        note_type: note.note_type
      });
      lastSavedBodyRef.current = next;
      const stamp = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
      });
      setSavedAt(stamp);
      onChanged();
    } catch (err) {
      setSaveError((err as Error).message || "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const scheduleDebouncedSave = (next: string) => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      void flushSave(next);
    }, 800);
  };

  // Clean up the debounce timer if the tile unmounts mid-type so we
  // don't trigger a save against a stale closure.
  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, []);

  const handleKeyDown = (event: KeyboardEvent) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "s") {
      event.preventDefault();
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      void flushSave();
      return;
    }
    if (event.key === "Escape") {
      // Esc collapses the expanded tile. Save first so nothing is
      // lost — same contract as clicking "Collapse ↑" or letting the
      // tile lose focus.
      event.preventDefault();
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      void flushSave();
      onExpand(false);
    }
  };

  const handleBlur = () => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    void flushSave();
  };

  const handleMove = async (event: Event) => {
    const value = (event.currentTarget as HTMLSelectElement).value;
    const next = value === "" ? null : value;
    if (next === (note.folder_id ?? null)) return;
    try {
      await notesApi.move(note.id, next);
      onChanged();
    } catch (err) {
      setSaveError((err as Error).message || "Move failed.");
    }
  };

  const openInReader = () => {
    if (!note.doc_id) return;
    navigateTo(`/reader/${encodeURIComponent(note.doc_id)}`);
  };

  const sourceLabel = note.document_name ?? null;
  // For the collapsed preview, trim and split — handles workspace
  // notes seeded with a placeholder "\n" (so they don't render as a
  // blank line with no text).
  const trimmedFirst = body.split("\n\n")[0]?.trim() ?? "";
  const previewBody = trimmedFirst || "Start writing…";

  return (
    <li
      ref={tileRef}
      className={[styles.tile, expanded ? styles.tileExpanded : ""]
        .filter(Boolean)
        .join(" ")}
    >
      <header className={styles.head}>
        <h3 className={styles.title}>{note.title || "Untitled note"}</h3>
        <div className={styles.actions}>
          <label className={styles.move}>
            <span className={styles.srOnly}>Move to folder</span>
            <select
              className={styles.moveSelect}
              value={note.folder_id ?? ""}
              onChange={handleMove}
              aria-label={
                note.folder_name
                  ? `Move from folder ${note.folder_name}`
                  : "Move to folder"
              }
            >
              {/*
                One option with value="" — selecting it unfiles the
                note. The visible button text reflects the current
                state: when the note has no folder, it reads
                "No folder" (the truth). When the note is filed, it
                reads the folder name. A chevron via .moveSelect::after
                signals the dropdown affordance.
              */}
              <option value="">No folder</option>
              {subjects.map((subject) =>
                subject.folders.length > 0 ? (
                  <optgroup key={subject.name} label={subject.name}>
                    {subject.folders.map((folder) => (
                      <option key={folder.id} value={folder.id}>
                        {folder.name}
                      </option>
                    ))}
                  </optgroup>
                ) : null
              )}
            </select>
          </label>
          <button
            type="button"
            className={[styles.btn, styles.btnPrimary].join(" ")}
            onClick={() => onExpand(!expanded)}
          >
            {expanded ? "Collapse ↑" : "Expand ↓"}
          </button>
        </div>
      </header>

      {expanded ? (
        <>
          <textarea
            ref={textareaRef}
            className={styles.textarea}
            value={body}
            onInput={(e) => {
              const next = (e.currentTarget as HTMLTextAreaElement).value;
              setBody(next);
              scheduleDebouncedSave(next);
            }}
            onBlur={handleBlur}
            onKeyDown={handleKeyDown}
            rows={11}
            aria-label="Edit note body"
            placeholder="Write here…"
          />
          <div className={styles.foot}>
            <div className={styles.cite}>
              {sourceLabel ? (
                <>
                  <span className={styles.citePill}>
                    <Ic.note className={styles.citeIc} />
                    {sourceLabel}
                  </span>
                  {note.doc_id ? (
                    <button
                      type="button"
                      className={styles.openInReader}
                      onClick={openInReader}
                    >
                      Open in Reader ↗
                    </button>
                  ) : null}
                </>
              ) : (
                <span className={[styles.citePill, styles.citePillMuted].join(" ")}>
                  No source
                </span>
              )}
            </div>
            <div className={styles.save}>
              {saveError ? (
                <span className={styles.saveErr} role="alert">
                  {saveError}
                </span>
              ) : (
                <>
                  <span
                    className={[styles.saveDot, saving ? styles.saveDotPulse : ""]
                      .filter(Boolean)
                      .join(" ")}
                    aria-hidden
                  />
                  <span>
                    {saving
                      ? "Saving…"
                      : savedAt
                        ? `Saved · ${savedAt}`
                        : `Synced · ${formatTimestamp(note.updated_at)}`}
                  </span>
                </>
              )}
            </div>
          </div>
        </>
      ) : (
        <>
          <p className={styles.preview}>{previewBody}</p>
          <div className={styles.foot}>
            <div className={styles.cite}>
              {sourceLabel ? (
                <span className={styles.citePill}>
                  <Ic.note className={styles.citeIc} />
                  {sourceLabel}
                </span>
              ) : (
                <span className={[styles.citePill, styles.citePillMuted].join(" ")}>
                  No source
                </span>
              )}
            </div>
            <div className={styles.ts}>{formatTimestamp(note.updated_at)}</div>
          </div>
        </>
      )}
    </li>
  );
}

function formatTimestamp(iso: string): string {
  // Match Stillwater's display strings ("Yesterday, 11:42 PM", "Mon · 9:14 AM").
  // Real localization is a follow-up; this keeps the chrome looking like
  // the design canvas while staying honest about the underlying ISO.
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  const time = date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit"
  });
  if (sameDay) return `Today, ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) {
    return `Yesterday, ${time}`;
  }
  const day = date.toLocaleDateString([], { weekday: "short" });
  return `${day} · ${time}`;
}
