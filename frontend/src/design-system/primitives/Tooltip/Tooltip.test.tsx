import { act, fireEvent, render, screen } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { Tooltip } from "./Tooltip";

test("Tooltip renders its trigger", () => {
  render(
    <Tooltip content="Hint">
      <button type="button">Hover</button>
    </Tooltip>
  );

  expect(screen.getByRole("button", { name: "Hover" })).toBeDefined();
});

test("Tooltip appears after delay and dismisses on escape", async () => {
  vi.useFakeTimers();

  render(
    <Tooltip content="Hint">
      <button type="button">Hover</button>
    </Tooltip>
  );

  fireEvent.mouseOver(screen.getByRole("button", { name: "Hover" }).parentElement as Element);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  expect(screen.getByRole("tooltip")).toBeDefined();

  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("tooltip")).toBeNull();

  vi.useRealTimers();
});

test("Tooltip dismisses on pointer leave", async () => {
  vi.useFakeTimers();

  render(
    <Tooltip content="Hint">
      <button type="button">Hover</button>
    </Tooltip>
  );

  const button = screen.getByRole("button", { name: "Hover" });
  fireEvent.mouseOver(button.parentElement as Element);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  fireEvent.mouseLeave(button.parentElement as Element);

  expect(screen.queryByRole("tooltip")).toBeNull();
  vi.useRealTimers();
});
