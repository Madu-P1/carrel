import { EmptyState } from "./EmptyState";
import styles from "./SourcePanel.module.css";

interface NoteLike {
  content?: string;
  title?: string;
}

export function NotesList({ notes }: { notes: NoteLike[] }) {
  if (notes.length === 0) {
    return (
      <EmptyState
        icon="study"
        title="No notes on this source yet."
        description="Open a chunk and press N to start a note. Notes you take here show up alongside the chunk they anchor to."
      />
    );
  }

  return (
    <ul className={styles.rowList}>
      {notes.map((note, index) => (
        <li
          className={styles.noteRow}
          key={`${note.title ?? "note"}-${index}`}
        >
          <div className={styles.rowHeader}>
            <span className={styles.rowTitle}>{note.title || "Untitled note"}</span>
          </div>
          {note.content ? <p className={styles.rowPreview}>{note.content}</p> : null}
        </li>
      ))}
    </ul>
  );
}
