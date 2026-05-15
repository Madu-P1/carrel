import { useEffect, useMemo, useState } from "preact/hooks";

import { Text } from "@/design-system";
import { createQuery } from "@/lib/query";
import { notes as notesApi, type NoteRecord } from "@/services/api/endpoints";

import { SubjectRail, type RailSelection } from "./components/SubjectRail";
import { NotesPane } from "./components/NotesPane";
import styles from "./NotesPage.module.css";

/**
 * Global Notes page.
 *
 * Layout: header above, then a two-column body: SubjectRail on the
 * left (subject groups, folders, counts, folder CRUD) and NotesPane on
 * the right (the actual note tiles for whatever the rail has selected).
 *
 * State here is intentionally thin: one selection object the rail
 * controls, two queries (organization for the rail, notes for the
 * pane) that refetch on every mutation. The "always-refetch" pattern
 * costs one extra round-trip per move/create but it keeps counts and
 * subject-resolution honest without us re-implementing the COALESCE
 * rule on the client.
 *
 * Selection model:
 *   { kind: "all" }                        all notes, default
 *   { kind: "subject", subject: "Math" }   any note resolved to Math
 *   { kind: "folder",  folder: <id>,
 *     subject: "Math", name: "Lectures" }  notes inside the folder
 *   { kind: "unsorted", subject: "Math" }  Math notes with no folder
 *   { kind: "orphan" }                     notes with no folder + no doc
 */
export function NotesPage() {
  const [selection, setSelection] = useState<RailSelection>({ kind: "all" });

  const organizationQuery = useMemo(
    () => createQuery(() => notesApi.organization()),
    []
  );
  useEffect(() => {
    const unsubscribe = organizationQuery.subscribe();
    void organizationQuery.refetch();
    return unsubscribe;
  }, [organizationQuery]);

  // Notes query is keyed by selection so switching subjects/folders
  // creates a fresh signal and the user doesn't briefly see the
  // previous selection's rows while the new fetch is in flight.
  // Selection identity changes on every setState, which is exactly
  // what we want here: any selection change triggers a refetch via
  // the dep on `notesQuery` in the useEffect below.
  const notesQuery = useMemo(
    () => createQuery(() => notesApi.list(notesListParams(selection))),
    [selection]
  );
  useEffect(() => {
    const unsubscribe = notesQuery.subscribe();
    void notesQuery.refetch();
    return unsubscribe;
  }, [notesQuery]);

  const subjects = organizationQuery.data.value?.subjects ?? [];
  const notes: NoteRecord[] = notesQuery.data.value?.notes ?? [];

  const refreshAll = () => {
    void organizationQuery.refetch();
    void notesQuery.refetch();
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.headerCopy}>
          <span className={styles.eyebrow}>Notes</span>
          <h1 className={styles.heading}>Your notes.</h1>
          <Text tone="secondary" variant="body">
            Grouped by subject. Folders are yours to organize within
            each subject. Notes you make in the Reader land here too.
          </Text>
        </div>
      </header>

      <div className={styles.body}>
        <SubjectRail
          subjects={subjects}
          selection={selection}
          loading={organizationQuery.loading.value ?? false}
          onSelect={setSelection}
          onChanged={refreshAll}
        />
        <NotesPane
          notes={notes}
          subjects={subjects}
          selection={selection}
          loading={notesQuery.loading.value ?? false}
          onChanged={refreshAll}
        />
      </div>
    </div>
  );
}

function notesListParams(selection: RailSelection) {
  // The page only ever asks for one "bucket" at a time. limit is
  // bumped to a high enough ceiling that we don't surprise a power
  // user; v2 will add pagination + search.
  switch (selection.kind) {
    case "all":
      return { limit: 500 };
    case "subject":
      return { subject_name: selection.subject, limit: 500 };
    case "folder":
      return { folder_id: selection.folder, limit: 500 };
    case "unsorted":
      // Unsorted-in-a-subject: notes in this subject's pool that
      // aren't assigned to any folder. The server filters subject
      // first; we further drop foldered notes on the client because
      // composing folder_id=none AND subject_name on the server
      // would be a fourth code path I don't want to maintain yet.
      return { subject_name: selection.subject, limit: 500 };
    case "orphan":
      return { subject_name: "Unfiled", limit: 500 };
  }
}

