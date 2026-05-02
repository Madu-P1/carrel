import { vi } from "vitest";

type FetchHandler = (
  url: URL,
  init: RequestInit & { method: string }
) => Response | Promise<Response | undefined> | undefined;

const handlers: FetchHandler[] = [];
const calls: Array<{ url: string; method: string; body?: BodyInit | null }> = [];

function installDefaultHandlers() {
  handlers.push((url, init) => {
    const method = init.method.toUpperCase();
    if (url.pathname === "/api/documents" && method === "GET") {
      return jsonResponse([]);
    }
    // Default to an empty SRS queue so any route that mounts StudyView has a
    // stable "caught up" state without each test having to mock the endpoint.
    if (url.pathname === "/api/srs/due" && method === "GET") {
      return jsonResponse({ cards: [] });
    }
    // Library home + dashboard both poll their own summary endpoints. Giving
    // each a zero-state default means tests don't have to mock them unless
    // they specifically exercise those surfaces.
    if (url.pathname === "/api/library/subjects" && method === "GET") {
      return jsonResponse({ subjects: [] });
    }
    if (url.pathname === "/api/library/duplicates" && method === "GET") {
      return jsonResponse({
        groups: [],
        total_groups: 0,
        total_duplicates: 0,
        total_cards_in_duplicates: 0
      });
    }
    if (url.pathname === "/api/system/provider" && method === "GET") {
      return jsonResponse({
        kind: "null",
        ai_enabled: false,
        model_balanced: "",
        preference: "off"
      });
    }
    if (url.pathname === "/api/usage-events" && method === "POST") {
      return jsonResponse({
        id: 1,
        event_name: "app.first_launch",
        surface: null,
        properties: {},
        created_at: "2026-05-02T00:00:00Z"
      });
    }
    if (url.pathname === "/api/dashboard" && method === "GET") {
      return jsonResponse({
        generated_at: "2026-04-22T12:00:00+00:00",
        greeting: {
          time_of_day: "afternoon",
          iso_date: "2026-04-22",
          display_date: "Wednesday, April 22"
        },
        stats: {
          streak_days: 0,
          streak_target_days: 30,
          week_minutes: 0,
          week_minutes_by_day: [0, 0, 0, 0, 0, 0, 0],
          sessions_today: 0,
          due_cards: 0,
          source_count: 0,
          last_studied_at: null
        },
        next_best_action: {
          kind: "import",
          eyebrow: "Start here",
          title: "Add your first source",
          reason: "Import something to get started.",
          primary: { label: "Open Library", path: "/library" },
          secondary: null
        },
        active_session: null
      });
    }
    if (url.pathname === "/api/sessions/active" && method === "GET") {
      return jsonResponse({ active_session: null });
    }
    return undefined;
  });
}

function normalizeInput(input: RequestInfo | URL, init?: RequestInit): { url: URL; requestInit: RequestInit & { method: string } } {
  if (input instanceof Request) {
    return {
      url: new URL(input.url),
      requestInit: {
        ...init,
        method: init?.method ?? input.method ?? "GET",
        body: init?.body ?? null
      }
    };
  }

  const raw = input instanceof URL ? input.toString() : input;
  return {
    url: new URL(raw, "http://127.0.0.1:8000"),
    requestInit: {
      ...(init ?? {}),
      method: init?.method ?? "GET",
      body: init?.body ?? null
    }
  };
}

async function fetchMock(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const { url, requestInit } = normalizeInput(input, init);
  calls.push({ url: url.toString(), method: requestInit.method, body: requestInit.body });

  for (const handler of [...handlers].reverse()) {
    const result = await handler(url, requestInit);
    if (result) {
      return result;
    }
  }

  throw new Error(`Unhandled fetch: ${requestInit.method} ${url.toString()}`);
}

export function installFetchMock() {
  vi.stubGlobal("fetch", vi.fn(fetchMock));
  installDefaultHandlers();
}

export function resetFetchMock() {
  handlers.length = 0;
  calls.length = 0;
  const stub = globalThis.fetch;
  if ("mockClear" in (stub as object)) {
    (stub as ReturnType<typeof vi.fn>).mockClear();
  }
  installDefaultHandlers();
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" }
  });
}

export function registerFetchHandler(handler: FetchHandler): () => void {
  handlers.push(handler);
  return () => {
    const index = handlers.indexOf(handler);
    if (index >= 0) {
      handlers.splice(index, 1);
    }
  };
}

export function mockJson(
  method: string,
  path: string,
  body:
    | unknown
    | ((url: URL, init: RequestInit & { method: string }) => unknown | Promise<unknown>),
  status = 200
) {
  return registerFetchHandler(async (url, init) => {
    if (url.pathname !== path || init.method.toUpperCase() !== method.toUpperCase()) {
      return undefined;
    }

    const payload = typeof body === "function" ? await body(url, init) : body;
    return jsonResponse(payload, status);
  });
}

export function getFetchCalls() {
  return [...calls];
}
