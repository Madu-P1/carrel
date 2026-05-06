import { useEffect, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { Button, Dialog, Icon, Stack, Text, toast } from "@/design-system";
import type { IngestionJob } from "@/services/api/endpoints";

import {
  activeJobCount,
  deleteJob,
  jobsState,
  refreshJobs,
  retryJob,
  startJobsFeed
} from "./jobsStore";
import styles from "./JobsTray.module.css";

const stageOrder: IngestionJob["stage"][] = [
  "importing",
  "extracting_text",
  "indexing",
  "generating_cards",
  "ready"
];

function stageLabel(stage: string): string {
  return stage.replace(/_/g, " ");
}

function JobRow({ job }: { job: IngestionJob }) {
  const activeIndex = stageOrder.indexOf(job.stage);
  const failed = job.status === "failed";
  return (
    <div className={styles.row}>
      <div className={styles.rowTop}>
        <div>
          <p className={styles.filename}>{job.filename}</p>
          <p className={styles.meta}>
            {job.status} · {stageLabel(job.stage)}
            {job.subject_name ? ` · ${job.subject_name}` : ""}
          </p>
        </div>
        <Text tone="tertiary" variant="caption">
          {Math.round((job.progress ?? 0) * 100)}%
        </Text>
      </div>
      <div className={styles.pipeline} aria-label={`Pipeline stage: ${stageLabel(job.stage)}`}>
        {stageOrder.map((stage, index) => (
          <span
            aria-hidden
            className={[
              styles.stage,
              index <= activeIndex ? styles.stageActive : "",
              failed && index === activeIndex ? styles.stageFailed : ""
            ].filter(Boolean).join(" ")}
            key={stage}
          />
        ))}
      </div>
      {job.error ? <div className={styles.error}>{job.error}</div> : null}
      <div className={styles.actions}>
        {job.status === "failed" || job.status === "cancelled" ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              void retryJob(job.id).catch(() => {
                toast.error("Retry failed", "Carrel could not queue this import again.");
              });
            }}
          >
            Retry
          </Button>
        ) : null}
        {job.document_id ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              navigateTo(`/reader/${encodeURIComponent(job.document_id!)}`);
            }}
          >
            Open source
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            void deleteJob(job.id).catch(() => {
              toast.error("Delete failed", "Carrel could not remove this job.");
            });
          }}
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

export function JobsTray() {
  const [open, setOpen] = useState(false);
  const count = activeJobCount();
  const items = jobsState.items.value;

  useEffect(() => {
    startJobsFeed();
  }, []);

  return (
    <>
      <Button
        aria-label={count > 0 ? `${count} import jobs active` : "Open jobs tray"}
        className={styles.trayButton}
        leadingIcon={<Icon name="doc" />}
        onClick={() => {
          setOpen(true);
          void refreshJobs();
        }}
        variant={count > 0 ? "secondary" : "ghost"}
      >
        Jobs{count > 0 ? ` ${count}` : ""}
      </Button>
      <Dialog
        open={open}
        title="Jobs Tray"
        description="Imports, extraction, indexing, and failures stay visible here."
        onClose={() => setOpen(false)}
      >
        <div className={styles.modalBody}>
          {items.length === 0 ? (
            <Stack gap={2}>
              <Text tone="secondary">No import jobs yet.</Text>
              <Text tone="tertiary" variant="caption">
                Drop a source into Library and its progress will appear here.
              </Text>
            </Stack>
          ) : (
            items.map((job) => <JobRow job={job} key={job.id} />)
          )}
        </div>
      </Dialog>
    </>
  );
}
