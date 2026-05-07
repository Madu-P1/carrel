import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { appShell } from "@/app/shell/useAppShell";
import { FirstRunTour, openFirstRunTour } from "@/features/onboarding/FirstRunTour";

import { mockJson } from "../support/mockFetch";

const STORAGE_KEY = "carrel.first-run-tour.completed";

test("first-run tour can be replayed after completion and advances through the product loop", async () => {
  window.localStorage.setItem(STORAGE_KEY, "1");
  // Must match the current TOUR_VERSION in FirstRunTour.tsx; bump
  // here whenever the production version bumps (the bump is by
  // design — re-prompts users on substantive content updates).
  window.localStorage.setItem("carrel.first-run-tour.version", "6");
  mockJson("POST", "/api/onboarding/demo-library", {
    seeded: true,
    documents: [],
    skipped_reason: null
  });

  render(<FirstRunTour />);

  expect(screen.queryByRole("dialog")).toBeNull();

  openFirstRunTour();

  expect(await screen.findByRole("dialog", { name: /Bring in a source you trust/i })).toBeDefined();
  expect(screen.getByText("IMPORT")).toBeDefined();
  expect(screen.getByLabelText("Step 1 of 5")).toBeDefined();
  expect(screen.queryByText(/Step 1 of 5/i)).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: /Load samples/i }));

  await waitFor(() => {
    expect(screen.getByRole("dialog", { name: /Read the passage that grounds the claim/i })).toBeDefined();
  });
  expect(appShell.currentRoute.value).toBe("/library");

  fireEvent.click(screen.getByRole("button", { name: /Open Ask/i }));
  expect(await screen.findByRole("dialog", { name: /Trace any answer back to the page/i })).toBeDefined();
  expect(appShell.currentRoute.value).toBe("/ask");
});

test("first-run tour defines product terms inline", async () => {
  window.localStorage.setItem(STORAGE_KEY, "1");
  // Must match the current TOUR_VERSION in FirstRunTour.tsx; bump
  // here whenever the production version bumps (the bump is by
  // design — re-prompts users on substantive content updates).
  window.localStorage.setItem("carrel.first-run-tour.version", "6");

  render(<FirstRunTour />);

  openFirstRunTour();

  expect(await screen.findByRole("dialog", { name: /Bring in a source you trust/i })).toBeDefined();

  const defineJobsTray = screen.getByRole("button", { name: /Define Jobs Tray/i });
  fireEvent.focus(defineJobsTray);

  expect(screen.getByText(/Live status of imports and extraction/i)).toBeDefined();
});

test("first-run tour does NOT auto-open by default", async () => {
  // Auto-open was retired 2026-05-07 in favor of inline on-app guidance
  // (see docs/onboarding-tutorial-script.md). The component stays mounted
  // for the manual Tour button + cmd+k shortcut, but a fresh user no
  // longer gets a modal overlay covering the actual UI on first launch.
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem("carrel.first-run-tour.version");
  window.localStorage.removeItem("carrel.first-run-tour.auto-open");

  render(<FirstRunTour />);

  // No dialog rendered, even with no completion marker set.
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("first-run tour CAN be force-opened via the dev override flag", async () => {
  // Useful for screenshotting the existing overlay while we build the
  // inline replacement. The flag is intentionally a localStorage opt-in
  // so a tester or designer can flip it from the devtools console
  // without rebuilding.
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem("carrel.first-run-tour.version");
  window.localStorage.setItem("carrel.first-run-tour.auto-open", "1");

  render(<FirstRunTour />);

  expect(await screen.findByRole("dialog", { name: /Bring in a source you trust/i })).toBeDefined();
});
