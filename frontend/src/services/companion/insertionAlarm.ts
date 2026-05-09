/**
 * sessionAlarm — fires `companion.alarmStart()` when the next study
 * trigger time arrives. The cube spins chaotically until the user
 * taps the floating panel; tap dispatches `carrel:companion-alarm-ack`
 * and we re-arm for whatever's next.
 *
 * Triggers (whichever is soonest in the future):
 *   1. A study-block event on the user's calendar — any event whose
 *      summary matches the STUDY_ALLOCATION regex (`Study X`,
 *      `Revise Y`, etc.). This is the everyday alarm: the user puts
 *      "Study calc 14:00–15:00" on their calendar and at 14:00 the
 *      cube goes wild.
 *   2. The soonest planner-suggested insertion from
 *      `/api/plan/insertions`. Covers the case where the planner
 *      proposed a session and the user hasn't moved it onto their
 *      calendar yet.
 *
 * Refresh triggers (move the next-trigger time):
 *   - Initial mount
 *   - SSE `calendar-changed` from `/api/plan/events/stream`
 *   - Window focus
 *   - 5-minute heartbeat (covers SSE drops)
 *   - After alarm dismissal
 */

import { planApi, type PlanEvent, type StudySessionInsertion } from "@/features/plan/api/planApi";
import { isUserStudyBlock } from "@/features/plan/utils/eventClassification";
import { API_BASE } from "@/services/api/client";
import { subscribeSse } from "@/services/sse";

import { companion } from "./bus";

let alarmTimer: number | null = null;
/** ISO timestamp of the trigger we're currently armed for. Used to
 *  no-op refresh calls that pick the same trigger again — re-arming
 *  the same trigger would push the timer further out and miss the
 *  moment. */
let scheduledForIso: string | null = null;
let installed = false;

/** A small bias so a 14:00 trigger doesn't fire at 13:59:59.998. */
const FIRE_GRACE_MS = 250;

/** Maximum gap between forced refreshes — protects against the SSE
 *  stream silently dropping. 5 minutes is short enough that the user
 *  won't miss a session by more than a couple of minutes. */
const HEARTBEAT_REFRESH_MS = 5 * 60 * 1000;

function clearAlarmTimer(): void {
  if (alarmTimer !== null) {
    window.clearTimeout(alarmTimer);
    alarmTimer = null;
  }
  scheduledForIso = null;
}

function nextFutureStart<T>(items: T[], pick: (item: T) => string | null): string | null {
  const nowMs = Date.now();
  let bestIso: string | null = null;
  let bestMs = Infinity;
  for (const item of items) {
    const iso = pick(item);
    if (!iso) continue;
    const t = Date.parse(iso);
    if (Number.isNaN(t) || t < nowMs - FIRE_GRACE_MS) continue;
    if (t < bestMs) { bestIso = iso; bestMs = t; }
  }
  return bestIso;
}

const pickStudyBlock = (e: PlanEvent): string | null =>
  !e.all_day && e.status !== "cancelled" && isUserStudyBlock(e.summary)
    ? e.start_at
    : null;
const pickInsertion = (i: StudySessionInsertion): string | null => i.start_at;

function timezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

async function refreshAndArm(): Promise<void> {
  // Pull both the calendar (events) and the planner (insertions) in
  // parallel so a slow planner doesn't delay arming on a study block
  // that's about to start.
  const [planResult, insertionsResult] = await Promise.allSettled([
    planApi.get(),
    planApi.insertions(timezone()),
  ]);

  const candidates: string[] = [];
  if (planResult.status === "fulfilled") {
    const iso = nextFutureStart(planResult.value.events, pickStudyBlock);
    if (iso) candidates.push(iso);
  }
  if (insertionsResult.status === "fulfilled") {
    const iso = nextFutureStart(insertionsResult.value.insertions, pickInsertion);
    if (iso) candidates.push(iso);
  }

  if (candidates.length === 0) {
    // Nothing upcoming. Don't clear an already-armed timer if both
    // calls failed — better to keep yesterday's signal than nothing.
    if (planResult.status === "fulfilled" && insertionsResult.status === "fulfilled") {
      clearAlarmTimer();
    }
    return;
  }

  const nextIso = candidates.reduce((best, iso) =>
    Date.parse(iso) < Date.parse(best) ? iso : best
  );

  if (scheduledForIso === nextIso) return;
  clearAlarmTimer();
  const delay = Math.max(0, Date.parse(nextIso) - Date.now() - FIRE_GRACE_MS);
  scheduledForIso = nextIso;
  alarmTimer = window.setTimeout(() => {
    alarmTimer = null;
    scheduledForIso = null;
    companion.alarmStart();
  }, delay);
}

function onAlarmAck(): void {
  // The Swift tap path already cleared the alarm visual; sync the
  // bus flag and re-arm for the *next* trigger so back-to-back
  // sessions both ring.
  companion.alarmStop();
  void refreshAndArm();
}

/** Idempotent. Call once at app boot. */
export function installInsertionAlarmWatcher(): void {
  if (installed) return;
  installed = true;
  void refreshAndArm();
  subscribeSse(`${API_BASE}/api/plan/events/stream`, "calendar-changed", () => { void refreshAndArm(); });
  window.addEventListener("focus", () => { void refreshAndArm(); });
  window.addEventListener("carrel:companion-alarm-ack", onAlarmAck as EventListener);
  window.setInterval(() => { void refreshAndArm(); }, HEARTBEAT_REFRESH_MS);
}
