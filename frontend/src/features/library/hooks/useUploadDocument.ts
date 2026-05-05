import { useSignal } from "@preact/signals";

import { ApiError } from "@/services/api/client";
import { jobs } from "@/services/api/endpoints";
import { events } from "@/services/metrics/events";

/**
 * Outcome shape for a single file in a batch upload.
 *
 * The dropzone accepts multiple files at once (drag-and-drop OR multi-select).
 * A duplicate in the middle of a batch should NOT abort the rest — the user
 * dropped 6 PDFs, one was already in the library, the other 5 should still
 * ingest. We surface per-file outcomes so the UI can show an honest summary:
 * "4 ingested, 1 already in library, 1 failed."
 */
export type UploadOutcome =
  | {
      kind: "ok";
      filename: string;
      docId: string;
      jobId?: string;
    }
  | {
      kind: "duplicate";
      filename: string;
      existingDocId: string;
      existingFilename: string;
      existingSubject: string | null;
      message: string;
    }
  | {
      kind: "error";
      filename: string;
      message: string;
      /** The original File so the dropzone can offer "Retry failed" without
       *  asking the user to re-select. Optional only because tests and future
       *  error paths may populate this outcome shape without a File handle. */
      file?: File;
    };

interface DuplicateDetail {
  code?: string;
  message?: string;
  existing_doc_id?: string;
  existing_filename?: string;
  existing_subject?: string | null;
}

function isDuplicateDetail(body: unknown): body is DuplicateDetail {
  if (!body || typeof body !== "object") return false;
  const detail = (body as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object") return false;
  return (detail as { code?: unknown }).code === "duplicate_source";
}

function extractDuplicate(body: unknown): DuplicateDetail | null {
  if (!isDuplicateDetail(body)) return null;
  return (body as { detail: DuplicateDetail }).detail;
}

function uploadErrorMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    const detail = (caught.body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return message;
    }
  }
  return caught instanceof Error ? caught.message : String(caught);
}

export function useUploadDocument() {
  const loading = useSignal(false);
  /** Legacy fatal-error signal, kept for callers that only care about the
   * last hard failure. New callers should read `outcomes` instead. */
  const error = useSignal<Error | null>(null);
  const outcomes = useSignal<UploadOutcome[]>([]);

  const uploadFiles = async (files: FileList | File[], subjectName = "General"): Promise<UploadOutcome[]> => {
    loading.value = true;
    error.value = null;
    const batch = Array.from(files);
    void events.track("import.started", { file_count: batch.length }, "library");
    const results: UploadOutcome[] = [];
    try {
      for (const file of batch) {
        void events.track("first_source_import_started", {
          bytes: file.size,
          file_type: file.type || file.name.split(".").pop()?.toLowerCase() || "unknown"
        }, "library");
        try {
          const response = await jobs.import(file, subjectName);
          results.push({
            kind: "ok",
            filename: file.name,
            docId: response.job.document_id ?? "",
            jobId: response.job.id
          });
        } catch (caught) {
          if (caught instanceof ApiError && caught.status === 409) {
            const dup = extractDuplicate(caught.body);
            if (dup) {
              results.push({
                kind: "duplicate",
                filename: file.name,
                existingDocId: String(dup.existing_doc_id ?? ""),
                existingFilename: String(dup.existing_filename ?? file.name),
                existingSubject: dup.existing_subject ?? null,
                message:
                  dup.message ??
                  `“${file.name}” is already in your library.`
              });
              continue;
            }
          }
          const message = uploadErrorMessage(caught);
          results.push({ kind: "error", filename: file.name, message, file });
          // Keep the legacy .error signal populated with the first hard
          // failure so old UI branches still light up.
          if (!error.value) {
            error.value = caught instanceof Error ? caught : new Error(message);
          }
        }
      }
      outcomes.value = results;
      const okCount = results.filter((result) => result.kind === "ok").length;
      const duplicateCount = results.filter((result) => result.kind === "duplicate").length;
      const failedCount = results.filter((result) => result.kind === "error").length;
      if (okCount > 0) {
        void events.track("import.completed", {
          duplicate_count: duplicateCount,
          failed_count: failedCount,
          file_count: okCount
        }, "library");
      }
      if (failedCount > 0) {
        void events.track("import.failed", {
          duplicate_count: duplicateCount,
          failed_count: failedCount,
          file_count: batch.length
        }, "library");
      }
      return results;
    } finally {
      loading.value = false;
    }
  };

  const clearOutcomes = () => {
    outcomes.value = [];
    error.value = null;
  };

  /**
   * Re-run just the files that failed in the most recent batch. Duplicates
   * aren't retried — they aren't failures; the server already has that
   * content and re-uploading would just hit the same 409. No File handle
   * means the error outcome came from a code path that didn't track the
   * original; we silently skip it.
   */
  const retryFailed = async (subjectName = "General"): Promise<UploadOutcome[] | null> => {
    const retriable = outcomes.value
      .filter((o): o is Extract<UploadOutcome, { kind: "error" }> => o.kind === "error")
      .map((o) => o.file)
      .filter((f): f is File => f instanceof File);
    if (retriable.length === 0) return null;
    return uploadFiles(retriable, subjectName);
  };

  return { uploadFiles, loading, error, outcomes, clearOutcomes, retryFailed };
}
