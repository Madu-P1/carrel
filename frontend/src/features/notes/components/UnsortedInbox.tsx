import { useMemo, useState } from "preact/hooks";

import {
  notes as notesApi,
  type NoteOrganizationSubject,
  type NoteRecord
} from "@/services/api/endpoints";

import { notePreviewText } from "../noteContent";
import { Ic } from "./NotesIcons";
import styles from "./UnsortedInbox.module.css";

interface UnsortedInboxProps {
  notes: NoteRecord[];
  subjects: NoteOrganizationSubject[];
  onChanged: () => void;
}

/**
 * Unsorted Inbox card — Stillwater.
 *
 * Shows the 5 most-recent notes with `folder_id IS NULL` across all
 * subjects. Each row exposes a one-click "File →" that opens a small
 * folder picker (native <select> styled to match the Stillwater button
 * chrome). The card has a warm amber 3px stripe at the left edge so
 * it reads as a triage surface, distinct from the cool teal of the
 * note tiles below.
 *
 * Empty state: the card vanishes entirely. No "you're all caught up"
 * filler — fewer chrome elements when there's nothing to triage.
 */
export function UnsortedInbox({
  notes,
  subjects,
  onChanged
}: UnsortedInboxProps) {
  const top5 = useMemo(() => {
    return notes.filter((n) => n.folder_id === null).slice(0, 5);
  }, [notes]);

  if (top5.length === 0) return null;

  return (
    <section className={styles.inbox}>
      <div className={styles.head}>
        <div className={styles.title}>
          <Ic.inbox className={styles.titleIc} />
          <h2 className={styles.titleText}>Unsorted Inbox</h2>
          <span className={styles.pill}>{top5.length}</span>
        </div>
      </div>

      <ul className={styles.list}>
        {top5.map((note) => (
          <InboxRow
            key={note.id}
            note={note}
            subjects={subjects}
            onChanged={onChanged}
          />
        ))}
      </ul>
    </section>
  );
}

interface InboxRowProps {
  note: NoteRecord;
  subjects: NoteOrganizationSubject[];
  onChanged: () => void;
}

function InboxRow({ note, subjects, onChanged }: InboxRowProps) {
  const [moving, setMoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (event: Event) => {
    const value = (event.currentTarget as HTMLSelectElement).value;
    if (!value) return;
    setMoving(true);
    setError(null);
    try {
      await notesApi.move(note.id, value);
      onChanged();
    } catch (err) {
      setError((err as Error).message || "File failed.");
    } finally {
      setMoving(false);
    }
  };

  const sourceLine = note.document_name ? `${note.document_name}` : "No source";
  const snippet = notePreviewText(note.content, "Empty note.");

  return (
    <li className={styles.row}>
      <div className={styles.body}>
        <div className={styles.rowTitle}>{note.title || "Untitled note"}</div>
        <p className={styles.snippet}>{snippet}</p>
        <div className={styles.meta}>
          <span className={styles.cite}>{sourceLine}</span>
          <span className={styles.dot}>·</span>
          <span className={styles.ts}>{relativeTime(note.updated_at)}</span>
          {error ? (
            <>
              <span className={styles.dot}>·</span>
              <span className={styles.err} role="alert">
                {error}
              </span>
            </>
          ) : null}
        </div>
      </div>
      <label className={styles.fileWrap}>
        <span className={styles.srOnly}>File this note into a folder</span>
        <select
          className={styles.file}
          value=""
          onChange={handleFile}
          disabled={moving || subjects.length === 0}
        >
          <option value="">File → </option>
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
    </li>
  );
}

function relativeTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}
