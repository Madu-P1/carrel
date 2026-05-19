import { signal } from "@preact/signals";

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
let pollTimer: number | null = null;

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

async function refreshEvents(): Promise<void> {
  try {
    const response = await jobs.events(jobsState.lastEventId.value);
    if (response.events.length > 0) {
      jobsState.events.value = [...jobsState.events.value, ...response.events].slice(-200);
      jobsState.lastEventId.value = response.last_event_id;
      await refreshJobs();
    }
  } catch {
    // Polling is a fallback signal. The visible error belongs to refreshJobs().
  }
}

function ensurePollFallback(): void {
  if (pollTimer === null) {
    pollTimer = window.setInterval(() => void refreshEvents(), 2500);
  }
}

export function startJobsFeed(): void {
  if (started) return;
  started = true;
  void refreshJobs();

  const streamUrl = jobs.streamUrl(jobsState.lastEventId.value);
  subscribeSse(streamUrl, "job", (event) => {
    try {
      const parsed = JSON.parse(event.data) as JobEvent;
      jobsState.events.value = [...jobsState.events.value, parsed].slice(-200);
      jobsState.lastEventId.value = Math.max(jobsState.lastEventId.value, parsed.id);
      void refreshJobs();
    } catch {
      void refreshEvents();
    }
  });
  subscribeSse(streamUrl, "error", () => {
    ensurePollFallback();
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
