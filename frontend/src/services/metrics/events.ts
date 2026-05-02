import { api } from "@/services/api/client";


export type UsageEventName =
  | "app.first_launch"
  | "import.started"
  | "import.completed"
  | "import.failed"
  | "onboarding.demo_library_loaded"
  | "library.search_used"
  | "reader.find_used"
  | "reader.focus_toggled"
  | "ask.first_question"
  | "srs.review_started"
  | "srs.review_completed";

type UsageEventPrimitive = boolean | number | string | null;
type UsageEventProperties = Record<string, UsageEventPrimitive | undefined>;

interface UsageEventResponse {
  id: number;
  event_name: UsageEventName;
  surface: string | null;
  properties: Record<string, UsageEventPrimitive>;
  created_at: string;
}

const DENIED_KEY_FRAGMENTS = [
  "answer",
  "api_key",
  "content",
  "document_text",
  "email",
  "filename",
  "file_name",
  "name",
  "path",
  "question",
  "query",
  "quote",
  "secret",
  "selected",
  "snippet",
  "text",
  "token",
  "user"
] as const;

function isSafeKey(key: string): boolean {
  return /^[a-z][a-z0-9_]{0,63}$/.test(key)
    && !DENIED_KEY_FRAGMENTS.some((fragment) => key.includes(fragment));
}

function sanitizeProperties(properties: UsageEventProperties = {}): Record<string, UsageEventPrimitive> {
  const safe: Record<string, UsageEventPrimitive> = {};
  for (const [key, value] of Object.entries(properties)) {
    if (!isSafeKey(key) || value === undefined) continue;
    if (typeof value === "number" && !Number.isFinite(value)) continue;
    if (typeof value === "string" && value.length > 120) continue;
    safe[key] = value;
  }
  return safe;
}

export const events = {
  async track(
    eventName: UsageEventName,
    properties: UsageEventProperties = {},
    surface?: string
  ): Promise<void> {
    try {
      await api<UsageEventResponse>("/api/usage-events", {
        method: "POST",
        body: {
          event_name: eventName,
          properties: sanitizeProperties(properties),
          surface: surface?.toLowerCase()
        }
      });
    } catch {
      // Metrics are local-only and best-effort. Product flows must never
      // fail because event persistence is unavailable.
    }
  }
};
