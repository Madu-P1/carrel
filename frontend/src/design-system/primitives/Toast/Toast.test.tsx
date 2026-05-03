import { act, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, expect, test, vi } from "vitest";

import {
  ToastHost,
  _resetToastsForTesting,
  dismissToast,
  showToast,
  toast,
} from "./Toast";

afterEach(() => _resetToastsForTesting());

test("ToastHost renders a toast added via showToast", () => {
  render(<ToastHost />);
  act(() => {
    showToast({ title: "Saved", description: "Queued for review.", kind: "success" });
  });
  expect(screen.getByText("Saved")).toBeDefined();
  expect(screen.getByText("Queued for review.")).toBeDefined();
  // success kind is announced as "status" not "alert".
  const node = screen.getByText("Saved").closest('[role="status"]');
  expect(node).toBeDefined();
});

test("Error toasts announce as role=alert", () => {
  render(<ToastHost />);
  act(() => {
    toast.error("Kaboom", "Network issue");
  });
  const node = screen.getByText("Kaboom").closest('[role="alert"]');
  expect(node).toBeDefined();
});

test("Toasts auto-dismiss after their durationMs", async () => {
  vi.useFakeTimers();
  render(<ToastHost />);
  act(() => {
    showToast({ title: "Briefly", durationMs: 500 });
  });
  expect(screen.getByText("Briefly")).toBeDefined();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(500);
  });
  expect(screen.queryByText("Briefly")).toBeNull();
  vi.useRealTimers();
});

test("Toasts with durationMs=0 persist until dismissed", async () => {
  vi.useFakeTimers();
  render(<ToastHost />);
  let id = "";
  act(() => {
    id = showToast({ title: "Sticky", durationMs: 0 });
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000);
  });
  expect(screen.getByText("Sticky")).toBeDefined();
  act(() => dismissToast(id));
  expect(screen.queryByText("Sticky")).toBeNull();
  vi.useRealTimers();
});

test("Clicking the dismiss button removes the toast", () => {
  render(<ToastHost />);
  act(() => {
    showToast({ title: "Bye", durationMs: 0 });
  });
  fireEvent.click(screen.getByLabelText(/Dismiss notification/i));
  expect(screen.queryByText("Bye")).toBeNull();
});

test("Clicking a toast action runs the callback and dismisses the toast", () => {
  const onClick = vi.fn();
  render(<ToastHost />);
  act(() => {
    showToast({
      title: "Suggestion dismissed",
      action: { label: "Undo", onClick },
      durationMs: 0,
    });
  });

  fireEvent.click(screen.getByRole("button", { name: /Undo/i }));
  expect(onClick).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("Suggestion dismissed")).toBeNull();
});

test("Multiple toasts stack in insertion order", () => {
  render(<ToastHost />);
  act(() => {
    showToast({ title: "First", durationMs: 0 });
    showToast({ title: "Second", durationMs: 0 });
    showToast({ title: "Third", durationMs: 0 });
  });
  const host = screen.getByLabelText("Notifications");
  const titles = Array.from(host.querySelectorAll('[role="status"], [role="alert"]')).map(
    (el) => (el.textContent ?? "").replace("Dismiss notification", "").trim()
  );
  // The visual order matches insertion order (top = oldest).
  expect(titles[0]).toMatch(/^First/);
  expect(titles[2]).toMatch(/^Third/);
});
