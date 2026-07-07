/**
 * Wrapper around `window.nativeCalendar` exposed by the macOS shell's
 * EventKit write bridge (NativeBridge.swift).
 *
 * In production (the desktop app) the bridge is always present; in
 * dev / browser fallback (running `vite dev` outside the .app), the
 * helper rejects with a sentinel error so callers can degrade
 * gracefully — e.g. the Add to Calendar button hides itself rather
 * than firing a no-op promise.
 */

export interface InsertCalendarEventInput {
  summary: string;
  /** ISO 8601 UTC. */
  start_at: string;
  end_at: string;
  location?: string | null;
}

export interface InsertCalendarEventResult {
  uid: string;
}

interface NativeCalendarBridge {
  insertEvent(input: InsertCalendarEventInput): Promise<InsertCalendarEventResult>;
}

declare global {
  interface Window {
    nativeCalendar?: NativeCalendarBridge;
  }
}

export class CalendarBridgeUnavailableError extends Error {
  constructor() {
    super("Native calendar bridge unavailable (open Cachet in the desktop app to add events).");
    this.name = "CalendarBridgeUnavailableError";
  }
}

export function isNativeCalendarAvailable(): boolean {
  return typeof window !== "undefined"
    && typeof window.nativeCalendar?.insertEvent === "function";
}

export async function insertNativeCalendarEvent(
  input: InsertCalendarEventInput
): Promise<InsertCalendarEventResult> {
  if (!isNativeCalendarAvailable()) {
    throw new CalendarBridgeUnavailableError();
  }
  // The cast is safe — isNativeCalendarAvailable just checked.
  return window.nativeCalendar!.insertEvent(input);
}
