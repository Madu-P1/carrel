/**
 * The records (Sources) Cachet checks drafts against, and the "which record am I
 * verifying against right now" selection.
 *
 * Cachet's in-house wedge: the lawyer loads the executed contract / brief / exhibit
 * here, files it into a project, then verifies an AI's claims against it. This module
 * owns the upload, the list of ingested records, the project (subject) a record is
 * filed under, and the active record. Shared by the Sources view (manage + organise)
 * and the lectern (attach + a compact indicator). The shared VerifyView stays
 * host-agnostic: the Cachet shell reads `loadedSource` and passes its doc id as a
 * prop, so Carrel is untouched.
 *
 * Projects map onto the engine's existing `subject_name` grouping — no new backend.
 */
import { signal } from "@preact/signals";

import { documents as documentsApi } from "@/services/api/endpoints";
import type { DocumentUploadResponse } from "@/services/api/endpoints";
import { uploadWithProgress } from "@/services/upload/withProgress";

/** The default project a record is filed into when the user does not pick one. */
export const DEFAULT_PROJECT = "Sources";

export interface LoadedSource {
  docId: string;
  filename: string;
}

/** One ingested record as shown in the Sources library. `project` is the engine's
 *  `subject_name`, defaulted so the UI never has to special-case null. */
export interface SourceDoc {
  id: string;
  filename: string;
  project: string;
  pageCount: number | null;
  fileType: string | null;
}

/** The active record survives app relaunch (the WKWebView is a fresh process each
 *  launch, so an in-memory signal alone loses the loaded record and the next verify
 *  runs with no source to check against — the deterministic catch then comes back
 *  empty). Best-effort: if localStorage is unavailable the in-memory value still works
 *  for the session. */
const ACTIVE_RECORD_KEY = "cachet.activeRecord";
function readActiveRecord(): LoadedSource | null {
  try {
    const raw = globalThis.localStorage?.getItem(ACTIVE_RECORD_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<LoadedSource>;
    return typeof v?.docId === "string" && typeof v?.filename === "string"
      ? { docId: v.docId, filename: v.filename }
      : null;
  } catch {
    return null;
  }
}

/** The record the next verify will be checked against, or null. Restored on load. */
export const loadedSource = signal<LoadedSource | null>(readActiveRecord());
loadedSource.subscribe((v) => {
  try {
    if (v) globalThis.localStorage?.setItem(ACTIVE_RECORD_KEY, JSON.stringify(v));
    else globalThis.localStorage?.removeItem(ACTIVE_RECORD_KEY);
  } catch {
    /* localStorage blocked (e.g. file:// origin) — in-memory still works this session */
  }
});

/** In-flight upload state for the dropzone UX, or null when idle. `fraction` is the
 *  byte-upload progress; once it reaches 1 the request is still open while the backend
 *  extracts (synchronous), so the UI shows "reading" until the promise resolves. */
export const sourceUpload = signal<{ filename: string; fraction: number } | null>(null);

/** Every ingested record. `null` = not loaded yet (show a loading state); `[]` =
 *  loaded and empty (show the empty state). Populated by `refreshSources`. */
export const sourceDocs = signal<SourceDoc[] | null>(null);

/** Non-blocking load error for the records list (the dropzone still works). */
export const sourcesError = signal<string | null>(null);

/** Distinct project names across loaded records, plus the default. Derived (not a
 *  second endpoint) so the picker is always consistent with what is actually filed. */
export function knownProjects(): string[] {
  const set = new Set<string>([DEFAULT_PROJECT]);
  for (const d of sourceDocs.value ?? []) {
    if (d.project) set.add(d.project);
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}

/** Load the full list of ingested records from the engine. Errors surface in
 *  `sourcesError` (no silent fallback) and resolve the loading state so the UI
 *  never hangs on a skeleton. */
export async function refreshSources(): Promise<void> {
  try {
    const rows = await documentsApi.list();
    sourceDocs.value = rows.map((d) => ({
      id: d.id,
      filename: d.filename,
      project: d.subject_name || DEFAULT_PROJECT,
      pageCount: d.page_count ?? null,
      fileType: d.file_type ?? null,
    }));
    sourcesError.value = null;
  } catch (e) {
    sourcesError.value = e instanceof Error ? e.message : "Your records could not be loaded.";
    if (sourceDocs.value === null) sourceDocs.value = [];
  }
}

/** Upload a file as a record, filed into `project`, and ingest it. Resolves once the
 *  document is ingested (the upload endpoint extracts synchronously), sets it as the
 *  active record, and refreshes the list so it appears immediately. Throws on failure;
 *  the caller surfaces it (no silent fallback). */
export async function uploadSource(
  file: File,
  project: string = DEFAULT_PROJECT
): Promise<LoadedSource> {
  sourceUpload.value = { filename: file.name, fraction: 0 };
  try {
    const { body } = await uploadWithProgress<DocumentUploadResponse>(
      "/api/documents/upload",
      file,
      {
        fields: { subject_name: project.trim() || DEFAULT_PROJECT },
        onProgress: (p) => {
          sourceUpload.value = { filename: file.name, fraction: p.fraction };
        }
      }
    );
    const docId = (body as { doc_id?: string } | null)?.doc_id;
    if (!docId) {
      throw new Error("The upload did not return a document id.");
    }
    const next: LoadedSource = { docId, filename: file.name };
    loadedSource.value = next;
    void refreshSources();
    return next;
  } finally {
    sourceUpload.value = null;
  }
}

/** Re-file a record into a different project (the engine's `subject_name`), then
 *  refresh so the list regroups. */
export async function setDocumentProject(docId: string, project: string): Promise<void> {
  await documentsApi.setSubject(docId, project.trim() || DEFAULT_PROJECT);
  await refreshSources();
}

/** Make an already-ingested record the one the next verify checks against.
 *  (Plain setter, not a hook — the name avoids the `use` prefix on purpose.) */
export function setActiveRecord(doc: SourceDoc): void {
  loadedSource.value = { docId: doc.id, filename: doc.filename };
}

/** Forget the active record (the next verify will have nothing to check against).
 *  Does not delete the record from the library. */
export function clearSource(): void {
  loadedSource.value = null;
}
