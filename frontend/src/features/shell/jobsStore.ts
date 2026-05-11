import { signal } from "@preact/signals";

import { withLocalApiToken } from "@/services/api/client";
import { jobs, type IngestionJob, type JobEvent } from "@/services/api/endpoints";

export const jobsState = {
  items: signal<IngestionJob[]>([]),
  events: signal<JobEvent[]>([]),
  loading: signal(false),
  error: signal<string | null>(null),
  lastEventId: signal(0)
};

let started = false;
let pollTimer: number | null = null;
let eventSource: EventSource | null = null;

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

export function startJobsFeed(): void {
  if (started) return;
  started = true;
  void refreshJobs();

  // PR-S1: the local-API gate now covers /api/jobs/stream. EventSource
  // cannot set custom headers, so we resolve the token and append it as
  // `?token=` via withLocalApiToken before constructing the source. The
  // async wait is brief (token is read from window.__CARREL_LOCAL_API_TOKEN
  // synchronously after the first call) but we still need to await it.
  void withLocalApiToken(jobs.streamUrl(jobsState.lastEventId.value)).then((authedUrl) => {
    try {
      eventSource = new EventSource(authedUrl);
      eventSource.addEventListener("job", (event) => {
        try {
          const parsed = JSON.parse((event as MessageEvent).data) as JobEvent;
          jobsState.events.value = [...jobsState.events.value, parsed].slice(-200);
          jobsState.lastEventId.value = Math.max(jobsState.lastEventId.value, parsed.id);
          void refreshJobs();
        } catch {
          void refreshEvents();
        }
      });
      eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;
        if (pollTimer === null) {
          pollTimer = window.setInterval(() => void refreshEvents(), 2500);
        }
      };
    } catch {
      pollTimer = window.setInterval(() => void refreshEvents(), 2500);
    }
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
