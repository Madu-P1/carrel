import { useState } from "preact/hooks";

import { Button, Input, Spinner, Stack, Text, toast } from "@/design-system";

import { useUploadDocument, type UploadOutcome } from "../hooks/useUploadDocument";

import styles from "./ImportDropzone.module.css";

interface ImportDropzoneProps {
  onUploaded: () => void;
  onSubjectCreated?: (subjectName: string) => Promise<void> | void;
  subjectOptions?: string[];
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
              ? "1 file queued for ingestion."
              : `${ok.length} files queued for ingestion.`}
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

export function ImportDropzone({
  onSubjectCreated,
  onUploaded,
  subjectOptions = []
}: ImportDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const [subjectName, setSubjectName] = useState("General");
  const [creatingSubject, setCreatingSubject] = useState(false);
  const { uploadFiles, loading, outcomes, clearOutcomes, retryFailed } = useUploadDocument();
  const normalizedSubject = subjectName.trim() || "General";

  const handleUpload = async (files: FileList | File[]) => {
    const results = await uploadFiles(files, normalizedSubject);
    const okCount = results.filter((r) => r.kind === "ok").length;
    const errCount = results.filter((r) => r.kind === "error").length;
    const dupCount = results.filter((r) => r.kind === "duplicate").length;
    if (okCount > 0) {
      onUploaded();
      const suffix =
        dupCount || errCount
          ? `${dupCount ? ` · ${dupCount} dup${dupCount === 1 ? "" : "s"}` : ""}${errCount ? ` · ${errCount} failed` : ""}`
          : "";
      toast.success(
        `${okCount} file${okCount === 1 ? "" : "s"} ingested${suffix}`,
        "Watch progress in Jobs. Ready sources appear in the Library."
      );
    } else if (errCount > 0) {
      toast.error(
        `${errCount} upload${errCount === 1 ? "" : "s"} failed`,
        "Use Retry failed in the outcome panel below to try again without re-selecting."
      );
    } else if (dupCount > 0) {
      toast.info(`${dupCount} file${dupCount === 1 ? "" : "s"} already in your library`);
    }
  };

  const handleRetryFailed = async () => {
    const results = await retryFailed(normalizedSubject);
    if (results && results.some((r) => r.kind === "ok")) {
      onUploaded();
    }
  };

  const handleCreateSubject = async () => {
    if (!onSubjectCreated) return;
    const target = normalizedSubject;
    setCreatingSubject(true);
    try {
      await onSubjectCreated(target);
      toast.success("Subject folder created", target);
    } catch (caught) {
      toast.error("Could not create subject", caught instanceof Error ? caught.message : String(caught));
    } finally {
      setCreatingSubject(false);
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
        <div className={styles.subjectControl}>
          <Input
            label="Subject folder"
            list="library-subject-options"
            onInput={(event) => setSubjectName((event.currentTarget as HTMLInputElement).value)}
            value={subjectName}
          />
          <datalist id="library-subject-options">
            {subjectOptions.map((subject) => (
              <option key={subject} value={subject} />
            ))}
          </datalist>
        </div>
        {onSubjectCreated ? (
          <Button
            disabled={creatingSubject || loading.value}
            isLoading={creatingSubject}
            onClick={() => void handleCreateSubject()}
            variant="secondary"
          >
            Create folder
          </Button>
        ) : null}
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
        accept=".pdf,.txt,.md,.markdown,.docx,.pptx,.csv,.tsv,.xlsx,.xls"
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
