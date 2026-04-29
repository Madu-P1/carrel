import { fireEvent, render, screen, within } from "@testing-library/preact";
import { expect, test } from "vitest";

import { PlanView } from "../../src/features/plan/PlanView";
import { jsonResponse, registerFetchHandler } from "../support/mockFetch";

/**
 * Pin the Plan surface's three core flows:
 *   1. Empty state when no feeds connected — voice-rule headline + CTA
 *   2. Coach suggestion renders with reason text inline
 *   3. is_freshening flag surfaces the "Refreshing in background…" hint
 */

const NOON_TODAY = (() => {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  return d.toISOString();
})();

const ONE_PM_TODAY = (() => {
  const d = new Date();
  d.setHours(13, 0, 0, 0);
  return d.toISOString();
})();

test("Plan empty state renders the connect-a-calendar CTA", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/plan" && init.method === "GET") {
      return jsonResponse({
        events: [],
        suggestions: [],
        feeds: [],
        is_freshening: false,
      });
    }
    return undefined;
  });

  render(<PlanView />);

  expect(await screen.findByText(/See your week and where to study/i)).toBeDefined();
  // Empty-state primary CTA. Voice rule: verb-led label.
  expect(screen.getByRole("button", { name: /Connect a calendar/i })).toBeDefined();
});

test("Coach suggestion renders inline with its reason text", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/plan" && init.method === "GET") {
      return jsonResponse({
        events: [],
        suggestions: [
          {
            id: "sugg-1",
            kind: "review_block",
            status: "pending",
            start_at: NOON_TODAY,
            end_at: ONE_PM_TODAY,
            due_at: null,
            reason_code: "free_block_overdue_srs",
            reason_text: "60-min gap and 4 cards overdue.",
            score: 1.0,
          },
        ],
        feeds: [
          {
            id: "feed-1",
            label: "Personal",
            url: "https://example.com/***",
            color: null,
            is_enabled: true,
            last_synced_at: new Date().toISOString(),
            last_successful_sync_at: new Date().toISOString(),
            consecutive_failures: 0,
            last_error: null,
          },
        ],
        is_freshening: false,
      });
    }
    return undefined;
  });

  render(<PlanView />);

  // Suggestion text appears in the grid.
  expect(
    await screen.findByText(/60-min gap and 4 cards overdue/i)
  ).toBeDefined();
  // Schedule + Dismiss buttons rendered.
  expect(screen.getByRole("button", { name: /Schedule it/i })).toBeDefined();
  expect(screen.getByRole("button", { name: /^Dismiss$/i })).toBeDefined();
});

test("is_freshening surfaces the background-refresh hint", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/plan" && init.method === "GET") {
      return jsonResponse({
        events: [],
        suggestions: [],
        feeds: [
          {
            id: "feed-1",
            label: "Stale Feed",
            url: "https://example.com/***",
            color: null,
            is_enabled: true,
            last_synced_at: null,
            last_successful_sync_at: null,
            consecutive_failures: 0,
            last_error: null,
          },
        ],
        is_freshening: true,
      });
    }
    return undefined;
  });

  render(<PlanView />);

  expect(
    await screen.findByText(/Refreshing in background/i)
  ).toBeDefined();
});

test("Add-feed dialog opens and validates required fields", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/plan" && init.method === "GET") {
      return jsonResponse({
        events: [],
        suggestions: [],
        feeds: [],
        is_freshening: false,
      });
    }
    return undefined;
  });

  render(<PlanView />);

  // Wait for empty state, then click the Connect-a-calendar CTA.
  fireEvent.click(
    await screen.findByRole("button", { name: /Connect a calendar/i })
  );

  // Dialog opens with the form. Multiple "Add feed" buttons exist on
  // the page (FeedList trigger + dialog submit), so scope the submit
  // query to within the dialog.
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByLabelText(/^Name$/i)).toBeDefined();
  expect(within(dialog).getByLabelText(/iCal URL/i)).toBeDefined();
  const addButton = within(dialog).getByRole("button", { name: /Add feed/i });
  expect((addButton as HTMLButtonElement).disabled).toBe(true);
});
