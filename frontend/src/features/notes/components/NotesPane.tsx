import { useMemo, useState } from "preact/hooks";

import { Icon, Text } from "@/design-system";
import {
  notes as notesApi,
  type NoteOrganizationSubject,
  type NoteRecord
} from "@/services/api/endpoints";

import type { RailSelection } from "./SubjectRail";
import styles from "./NotesPane.module.css";

interface NotesPaneProps {
  notes: NoteRecord[];
  subjects: NoteOrganizationSubject[];
  selection: RailSelection;
  loading: boolean;
  onChanged: () => void;
}

/**
 * Main pane of the global Notes page.
 *
 * Renders the breadcrumb for the current selection, then a list of
 * note tiles (or an empty state). Each tile carries a "Move to"
 * dropdown that re-files the note by calling /api/notes/{id}/folder.
 *
 * "Unsorted" selection is the one case where the client filters: the
 * server returns every note in the subject, and we drop the ones that
 * already have a folder. The pane filter is intentionally local so we
 * don't add another shape to the GET /api/notes contract for a single
 * UI affordance.
 */
export function NotesPane({
  notes,
  subjects,
  selection,
  loading,
  onChanged
}: NotesPaneProps) {
  const filtered = useMemo(() => {
    if (selection.kind === "unsorted") {
      return notes.filter((n) => n.folder_id === null);
    }
    return notes;
  }, [notes, selection]);

  return (
    <section aria-label="Notes" className={styles.pane}>
      <SelectionHeader selection={selection} count={filtered.length} />

      {loading && filtered.length === 0 ? (
        <div className={styles.skeleton} aria-hidden>
          <div className={styles.skeletonTile} />
          <div className={styles.skeletonTile} />
          <div className={styles.skeletonTile} />
        </div>
      ) : null}

      {!loading && filtered.length === 0 ? (
        <EmptyState selection={selection} />
      ) : null}

      <ul className={styles.list}>
        {filtered.map((note) => (
          <NoteTile
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

function SelectionHeader({
  selection,
  count
}: {
  selection: RailSelection;
  count: number;
}) {
  let label: string;
  switch (selection.kind) {
    case "all":
      label = "All notes";
      break;
    case "subject":
      label = selection.subject;
      break;
    case "folder":
      label = `${selection.subject} · ${selection.name}`;
      break;
    case "unsorted":
      label = `${selection.subject} · Unsorted`;
      break;
    case "orphan":
      label = "Unfiled";
      break;
  }
  const noun = count === 1 ? "note" : "notes";
  return (
    <header className={styles.selectionHeader}>
      <h2 className={styles.selectionTitle}>{label}</h2>
      <Text tone="tertiary" variant="caption">
        {count} {noun}
      </Text>
    </header>
  );
}

function EmptyState({ selection }: { selection: RailSelection }) {
  let title: string;
  let body: string;
  switch (selection.kind) {
    case "all":
      title = "No notes yet.";
      body =
        "Save a note from the Reader's Notes tab and it will show up here. Make folders to organize them per subject.";
      break;
    case "subject":
      title = `No notes under ${selection.subject} yet.`;
      body =
        "Open a source in this subject and save a note from the Reader. It will land here under " +
        `${selection.subject}.`;
      break;
    case "folder":
      title = `${selection.name} is empty.`;
      body =
        "Move notes into this folder from the dropdown on any tile, or save a new note from the Reader.";
      break;
    case "unsorted":
      title = `Everything in ${selection.subject} is already filed.`;
      body =
        "Notes you save from the Reader land here first. Once you move them into a folder they leave this list.";
      break;
    case "orphan":
      title = "No unfiled notes.";
      body =
        "A note ends up here when it has no source document and isn't assigned to a folder.";
      break;
  }
  return (
    <div className={styles.empty}>
      <Icon name="study" size={20} />
      <p className={styles.emptyTitle}>{title}</p>
      <p className={styles.emptyBody}>{body}</p>
    </div>
  );
}

interface NoteTileProps {
  note: NoteRecord;
  subjects: NoteOrganizationSubject[];
  onChanged: () => void;
}

function NoteTile({ note, subjects, onChanged }: NoteTileProps) {
  const [moving, setMoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onMove = async (event: Event) => {
    const value = (event.currentTarget as HTMLSelectElement).value;
    const next = value === "" ? null : value;
    if (next === (note.folder_id ?? null)) return;
    setMoving(true);
    setError(null);
    try {
      await notesApi.move(note.id, next);
      onChanged();
    } catch (err) {
      setError((err as Error).message || "Could not move the note.");
    } finally {
      setMoving(false);
    }
  };

  return (
    <li className={styles.tile}>
      <div className={styles.tileHeader}>
        <h3 className={styles.tileTitle}>{note.title || "Untitled note"}</h3>
        <span className={styles.tileSubject}>{note.subject}</span>
      </div>
      {note.content ? <p className={styles.tileBody}>{note.content}</p> : null}
      <footer className={styles.tileFooter}>
        <div className={styles.tileMeta}>
          {note.document_name ? (
            <span title={note.document_name} className={styles.tileMetaItem}>
              <Icon name="doc" size={12} />
              <span>{note.document_name}</span>
            </span>
          ) : null}
          {note.folder_name ? (
            <span className={styles.tileMetaItem}>
              <Icon name="library" size={12} />
              <span>{note.folder_name}</span>
            </span>
          ) : null}
        </div>
        <label className={styles.moveLabel}>
          <span className={styles.srOnly}>Move to folder</span>
          <select
            className={styles.moveSelect}
            value={note.folder_id ?? ""}
            onChange={onMove}
            disabled={moving}
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
      {error ? (
        <p className={styles.tileError} role="alert">
          {error}
        </p>
      ) : null}
    </li>
  );
}
