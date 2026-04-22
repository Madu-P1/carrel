import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test, afterEach } from "vitest";

import {
  ShortcutsOverlay,
  shortcutsOverlayOpen,
  openShortcutsOverlay,
  closeShortcutsOverlay
} from "../../src/app/shell/ShortcutsOverlay";

afterEach(() => {
  closeShortcutsOverlay();
});

test("renders nothing when closed", () => {
  render(<ShortcutsOverlay />);
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("renders a dialog with shortcuts when open", () => {
  openShortcutsOverlay();
  render(<ShortcutsOverlay />);
  expect(screen.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeDefined();
  // Shows at least one shortcut from the Navigation group.
  expect(screen.getByText(/Dashboard/)).toBeDefined();
  expect(screen.getByText(/Command palette/)).toBeDefined();
  expect(screen.getByText(/Ask a question/)).toBeDefined();
});

test("closes when the close button is clicked", () => {
  openShortcutsOverlay();
  render(<ShortcutsOverlay />);

  fireEvent.click(screen.getByRole("button", { name: /close shortcuts/i }));
  expect(shortcutsOverlayOpen.value).toBe(false);
});

test("closes when Escape is pressed", () => {
  openShortcutsOverlay();
  render(<ShortcutsOverlay />);

  fireEvent.keyDown(window, { key: "Escape" });
  expect(shortcutsOverlayOpen.value).toBe(false);
});

test("closes when the backdrop is clicked, but NOT when the sheet is clicked", () => {
  openShortcutsOverlay();
  render(<ShortcutsOverlay />);

  // Click the sheet content — should stay open (click stops propagation).
  fireEvent.click(screen.getByText(/Dashboard/));
  expect(shortcutsOverlayOpen.value).toBe(true);

  // Click the backdrop (role=dialog is the backdrop in our markup).
  fireEvent.click(screen.getByRole("dialog"));
  expect(shortcutsOverlayOpen.value).toBe(false);
});
