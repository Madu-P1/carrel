import { signal } from "@preact/signals";

import { documentsQuery } from "@/features/library/hooks/useDocumentsQuery";
import { jobs, type IngestionJob, type JobEvent } from "@/services/api/endpoints";
import { subscribeSse } from "@/services/sse";

export const jobsState = {
  items: signal<IngestionJob[]>([]),
  events: signal<JobEvent[]>([]),
  loading: signal(false),
  error: signal<string | null>(null),
  lastEventId: signal(0)
};

let started = false;

function upsertJob(job: IngestionJob): void {
  const existing = jobsState.items.value;
  const index = existing.findIndex((item) => item.id === job.id);
  if (index === -1) {
    jobsState.items.value = [job, ...existing];
    return;
  }
  const next = existing.slice();
  next[index] = job;
  jobsState.items.value = next;
}

export async function refreshJobs(): Promise<void> {
  jobsState.loading.value = true;
  jobsState.error.value = null;
  try {
    const response = await jobs.list();
    jobsState.items.value = response.jobs;
  } catch (error) {
    jobsState.error.value = error instanceof Error ? error.message : String(error);
  } finally {
    jobsState.loading.value = false;
  }
}

export function startJobsFeed(): void {
  if (started) return;
  started = true;
  void refreshJobs();
  // Shared SSE multiplexer handles reconnect with backoff; on each
  // job event we refresh both jobs (for the tray) and documents
  // (for the Library, which mirrors job state for external uploads
  // like the floating cube).
  subscribeSse(jobs.streamUrl(jobsState.lastEventId.value), "job", (event) => {
    try {
      const parsed = JSON.parse(event.data) as JobEvent;
      jobsState.events.value = [...jobsState.events.value, parsed].slice(-200);
      jobsState.lastEventId.value = Math.max(jobsState.lastEventId.value, parsed.id);
    } catch {
      /* malformed payload — fall through to refreshes anyway */
    }
    void refreshJobs();
    void documentsQuery.refetch();
  });
}

export async function retryJob(jobId: string): Promise<void> {
  const response = await jobs.retry(jobId);
  upsertJob(response.job);
}

export async function deleteJob(jobId: string): Promise<void> {
  await jobs.delete(jobId);
  jobsState.items.value = jobsState.items.value.filter((job) => job.id !== jobId);
}

export function activeJobCount(): number {
  return jobsState.items.value.filter((job) => job.status === "queued" || job.status === "running").length;
}
