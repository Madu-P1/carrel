import { useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import {
  notes as notesApi,
  type NoteOrganizationSubject,
  type NoteRecord
} from "@/services/api/endpoints";

import { notePreviewText } from "../noteContent";
import { Ic } from "./NotesIcons";
import styles from "./NoteTile.module.css";

interface NoteTileProps {
  note: NoteRecord;
  subjects: NoteOrganizationSubject[];
  onChanged: () => void;
}

/**
 * Stillwater note tile — clickable card.
 *
 * Click anywhere on the tile (except an action) opens the full-page
 * Note Editor at /notes/:id. The metadata footer carries the source
 * pill, the timestamp, and a "Move to folder" select.
 *
 * Inline-edit on the tile was removed when the dedicated writing page
 * shipped — the editor is the only place a note is authored, and the
 * tile is a preview/launcher.
 */
export function NoteTile({ note, subjects, onChanged }: NoteTileProps) {
  const [moveError, setMoveError] = useState<string | null>(null);

  const openEditor = () => {
    navigateTo(`/notes/${encodeURIComponent(note.id)}`);
  };

  const handleMove = async (event: Event) => {
    const value = (event.currentTarget as HTMLSelectElement).value;
    const next = value === "" ? null : value;
    if (next === (note.folder_id ?? null)) return;
    setMoveError(null);
    try {
      await notesApi.move(note.id, next);
      onChanged();
    } catch (err) {
      setMoveError((err as Error).message || "Move failed.");
    }
  };

  const sourceLabel = note.document_name ?? null;
  const previewBody =
    notePreviewText(note.content).split(/\.\s+|\n\n/)[0] ?? "Start writing...";

  return (
    <li className={styles.tile}>
      <button
        type="button"
        className={styles.tileOpener}
        onClick={openEditor}
        aria-label={`Open note "${note.title || "Untitled note"}"`}
      >
        <header className={styles.head}>
          <h3 className={styles.title}>{note.title || "Untitled note"}</h3>
        </header>
        <p className={styles.preview}>{previewBody}</p>
      </button>

      <footer className={styles.foot}>
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
          <span className={styles.ts}>{formatTimestamp(note.updated_at)}</span>
        </div>
        <label className={styles.move}>
          <span className={styles.srOnly}>Move to folder</span>
          <select
            className={styles.moveSelect}
            value={note.folder_id ?? ""}
            onChange={handleMove}
            onClick={(e) => e.stopPropagation()}
            aria-label={
              note.folder_name
                ? `Move from folder ${note.folder_name}`
                : "Move to folder"
            }
          >
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
      </footer>
      {moveError ? (
        <p className={styles.error} role="alert">
          {moveError}
        </p>
      ) : null}
    </li>
  );
}

function formatTimestamp(iso: string): string {
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
