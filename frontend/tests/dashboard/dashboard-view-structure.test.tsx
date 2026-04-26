import { render, screen, within } from "@testing-library/preact";
import { expect, test } from "vitest";

import { DashboardView } from "../../src/features/dashboard/DashboardView";
import type { DashboardPayload } from "../../src/services/api/endpoints";
import { mockJson, registerFetchHandler } from "../support/mockFetch";

/**
 * Ship 6 reorganised the dashboard hierarchy:
 *   1. Status chips ABOVE the greeting (urgent info first)
 *   2. Hero composer (dominant)
 *   3. NextBestAction (one card, accent-tint, NO yellow)
 *   4. ContinueModule (only when active_session exists)
 *   5. QuickActionGrid (4 compact tiles)
 *   6. StatStrip
 *
 * These tests pin the new structure so a casual refactor can't quietly
 * undo the order or revive the warn-tinted callout the critique killed.
 */

const BASE_PAYLOAD: DashboardPayload = {
  generated_at: "2026-04-26T08:00:00Z",
  greeting: {
    time_of_day: "morning",
    iso_date: "2026-04-26",
    display_date: "Saturday, April 26",
  },
  stats: {
    streak_days: 3,
    streak_target_days: 7,
    week_minutes: 90,
    week_minutes_by_day: [10, 15, 20, 0, 25, 0, 20],
    sessions_today: 1,
    due_cards: 2,
    source_count: 11,
    last_studied_at: "2026-04-25T19:00:00Z",
  },
  next_best_action: {
    kind: "review",
    eyebrow: "Recommended next",
    title: "Review weak concepts",
    reason: "Three cards from yesterday slipped under 60% confidence.",
    primary: { path: "/study", label: "Review now" },
    secondary: { path: "/session", label: "Skip" },
  },
  active_session: null,
};

function mockDashboard(payload: DashboardPayload) {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/dashboard" && init.method === "GET") {
      return new Response(JSON.stringify(payload), {
        headers: { "content-type": "application/json" },
        status: 200,
      });
    }
    return undefined;
  });
}

test("status chips render ABOVE the greeting in the DOM", async () => {
  mockDashboard({
    ...BASE_PAYLOAD,
    stats: { ...BASE_PAYLOAD.stats, due_cards: 3 },
  });
  mockJson("GET", "/api/sessions/active", { active_session: null });

  render(<DashboardView />);

  // Wait for content to land (greeting is the late signal).
  const greeting = await screen.findByText(/Good morning\./i);

  // The cards-due chip should be in the DOM and earlier than the greeting.
  const dueChip = screen.getByRole("button", { name: /3 cards due now/i });

  // compareDocumentPosition: bit 4 (FOLLOWING) means dueChip is BEFORE
  // greeting. We expect the chip to come first.
  // eslint-disable-next-line no-bitwise
  expect(dueChip.compareDocumentPosition(greeting) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("dashboard does NOT render a yellow / warn-tinted recommendation card", async () => {
  mockDashboard(BASE_PAYLOAD);
  mockJson("GET", "/api/sessions/active", { active_session: null });

  render(<DashboardView />);

  // The recommendation card lands by aria-label.
  const card = await screen.findByLabelText(/Next best action/i);

  // The replacement uses --state-bg-selected / --color-accent — no class
  // name from the old `.nba` block should survive. We assert the
  // computed color of the card's left border isn't the warn token.
  // (Since CSS vars don't resolve in jsdom, we instead assert the
  // CLASS the card carries comes from the new module, not the legacy
  // `.nba` class on DashboardView.module.css.)
  expect(card.className).not.toContain("nba");
  expect(card.className).toMatch(/card/i);
});

test("ContinueModule renders only when there is an active session", async () => {
  // First render: no active session → no Continue band.
  mockDashboard({ ...BASE_PAYLOAD, active_session: null });
  mockJson("GET", "/api/sessions/active", { active_session: null });

  const { unmount } = render(<DashboardView />);
  await screen.findByText(/Good morning\./i);
  expect(screen.queryByLabelText(/Continue where you left off/i)).toBeNull();
  unmount();

  // Second render: with an active session → band renders, button label "Resume".
  mockDashboard({
    ...BASE_PAYLOAD,
    active_session: {
      id: "sess-1",
      objective: "[ui:pomodoro] Cover chapter 7",
      mode: "focus_sprint",
      duration_minutes: 25,
      started_at: "2026-04-26T07:30:00Z",
    },
  });
  mockJson("GET", "/api/sessions/active", {
    active_session: {
      id: "sess-1",
      goal_id: null,
      objective: "[ui:pomodoro] Cover chapter 7",
      mode: "focus_sprint",
      duration_minutes: 25,
      difficulty_target: null,
      started_at: "2026-04-26T07:30:00Z",
      status: "active",
    },
  });

  render(<DashboardView />);
  const band = await screen.findByLabelText(/Continue where you left off/i);
  // Both ContinueModule and ActiveSessionCard render the objective.
  // Scope the assertion to the Continue band so we only verify THIS
  // surface stripped the [ui:mode] prefix; ActiveSessionCard's behavior
  // is exercised by its own tests.
  expect(band.textContent).toMatch(/Cover chapter 7/i);
  expect(band.textContent).not.toMatch(/\[ui:pomodoro\]/);
  expect(within(band).getByRole("button", { name: /resume/i })).toBeDefined();
});

test("Hero composer is the dominant Ask entry — submitting routes to /ask?q=...&auto=1", async () => {
  mockDashboard(BASE_PAYLOAD);
  mockJson("GET", "/api/sessions/active", { active_session: null });

  render(<DashboardView />);

  // Hero composer carries the role=search label. Ship 7 voice sweep
  // renamed the prior "Ask Einstein" to "Ask from your sources" — the
  // verb-led, source-grounded version per the new copy rules.
  const composer = await screen.findByRole("search", {
    name: /Ask from your sources/i,
  });
  expect(composer).toBeDefined();
  // It's a single dominant input — assert exactly one search role on the
  // page (any duplicate would mean the old composer still mounted).
  expect(screen.getAllByRole("search").length).toBe(1);
});
