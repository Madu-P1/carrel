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

test("Tooltip dismisses immediately when the trigger is clicked (flight-through)", async () => {
  vi.useFakeTimers();
  render(
    <Tooltip content="Source · p.3">
      <button type="button">Hover</button>
    </Tooltip>
  );
  const trigger = screen.getByRole("button", { name: "Hover" }).parentElement as Element;
  fireEvent.mouseOver(trigger);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  expect(screen.getByRole("tooltip")).toBeDefined();
  fireEvent.click(trigger);
  expect(screen.queryByRole("tooltip")).toBeNull();
  vi.useRealTimers();
});

test("Tooltip multiline variant adds the multiline class so the content wraps", async () => {
  vi.useFakeTimers();
  render(
    <Tooltip content="A long quote that should wrap across multiple lines in the tooltip." multiline>
      <button type="button">Hover</button>
    </Tooltip>
  );
  fireEvent.mouseOver(screen.getByRole("button").parentElement as Element);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  const tip = screen.getByRole("tooltip");
  // The class attribute should include a `multiline`-named CSS-modules class.
  expect(tip.className).toMatch(/multiline/);
  vi.useRealTimers();
});

test("Tooltip honors a custom delay", async () => {
  vi.useFakeTimers();
  render(
    <Tooltip content="Fast" delay={100}>
      <button type="button">Hover</button>
    </Tooltip>
  );
  fireEvent.mouseOver(screen.getByRole("button").parentElement as Element);
  // Not yet — 60ms is less than the custom 100ms delay.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60);
  });
  expect(screen.queryByRole("tooltip")).toBeNull();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60);
  });
  expect(screen.getByRole("tooltip")).toBeDefined();
  vi.useRealTimers();
});
