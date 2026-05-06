import { render, screen } from "@testing-library/preact";
import { test, expect } from "vitest";

import { App } from "../src/app/App";

test("App renders the shell and the Dashboard home by default", async () => {
  render(<App />);

  expect(screen.getByText(/Carrel/i)).toBeDefined();
  // Default landing is the Dashboard; the time-of-day greeting rendered by
  // DashboardView is the canonical "we booted cleanly" marker.
  expect(await screen.findByText(/Good (morning|afternoon|evening|night)\./i)).toBeDefined();
});

test("App renders the Library home when navigated to /library", async () => {
  window.history.pushState({}, "", "/library");
  render(<App />);

  expect(screen.getByText(/Carrel/i)).toBeDefined();
  // LibraryView is code-split (signal-backed lazy route), so its content
  // arrives after the import promise resolves rather than on first paint.
  // findBy* awaits the next render the lazy signal triggers.
  expect(await screen.findByText(/Your sources\./i)).toBeDefined();
  expect(await screen.findByText(/No sources yet\./i)).toBeDefined();
});
