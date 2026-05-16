import { render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { BackendBootCheck } from "../../src/app/shell/BackendBootCheck";
import {
  jsonResponse,
  mockJson,
  registerFetchHandler
} from "../support/mockFetch";

/**
 * Regression: BackendBootCheck's cold-start race.
 *
 * Before the fix, the component only probed /api/health ONCE on mount
 * with a 5-second timeout. The Swift BackendSupervisor spawns Python
 * on app launch, and cold start (imports + SQLite migrations + provider
 * warmup) routinely takes 5–30s. The first probe lost the race against
 * the 5s timeout, state stuck at "error", and the overlay only cleared
 * when the user manually clicked "Retry."
 *
 * The fix: silent background polling every 2s while state is "error".
 * Once a probe succeeds, state flips to "ok" and the overlay clears
 * automatically.
 */

test("Overlay appears when the initial /api/health probe fails", async () => {
  // Default mockFetch returns 404 for any unmatched path. Probe will
  // see a non-ok response (treated as failure by `response.ok` check
  // when the path isn't matched? No — let's explicitly fail it).
  registerFetchHandler((url) => {
    if (url.pathname === "/api/health") {
      // Throw to simulate a network error (Swift supervisor still
      // spawning Python — the socket isn't accepting yet).
      throw new Error("ECONNREFUSED");
    }
    return undefined;
  });

  render(<BackendBootCheck />);

  const title = await screen.findByText(/couldn't connect to local backend/i);
  expect(title).toBeDefined();
});

test("Overlay clears automatically once the auto-poll probe succeeds", async () => {
  // First probe fails (Python not ready yet). Subsequent probes succeed.
  let attempts = 0;
  registerFetchHandler((url) => {
    if (url.pathname !== "/api/health") return undefined;
    attempts += 1;
    if (attempts === 1) {
      throw new Error("ECONNREFUSED");
    }
    return jsonResponse({ status: "ok", mode: "local", documents: 0 });
  });

  render(<BackendBootCheck />);

  // First probe fails → overlay shows.
  await screen.findByText(/couldn't connect to local backend/i);

  // Auto-poll fires every 2s; on the next probe (success), overlay clears.
  // Use a generous timeout so the real 2s interval has time to land.
  await waitFor(
    () => {
      expect(
        screen.queryByText(/couldn't connect to local backend/i)
      ).toBeNull();
    },
    { timeout: 4_000 }
  );

  expect(attempts).toBeGreaterThanOrEqual(2);
});

test("Overlay never appears when the first probe succeeds", async () => {
  mockJson("GET", "/api/health", {
    status: "ok",
    mode: "local",
    documents: 0
  });

  render(<BackendBootCheck />);

  // Wait a beat for the probe + state transition to settle. Should
  // never show the overlay.
  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(
    screen.queryByText(/couldn't connect to local backend/i)
  ).toBeNull();
});
