import { renderHook, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { useSidebarSignals } from "../../src/app/shell/useSidebarSignals";
import { jsonResponse, registerFetchHandler } from "../support/mockFetch";

/**
 * The sidebar hook polls three endpoints: /api/srs/due, /api/documents,
 * and /api/system/provider. Each feeds an independent surface (Study
 * badge, Today count, footer chip). These tests pin the hook's contract:
 *
 *   - Resolves each signal independently — one slow / errored endpoint
 *     doesn't starve the others.
 *   - Initial state is null for each signal; transitions to a value
 *     once the corresponding fetch resolves.
 *   - Provider error surfaces a degraded "unknown" status instead of
 *     leaving the footer blank forever.
 */

test("due, doc, and provider signals resolve from their endpoints", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/srs/due" && init.method === "GET") {
      return jsonResponse({
        cards: [
          { id: "a", front: "", back: "", state: "new", stability: 1, difficulty: 0.3, reps: 0, lapses: 0, due_date: null, concept: "", document_name: "", subject_name: null },
          { id: "b", front: "", back: "", state: "new", stability: 1, difficulty: 0.3, reps: 0, lapses: 0, due_date: null, concept: "", document_name: "", subject_name: null },
          { id: "c", front: "", back: "", state: "new", stability: 1, difficulty: 0.3, reps: 0, lapses: 0, due_date: null, concept: "", document_name: "", subject_name: null }
        ]
      });
    }
    if (url.pathname === "/api/documents" && init.method === "GET") {
      return jsonResponse([
        { id: "d1", filename: "a.pdf" },
        { id: "d2", filename: "b.pdf" }
      ]);
    }
    if (url.pathname === "/api/system/provider" && init.method === "GET") {
      return jsonResponse({
        kind: "ollama",
        ai_enabled: true,
        model_balanced: "llama3.1:8b",
        preference: "ollama"
      });
    }
    return undefined;
  });

  const { result } = renderHook(() => useSidebarSignals());

  await waitFor(() => {
    expect(result.current.dueCount).toBe(3);
    expect(result.current.docCount).toBe(2);
    expect(result.current.provider?.kind).toBe("ollama");
  });
});

test("provider endpoint error surfaces a degraded 'unknown' status", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/srs/due" && init.method === "GET") {
      return jsonResponse({ cards: [] });
    }
    if (url.pathname === "/api/documents" && init.method === "GET") {
      return jsonResponse([]);
    }
    if (url.pathname === "/api/system/provider" && init.method === "GET") {
      return jsonResponse({ detail: "oops" }, 500);
    }
    return undefined;
  });

  const { result } = renderHook(() => useSidebarSignals());

  await waitFor(() => {
    expect(result.current.provider?.kind).toBe("unknown");
    expect(result.current.provider?.ai_enabled).toBe(false);
  });
});

test("a failing docs endpoint does not block the due signal from resolving", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/srs/due" && init.method === "GET") {
      return jsonResponse({
        cards: [{ id: "a", front: "", back: "", state: "new", stability: 1, difficulty: 0.3, reps: 0, lapses: 0, due_date: null, concept: "", document_name: "", subject_name: null }]
      });
    }
    if (url.pathname === "/api/documents" && init.method === "GET") {
      return jsonResponse({ detail: "oops" }, 500);
    }
    if (url.pathname === "/api/system/provider" && init.method === "GET") {
      return jsonResponse({
        kind: "null",
        ai_enabled: false,
        model_balanced: "",
        preference: "off"
      });
    }
    return undefined;
  });

  const { result } = renderHook(() => useSidebarSignals());

  await waitFor(() => {
    expect(result.current.dueCount).toBe(1);
  });
  // docCount stays null because its fetch errored — critical behavior:
  // one slow/failed endpoint must not starve the others.
  expect(result.current.docCount).toBeNull();
  expect(result.current.provider?.kind).toBe("null");
});
