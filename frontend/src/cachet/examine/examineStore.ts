/**
 * The document under examination, app-wide.
 *
 * Same survival story as liveDraft / lecternVerify: the Cachet shell swaps
 * views by route and UNMOUNTS the current view on every move, so an open
 * examination held in a view's own state would vanish on a rail click. The
 * overlay is mounted once at the CachetApp level and driven by this
 * module-scope signal, so an open record survives navigation and any view
 * (the Examination drawer's sources, the Vault's records) can open it.
 */
import { signal } from "@preact/signals";

export interface ExaminationRequest {
  docId: string;
  /** Display name in the header (the record's filename or document name). */
  filename: string;
  /** Engine file_type when the caller already knows it ("pdf", "docx", "txt");
   *  resolved from the engine when absent. */
  fileType?: string | null;
  /** Cited page (1-based) to land on, when known. */
  page?: number | null;
  /** The cited passage to anchor, verbatim from the verdict. Optional: the
   *  Vault opens records with no anchor. */
  quote?: string | null;
}

export const examination = signal<ExaminationRequest | null>(null);

/** True while a DocumentExamination host is mounted (the Cachet shell mounts
 *  one; the Carrel host does not). Shared surfaces like SourceInspector gate
 *  their "Open the document" affordance on this so they never offer an
 *  action that has no host to render it. */
export const examinationHostMounted = signal(false);

export function openExamination(request: ExaminationRequest): void {
  examination.value = request;
}

export function closeExamination(): void {
  examination.value = null;
}
