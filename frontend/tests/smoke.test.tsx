import { render, screen } from "@testing-library/preact";
import { test, expect } from "vitest";

import { App } from "../src/app/App";

test("App renders the shell and the Dashboard home by default", async () => {
  render(<App />);

  expect(screen.getByText(/Einstein Workspace/i)).toBeDefined();
  // Default landing is the Dashboard; the time-of-day greeting rendered by
  // DashboardView is the canonical "we booted cleanly" marker.
  expect(await screen.findByText(/Good (morning|afternoon|evening|night)\./i)).toBeDefined();
});

test("App renders the Library home when navigated to /library", async () => {
  window.history.pushState({}, "", "/library");
  render(<App />);

  expect(screen.getByText(/Einstein Workspace/i)).toBeDefined();
  expect(screen.getByText(/Source-grounded documents, grouped the way you study\./i)).toBeDefined();
  expect(await screen.findByText(/No sources yet\./i)).toBeDefined();
});
