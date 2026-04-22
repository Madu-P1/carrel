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
 * Two behaviours we care about:
 *   1. Duplicates are surfaced explicitly with the existing filename + subject,
 *      so the user sees "already in library as X" instead of a generic error.
 *   2. A mixed batch (some ok, some dup, some failed) shows all three buckets
 *      without hiding the good news behind the bad. Users need to see what
 *      actually ingested.
 */
function OutcomeSummary({
  outcomes,
  onDismiss
}: {
  outcomes: UploadOutcome[];
  onDismiss: () => void;
}) {
  if (outcomes.length === 0) return null;
  const ok = outcomes.filter((o) => o.kind === "ok");
  const dups = outcomes.filter((o) => o.kind === "duplicate");
  const errs = outcomes.filter((o) => o.kind === "error");
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
        {ok.length > 0 && (
          <Text tone="secondary">
            {ok.length === 1
              ? "1 file ingested."
              : `${ok.length} files ingested.`}
          </Text>
        )}
        {dups.length > 0 && (
          <div className={styles.outcomeGroup}>
            <Text tone="secondary">
              {dups.length === 1
                ? "1 file was already in your library, skipped:"
                : `${dups.length} files were already in your library, skipped:`}
            </Text>
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
          </div>
        )}
        {errs.length > 0 && (
          <div className={styles.outcomeGroup}>
            <Text tone="danger">
              {errs.length === 1 ? "1 file failed:" : `${errs.length} files failed:`}
            </Text>
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
      </Stack>
    </div>
  );
}

export function ImportDropzone({ onUploaded }: ImportDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const { uploadFiles, loading, outcomes, clearOutcomes } = useUploadDocument();

  const handleUpload = async (files: FileList | File[]) => {
    const results = await uploadFiles(files);
    // Refetch if at least one file ingested — otherwise the library hasn't
    // changed and we save a round trip.
    if (results.some((r) => r.kind === "ok")) {
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

      <OutcomeSummary outcomes={outcomes.value} onDismiss={clearOutcomes} />
    </div>
  );
}
