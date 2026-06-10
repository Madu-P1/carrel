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

import { documents as documentsApi, vaults as vaultsApi } from "@/services/api/endpoints";
import type { DocumentUploadResponse } from "@/services/api/endpoints";
import { uploadWithProgress } from "@/services/upload/withProgress";

/** The default vault a record is filed into when the user does not pick one.
 *  Matches the engine's schema default subject_name ('General'). The folder
 *  concept reads as "vault" in the UI; the identifier stays `project` (mapping to
 *  subject_name) until the vault-management redesign renames the internals. */
export const DEFAULT_PROJECT = "General";

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

/** True when the URL asks for the Sources visual fixture. Pure parse; the
 *  caller must ALSO gate on import.meta.env.DEV so the fixture branch (and its
 *  fake records) compiles out of production builds entirely. */
export function sourcesFixtureRequested(search: string): boolean {
  return new URLSearchParams(search).get("fixture") === "sources";
}

/** Drop the PERSISTED active record without clearing the in-memory signal.
 *  The dev fixture uses this so its fake record never survives the fixture
 *  page into a later real session via localStorage. */
export function clearPersistedActiveRecord(): void {
  try {
    globalThis.localStorage?.removeItem(ACTIVE_RECORD_KEY);
  } catch {
    /* localStorage blocked — nothing was persisted anyway */
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

/** Every vault (folder) the backend knows about: the union of the subjects records
 *  are filed under and the empty-vault registry. `null` until first loaded. This is
 *  what lets an empty, just-created vault show before it holds any record. */
export const vaultNames = signal<string[] | null>(null);

/** Distinct vault names: the registry (so empty vaults show), the subjects records
 *  are filed under, and the default. Merged so a picker is consistent whether a
 *  vault was created empty or implied by a filed record. */
export function knownProjects(): string[] {
  // Vault identity is case-insensitive: "General" and "general" are one vault, not
  // two. The first spelling seen wins, in priority order: the registry (the
  // canonical folder name), then the default, then the subjects records are filed
  // under. So a folder created as "General" keeps that spelling even if a record
  // was filed under "general".
  const byLower = new Map<string, string>();
  const add = (name: string) => {
    const key = name.toLowerCase();
    if (!byLower.has(key)) byLower.set(key, name);
  };
  for (const name of vaultNames.value ?? []) {
    if (name) add(name);
  }
  add(DEFAULT_PROJECT);
  for (const d of sourceDocs.value ?? []) {
    if (d.project) add(d.project);
  }
  return [...byLower.values()].sort((a, b) => a.localeCompare(b));
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
    // Validate the persisted active record against the library we just got.
    // The localStorage pointer can outlive its database (a record ingested by
    // an earlier server instance): the lectern then asserts "loaded as the
    // record" while the engine resolves the docId to nothing and every check
    // honestly refuses — the screen contradicts itself about session state.
    // Clearing only on a SUCCESSFUL fetch: an offline backend proves nothing.
    const active = loadedSource.value;
    if (active && !rows.some((d) => d.id === active.docId)) {
      loadedSource.value = null;
    }
  } catch (e) {
    sourcesError.value = e instanceof Error ? e.message : "Your records could not be loaded.";
    if (sourceDocs.value === null) sourceDocs.value = [];
  }
}

/** Load the vault list (registry + filed subjects) so empty vaults show. Errors are
 *  non-fatal: the records list still derives its own vaults, so a failed vault fetch
 *  just hides the empty ones rather than breaking the page. */
export async function refreshVaults(): Promise<void> {
  try {
    const { vaults } = await vaultsApi.list();
    vaultNames.value = vaults;
  } catch {
    if (vaultNames.value === null) vaultNames.value = [];
  }
}

/** Create a (possibly empty) vault, then resync the list from the response. Throws
 *  on failure (e.g. a blank name); the caller surfaces it. */
export async function createVault(name: string): Promise<void> {
  const { vaults } = await vaultsApi.create(name);
  vaultNames.value = vaults;
}

/** Forget an empty vault. The backend refuses (409) if any record is still filed
 *  under it, so this throws rather than silently moving records; the caller surfaces
 *  the message. Resyncs both the vault list and the records on success. */
export async function deleteVault(name: string): Promise<void> {
  await vaultsApi.remove(name);
  await Promise.all([refreshVaults(), refreshSources()]);
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

/** Permanently delete a record from the library and everything Cachet ingested
 *  from it (chunks, nodes, anchors, embeddings). Irreversible. If the deleted
 *  record was the active one, the next verify is left with nothing to check
 *  against (the lectern's refusal CTA then guides the user back here). Refreshes
 *  the list so the row disappears. Throws on failure; the caller surfaces it. */
export async function deleteDocument(docId: string): Promise<void> {
  await documentsApi.delete(docId);
  if (loadedSource.value?.docId === docId) {
    loadedSource.value = null;
  }
  await refreshSources();
}
