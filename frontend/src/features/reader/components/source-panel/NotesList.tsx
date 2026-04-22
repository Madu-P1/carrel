import { Pane, Text } from "@/design-system";

import styles from "./SourcePanel.module.css";

interface NoteLike {
  content?: string;
  title?: string;
}

export function NotesList({ notes }: { notes: NoteLike[] }) {
  return (
    <Pane title={`Notes (${notes.length})`}>
      <div className={styles.notesList}>
        {notes.map((note, index) => (
          <div className={styles.noteItem} key={`${note.title ?? "note"}-${index}`}>
            <Text weight="semibold">{note.title || "Untitled note"}</Text>
            {note.content ? <Text tone="secondary">{note.content}</Text> : null}
          </div>
        ))}
      </div>
    </Pane>
  );
}
