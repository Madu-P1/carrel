import { signal } from "@preact/signals";

import { createQuery } from "@/lib/query";
import { notes as notesApi } from "@/services/api/endpoints";

/**
 * Shared state for the /notes feature.
 *
 * The Notes-specific rail used to be rendered inside `NotesPage`, which
 * left two Carrel logos visible (one in the AppShell, one in the page).
 * Now the AppShell's WorkspaceSidebar swaps its middle nav section for
 * the Notes Workspace+Subjects content when the user is on /notes.
 *
 * That means TWO consumers (WorkspaceSidebar rendering the rail body,
 * and NotesPage rendering the main pane) need to read the same
 * selection + the same organization query. Lifting them to a module-
 * level signal is the cheapest sharing mechanism.
 */

export type RailSelection =
  | { kind: "all" }
  | { kind: "inbox" }
  | { kind: "this-week" }
  | { kind: "subject"; subject: string }
  | { kind: "folder"; folder: string; subject: string; name: string }
  | { kind: "unsorted"; subject: string }
  | { kind: "orphan" };

/** Current Notes-page rail selection. Reset to "all" on a "+ New note"
 *  so the just-created note is visible in the flat list. */
export const notesSelection = signal<RailSelection>({ kind: "all" });

/** Id of the note that should mount expanded (e.g. just created via
 *  "+ New note"). Consumed once by the tile and cleared when the user
 *  changes selection. */
export const notesPendingExpandId = signal<string | null>(null);

/** Organization query: subjects + folders + counts. One singleton so
 *  the rail and the main pane stay in sync. */
export const notesOrganizationQuery = createQuery(() => notesApi.organization());

export function setNotesSelection(next: RailSelection): void {
  notesSelection.value = next;
  notesPendingExpandId.value = null;
}

export function setPendingExpandId(id: string | null): void {
  notesPendingExpandId.value = id;
}

export function refreshNotesOrganization(): void {
  void notesOrganizationQuery.refetch();
}
