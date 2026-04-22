import { useState } from "preact/hooks";

import { Button, Spinner, Stack, Text } from "@/design-system";

import { useUploadDocument, type UploadOutcome } from "../hooks/useUploadDocument";
import styles from "./ImportDropzone.module.css";

interface ImportDropzoneProps {
  onUploaded: () => void;
}

/**
 * Renders the per-file outcome summary after a batch upload.
 *
 * Layout:
 *   - Failures FIRST (with a "Retry failed" action) because those demand
 *     attention and tend to get lost when successes dominate.
 *   - Successes next, rendered as a quiet single line.
 *   - Duplicates LAST behind a <details> disclosure so the "4 already here"
 *     noise doesn't bury the real outcomes.
 *
 * Retry only fires for errors: duplicates aren't failures (the server has
 * that content already) and successes obviously don't need retry.
 */
function OutcomeSummary({
  outcomes,
  onDismiss,
  onRetryFailed,
  retrying
}: {
  outcomes: UploadOutcome[];
  onDismiss: () => void;
  onRetryFailed: () => void;
  retrying: boolean;
}) {
  if (outcomes.length === 0) return null;
  const ok = outcomes.filter((o) => o.kind === "ok");
  const dups = outcomes.filter((o) => o.kind === "duplicate");
  const errs = outcomes.filter((o) => o.kind === "error");
  const retriableCount = errs.filter((e) => e.kind === "error" && e.file instanceof File).length;
  return (
    <div className={styles.outcome}>
      <Stack gap={2}>
        <Stack direction="horizontal" gap={2} className={styles.outcomeHeader}>
          <Text variant="h3" weight="semibold">
            Upload result
          </Text>
          <button type="button" onClick={onDismiss} className={styles.outcomeDismiss}>
            Dismiss
          </button>
        </Stack>

        {errs.length > 0 && (
          <div className={styles.outcomeGroup}>
            <Stack direction="horizontal" gap={3} className={styles.outcomeGroupHeader}>
              <Text tone="danger">
                {errs.length === 1 ? "1 file failed." : `${errs.length} files failed.`}
              </Text>
              {retriableCount > 0 && (
                <button
                  className={styles.outcomeRetry}
                  disabled={retrying}
                  onClick={onRetryFailed}
                  type="button"
                >
                  {retrying
                    ? "Retrying…"
                    : retriableCount === 1
                      ? "Retry 1 failed file"
                      : `Retry ${retriableCount} failed files`}
                </button>
              )}
            </Stack>
            <ul className={styles.outcomeList}>
              {errs.map((err) =>
                err.kind === "error" ? (
                  <li key={err.filename} className={styles.outcomeItem}>
                    <span className={styles.outcomeFile}>{err.filename}</span>
                    <span className={styles.outcomeArrow} aria-hidden>
                      →
                    </span>
                    <span className={styles.outcomeError}>{err.message}</span>
                  </li>
                ) : null
              )}
            </ul>
          </div>
        )}

        {ok.length > 0 && (
          <Text tone="secondary">
            {ok.length === 1
              ? "1 file ingested."
              : `${ok.length} files ingested.`}
          </Text>
        )}

        {dups.length > 0 && (
          <details className={styles.outcomeGroup}>
            <summary className={styles.outcomeDupesSummary}>
              {dups.length === 1
                ? "1 duplicate skipped"
                : `${dups.length} duplicates skipped`}
            </summary>
            <ul className={styles.outcomeList}>
              {dups.map((dup) =>
                dup.kind === "duplicate" ? (
                  <li key={dup.filename} className={styles.outcomeItem}>
                    <span className={styles.outcomeFile}>{dup.filename}</span>
                    <span className={styles.outcomeArrow} aria-hidden>
                      →
                    </span>
                    <span className={styles.outcomeExisting}>
                      already here as “{dup.existingFilename}”
                      {dup.existingSubject ? ` · ${dup.existingSubject}` : ""}
                    </span>
                  </li>
                ) : null
              )}
            </ul>
          </details>
        )}
      </Stack>
    </div>
  );
}

export function ImportDropzone({ onUploaded }: ImportDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const { uploadFiles, loading, outcomes, clearOutcomes, retryFailed } = useUploadDocument();

  const handleUpload = async (files: FileList | File[]) => {
    const results = await uploadFiles(files);
    // Refetch if at least one file ingested — otherwise the library hasn't
    // changed and we save a round trip.
    if (results.some((r) => r.kind === "ok")) {
      onUploaded();
    }
  };

  const handleRetryFailed = async () => {
    const results = await retryFailed();
    if (results && results.some((r) => r.kind === "ok")) {
      onUploaded();
    }
  };

  return (
    <div
      className={[styles.dropzone, dragging ? styles.dragging : ""].filter(Boolean).join(" ")}
      onDragLeave={() => setDragging(false)}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDrop={async (event) => {
        event.preventDefault();
        setDragging(false);
        const files = event.dataTransfer?.files;
        if (files && files.length > 0) {
          await handleUpload(files);
        }
      }}
    >
      <Stack gap={2}>
        <Text variant="h3" weight="semibold">
          Import sources
        </Text>
        <Text tone="secondary">
          Drop files here to ingest them, or choose files manually from your machine.
          Duplicate files are skipped automatically.
        </Text>
      </Stack>

      <div className={styles.actions}>
        <Button
          disabled={loading.value}
          onClick={() => document.getElementById("library-import-input")?.click()}
          variant="secondary"
        >
          Or choose files
        </Button>
        {loading.value ? <Spinner size={16} /> : null}
      </div>

      <input
        id="library-import-input"
        multiple
        onChange={async (event) => {
          const input = event.currentTarget as HTMLInputElement | null;
          const files = input?.files;
          if (!files) {
            return;
          }
          await handleUpload(files);
          if (input) {
            input.value = "";
          }
        }}
        style={{ display: "none" }}
        type="file"
      />

      <OutcomeSummary
        onDismiss={clearOutcomes}
        onRetryFailed={() => void handleRetryFailed()}
        outcomes={outcomes.value}
        retrying={loading.value}
      />
    </div>
  );
}
