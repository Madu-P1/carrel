import { useEffect, useMemo, useState } from "preact/hooks";

import { enterNotesRailMode, navigateTo } from "@/app/shell/useAppShell";
import { createQuery } from "@/lib/query";
import {
  notes as notesApi,
  type NoteRecord,
  type SavedNote
} from "@/services/api/endpoints";

import { NotesPane } from "./components/NotesPane";
import {
  notesOrganizationQuery,
  notesSelection,
  refreshNotesOrganization,
  type RailSelection
} from "./state";
import styles from "./NotesPage.module.css";

/**
 * Global Notes page — Stillwater (Phase A).
 *
 * Now a single-column page: the rail content lives in the AppShell's
 * WorkspaceSidebar slot (one Carrel brand mark across the whole app,
 * smoothly swapping rail content on /notes). This component owns only
 * the main pane: hero, action bar, Unsorted Inbox, subject blocks,
 * note tiles, footer.
 *
 * State is shared with the rail via module-level signals in `./state`:
 * the selection, the organization query, and the pending-expand id.
 * Both consumers subscribe independently; refreshes refetch the same
 * underlying query.
 */
export function NotesPage() {
  const selection = notesSelection.value;
  // Visible error state for "+ New note" so a failure (e.g. 403 from
  // the token gate when running in Vite dev without a matching
  // CARREL_LOCAL_API_TOKEN) surfaces in the UI instead of silently
  // logging to the console. Karpathy lesson learned: do not swallow
  // errors that block the user's primary action.
  const [newNoteError, setNewNoteError] = useState<string | null>(null);

  // Subscribe to the organization query so NotesPage stays
  // re-rendering when subjects/folders change. SubjectRail (rendered
  // in the AppShell) subscribes independently.
  useEffect(() => {
    const unsubscribe = notesOrganizationQuery.subscribe();
    void notesOrganizationQuery.refetch();
    return unsubscribe;
  }, []);

  // Reset rail-replacement to "Notes content" every time NotesPage
  // mounts. Without this, a user who tapped the brand mark to surface
  // the global nav, navigated away, then navigated back to /notes
  // would land in workspace-nav mode instead of the Notes-rail mode
  // they'd expect by default.
  useEffect(() => {
    enterNotesRailMode();
  }, []);

  // The notes list query is keyed by selection — switching subjects
  // creates a fresh query so the user doesn't briefly see stale rows
  // from the previous bucket.
  const notesQuery = useMemo(
    () => createQuery(() => notesApi.list(notesListParams(selection))),
    [selection]
  );
  useEffect(() => {
    const unsubscribe = notesQuery.subscribe();
    void notesQuery.refetch();
    return unsubscribe;
  }, [notesQuery]);

  const subjects = notesOrganizationQuery.data.value?.subjects ?? [];
  const notes: NoteRecord[] = notesQuery.data.value?.notes ?? [];

  const refreshAll = () => {
    refreshNotesOrganization();
    void notesQuery.refetch();
  };

  const handleNewNote = async () => {
    // "+ New note": create a doc-less workspace note and navigate to
    // the full-page editor at /notes/:id. The server enforces
    // content.min_length=1, so we seed with "\n"; NoteEditor clears
    // it visually on mount so the user sees an empty page.
    setNewNoteError(null);
    try {
      const created: { note: SavedNote } = await notesApi.save({
        title: "Untitled note",
        content: "\n",
        note_type: "workspace_note"
      });
      refreshNotesOrganization();
      navigateTo(`/notes/${encodeURIComponent(created.note.id)}`);
    } catch (err) {
      // Visible error. The most common cause in dev is a missing/
      // mismatched local API token between Vite (frontend) and the
      // Python backend; the bundled macOS app handles this via
      // WKUserScript injection. Surface the real message so the user
      // can diagnose without opening the browser console.
      const message = (err as Error).message || "Could not create the note.";
      const hint = /token/i.test(message)
        ? " (Vite dev: set VITE_CARREL_LOCAL_API_TOKEN in frontend/.env to match the backend's CARREL_LOCAL_API_TOKEN, or use the bundled app.)"
        : "";
      setNewNoteError(`${message}${hint}`);
    }
  };

  return (
    <div className={styles.page} data-stillwater="true">
      <NotesPane
        notes={notes}
        subjects={subjects}
        selection={selection}
        loading={notesQuery.loading.value ?? false}
        onChanged={refreshAll}
        onNewNote={() => void handleNewNote()}
        newNoteError={newNoteError}
        onDismissNewNoteError={() => setNewNoteError(null)}
      />
    </div>
  );
}

function notesListParams(selection: RailSelection) {
  switch (selection.kind) {
    case "all":
      return { limit: 500 };
    case "subject":
      return { subject_name: selection.subject, limit: 500 };
    case "folder":
      return { folder_id: selection.folder, limit: 500 };
    case "unsorted":
      return { subject_name: selection.subject, limit: 500 };
    case "orphan":
      return { subject_name: "Unfiled", limit: 500 };
    case "inbox":
      return { folder_id: "none", limit: 500 };
    case "this-week":
      // Backend `this_week=1` filter ships with the FTS5 endpoint
      // (Phase A migration 0021); until then we fall back to all-notes.
      return { limit: 500 };
  }
}
