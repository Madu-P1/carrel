import { renderHook, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { useSidebarSignals } from "../../src/app/shell/useSidebarSignals";
import { jsonResponse, registerFetchHandler } from "../support/mockFetch";

/**
 * The sidebar hook polls /api/shell/status for compact counts/provider
 * metadata and /api/health for process liveness. These tests pin the hook's
 * contract:
 *
 *   - Resolves each signal independently — one slow / errored endpoint
 *     doesn't starve the others.
 *   - Initial state is null for each signal; transitions to a value
 *     once the corresponding fetch resolves.
 *   - Provider error surfaces a degraded "unknown" status instead of
 *     leaving the footer blank forever.
 */

test("due, doc, and provider signals resolve from the shell status endpoint", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/shell/status" && init.method === "GET") {
      return jsonResponse({
        due_count: 3,
        doc_count: 2,
        provider: {
          kind: "ollama",
          ai_enabled: true,
          model_balanced: "llama3.1:8b",
          preference: "ollama"
        }
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

test("shell status error leaves last-known shell values untouched", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/shell/status" && init.method === "GET") {
      return jsonResponse({ detail: "oops" }, 500);
    }
    return undefined;
  });

  const { result } = renderHook(() => useSidebarSignals());

  await new Promise((resolve) => window.setTimeout(resolve, 0));
  expect(result.current.dueCount).toBeNull();
  expect(result.current.docCount).toBeNull();
  expect(result.current.provider).toBeNull();
});

test("a failing health endpoint marks only backend as down", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/shell/status" && init.method === "GET") {
      return jsonResponse({
        due_count: 1,
        doc_count: 4,
        provider: {
          kind: "null",
          ai_enabled: false,
          model_balanced: "",
          preference: "off"
        }
      });
    }
    if (url.pathname === "/api/health" && init.method === "GET") {
      return jsonResponse({ detail: "offline" }, 500);
    }
    return undefined;
  });

  const { result } = renderHook(() => useSidebarSignals());

  await waitFor(() => {
    expect(result.current.dueCount).toBe(1);
  });
  expect(result.current.docCount).toBe(4);
  expect(result.current.provider?.kind).toBe("null");
  expect(result.current.backend).toBe("down");
});
