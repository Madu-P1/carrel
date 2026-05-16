import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import {
  type NoteOrganizationSubject,
  type NoteRecord
} from "@/services/api/endpoints";

import type { RailSelection } from "../state";
import { Ic } from "./NotesIcons";
import { NoteTile } from "./NoteTile";
import { UnsortedInbox } from "./UnsortedInbox";
import styles from "./NotesPane.module.css";

interface NotesPaneProps {
  notes: NoteRecord[];
  subjects: NoteOrganizationSubject[];
  selection: RailSelection;
  loading: boolean;
  onChanged: () => void;
  onNewNote: () => void;
  initialExpandedId: string | null;
}

/**
 * Main content pane — Stillwater.
 *
 * Top-down layout (all in one scrolling column):
 *   - Hero: eyebrow date + serif title + sub-copy
 *   - Action bar: full-width search input + "+ New note" primary button
 *   - Unsorted Inbox card (shows up when selection is "all" or "inbox")
 *   - Subject blocks: one per subject with notes, serif title + meta line,
 *     then a stack of NoteTile rows
 *   - Footer: mono "end of library" + sync line
 *
 * When the rail selects a specific subject / folder / unsorted-in-subject,
 * we hide the Unsorted Inbox card (it would be misleading at that scope)
 * and show only the relevant subject block.
 */
export function NotesPane({
  notes,
  subjects,
  selection,
  loading,
  onChanged,
  onNewNote,
  initialExpandedId
}: NotesPaneProps) {
  const [expandedId, setExpandedId] = useState<string | null>(initialExpandedId);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  // Sync expanded state to the prop on remount (e.g. "+ New note"
  // sets a new expanded id from the parent). useEffect, not useMemo —
  // this is a side effect, not a memo.
  useEffect(() => {
    if (initialExpandedId && initialExpandedId !== expandedId) {
      setExpandedId(initialExpandedId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialExpandedId]);

  // ⌘K from anywhere on the page focuses the search input. Matches
  // the kbd hint shown next to the search field. Limited to keydown
  // (not keypress) so it triggers reliably across keyboard layouts.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Group notes by their resolved subject. We use the COALESCE-resolved
  // subject from the server (note.subject) so the grouping matches the
  // rail counts. Unsorted-in-a-subject filter is applied client-side.
  const filteredNotes = useMemo(() => {
    if (selection.kind === "unsorted") {
      return notes.filter((n) => n.folder_id === null);
    }
    return notes;
  }, [notes, selection]);

  const grouped = useMemo(() => {
    const groups = new Map<string, NoteRecord[]>();
    for (const note of filteredNotes) {
      const key = note.subject || "Unfiled";
      const bucket = groups.get(key) ?? [];
      bucket.push(note);
      groups.set(key, bucket);
    }
    // Stable ordering: real subjects alphabetically, Unfiled last.
    return Array.from(groups.entries()).sort(([a], [b]) => {
      if (a === b) return 0;
      if (a === "Unfiled") return 1;
      if (b === "Unfiled") return -1;
      return a.localeCompare(b);
    });
  }, [filteredNotes]);

  const showInbox =
    selection.kind === "all" || selection.kind === "inbox";

  const totalNotes = filteredNotes.length;

  return (
    <main className={styles.main}>
      <Hero />

      <ActionBar onNewNote={onNewNote} searchInputRef={searchInputRef} />

      {showInbox ? (
        <UnsortedInbox
          notes={notes}
          subjects={subjects}
          onChanged={onChanged}
        />
      ) : null}

      {loading && filteredNotes.length === 0 ? (
        <div className={styles.skeleton} aria-hidden>
          <div className={styles.skeletonTile} />
          <div className={styles.skeletonTile} />
          <div className={styles.skeletonTile} />
        </div>
      ) : null}

      {!loading && filteredNotes.length === 0 ? (
        <EmptyState selection={selection} onNewNote={onNewNote} />
      ) : null}

      {grouped.map(([subjectName, subjectNotes]) => (
        <section key={subjectName} className={styles.subjectBlock}>
          <div className={styles.subjectHead}>
            <h2 className={styles.subjectTitle}>{subjectName}</h2>
            <div className={styles.subjectMeta}>
              <span>{subjectNotes.length} notes</span>
              {subjectFolderCount(subjects, subjectName) > 0 ? (
                <>
                  <span className={styles.dot}>·</span>
                  <span>
                    {subjectFolderCount(subjects, subjectName)} folders
                  </span>
                </>
              ) : null}
            </div>
          </div>
          <ul className={styles.tiles}>
            {subjectNotes.map((note) => (
              <NoteTile
                key={note.id}
                note={note}
                subjects={subjects}
                expanded={note.id === expandedId}
                onExpand={(next) => setExpandedId(next ? note.id : null)}
                onChanged={onChanged}
              />
            ))}
          </ul>
        </section>
      ))}

      {totalNotes > 0 ? (
        <footer className={styles.foot}>
          <span className={styles.footMono}>end of library</span>
          <span className={styles.footDim}>
            · {totalNotes} {totalNotes === 1 ? "note" : "notes"} · local-first
          </span>
        </footer>
      ) : null}
    </main>
  );
}

function Hero() {
  // The date/time eyebrow that the Stillwater canvas used was redundant
  // against the system clock + Carrel's own greeting on the Dashboard.
  // Dropped per founder feedback 2026-05-16; the hero now leads with
  // the serif title and lets the page breathe.
  return (
    <header className={styles.hero}>
      <h1 className={styles.heroTitle}>
        Your thinking, your sources,
        <br />
        in one place.
      </h1>
      <p className={styles.heroSub}>
        Read in the Reader. Write here. Review next morning. Every note
        cites itself.
      </p>
    </header>
  );
}

interface ActionBarProps {
  onNewNote: () => void;
  searchInputRef: { current: HTMLInputElement | null };
}

function ActionBar({ onNewNote, searchInputRef }: ActionBarProps) {
  return (
    <div className={styles.actionbar}>
      <label className={styles.search}>
        <Ic.search className={styles.searchIc} />
        <input
          ref={searchInputRef}
          className={styles.searchInput}
          placeholder="Search notes, sources, or a phrase you wrote…"
          defaultValue=""
          aria-label="Search notes"
        />
        <kbd className={styles.kbd}>⌘K</kbd>
      </label>
      <button
        type="button"
        className={styles.newNote}
        onClick={onNewNote}
      >
        <Ic.plus />
        <span>New note</span>
      </button>
    </div>
  );
}

function EmptyState({
  selection,
  onNewNote
}: {
  selection: RailSelection;
  onNewNote: () => void;
}) {
  // Initialize with a safe fallback so TypeScript doesn't flag a path
  // through the switch as undefined (the union has 7 cases and TS's
  // narrowing analysis doesn't prove exhaustiveness for late-introduced
  // kinds like "inbox" / "this-week"). The fallback never renders.
  let title = "No notes here.";
  let body = "Save a note in the Reader or create a workspace note to start.";
  switch (selection.kind) {
    case "all":
      title = "No notes yet.";
      body =
        "Save a note from the Reader's Notes tab or hit “+ New note” to start your library.";
      break;
    case "inbox":
      title = "Inbox is empty.";
      body =
        "Every note you have is filed. Save a new one in the Reader and it will land here for triage.";
      break;
    case "this-week":
      title = "Nothing from this week yet.";
      body =
        "Notes you write or revise in the next 7 days will show up here.";
      break;
    case "subject":
      title = `No notes under ${selection.subject}.`;
      body =
        "Open a source in this subject and save a note from the Reader — it will land here.";
      break;
    case "folder":
      title = `${selection.name} is empty.`;
      body =
        "Move notes into this folder from any tile, or use the Unsorted Inbox at the top of the page.";
      break;
    case "unsorted":
      title = `${selection.subject} is fully filed.`;
      body =
        "Notes you save from the Reader start here, then move into a folder when you triage.";
      break;
    case "orphan":
      title = "No unfiled notes.";
      body =
        "A note ends up here when it has no source document and isn't assigned to a folder.";
      break;
  }

  return (
    <div className={styles.empty}>
      <p className={styles.emptyTitle}>{title}</p>
      <p className={styles.emptyBody}>{body}</p>
      {selection.kind === "all" || selection.kind === "inbox" ? (
        <button
          type="button"
          className={styles.emptyCta}
          onClick={onNewNote}
        >
          <Ic.plus />
          <span>New note</span>
        </button>
      ) : null}
    </div>
  );
}

function subjectFolderCount(
  subjects: NoteOrganizationSubject[],
  name: string
): number {
  const subject = subjects.find((s) => s.name === name);
  return subject ? subject.folders.length : 0;
}
