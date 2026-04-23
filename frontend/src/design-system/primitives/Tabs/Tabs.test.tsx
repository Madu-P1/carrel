import { fireEvent, render, screen } from "@testing-library/preact";
import { useState } from "preact/hooks";
import { expect, test, vi } from "vitest";

import { Tabs, type TabItem } from "./Tabs";

const ITEMS: TabItem[] = [
  { id: "chunks", label: "Chunks", count: 12 },
  { id: "notes", label: "Notes", count: 3 },
  { id: "related", label: "Related", count: 5 },
  { id: "ask", label: "Ask" },
];

function Harness({ initial = "chunks" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return <Tabs items={ITEMS} onChange={setValue} value={value} ariaLabel="Reader rail" />;
}

test("renders a tablist with aria-selected on the active tab", () => {
  render(<Harness />);
  const list = screen.getByRole("tablist", { name: /Reader rail/i });
  expect(list).toBeDefined();
  const chunks = screen.getByRole("tab", { name: /Chunks/i });
  expect(chunks.getAttribute("aria-selected")).toBe("true");
  const notes = screen.getByRole("tab", { name: /Notes/i });
  expect(notes.getAttribute("aria-selected")).toBe("false");
});

test("clicking a tab fires onChange and updates aria-selected", () => {
  const onChange = vi.fn();
  render(<Tabs items={ITEMS} onChange={onChange} value="chunks" ariaLabel="Reader rail" />);
  fireEvent.click(screen.getByRole("tab", { name: /Notes/i }));
  expect(onChange).toHaveBeenCalledWith("notes");
});

test("ArrowRight / ArrowLeft cycles the active tab", () => {
  render(<Harness />);
  const list = screen.getByRole("tablist");
  const chunks = screen.getByRole("tab", { name: /Chunks/i });
  chunks.focus();
  fireEvent.keyDown(list, { key: "ArrowRight" });
  // State-driven: after the arrow, Notes is now aria-selected.
  expect(screen.getByRole("tab", { name: /Notes/i }).getAttribute("aria-selected")).toBe("true");
  fireEvent.keyDown(list, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: /Related/i }).getAttribute("aria-selected")).toBe("true");
  fireEvent.keyDown(list, { key: "ArrowLeft" });
  expect(screen.getByRole("tab", { name: /Notes/i }).getAttribute("aria-selected")).toBe("true");
});

test("ArrowRight wraps at the end; ArrowLeft wraps at the start", () => {
  render(<Harness initial="ask" />);
  const list = screen.getByRole("tablist");
  fireEvent.keyDown(list, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: /Chunks/i }).getAttribute("aria-selected")).toBe("true");
  fireEvent.keyDown(list, { key: "ArrowLeft" });
  expect(screen.getByRole("tab", { name: /Ask/i }).getAttribute("aria-selected")).toBe("true");
});

test("disabled tabs are not activatable", () => {
  const disabledItems: TabItem[] = [
    { id: "a", label: "Alpha" },
    { id: "b", label: "Beta", disabled: true },
    { id: "c", label: "Gamma" },
  ];
  const onChange = vi.fn();
  render(<Tabs items={disabledItems} onChange={onChange} value="a" />);
  const beta = screen.getByRole("tab", { name: /Beta/i });
  fireEvent.click(beta);
  expect(onChange).not.toHaveBeenCalled();
  // ArrowRight from 'a' skips 'b' and lands on 'c'.
  fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" });
  expect(onChange).toHaveBeenCalledWith("c");
});

test("count is rendered next to the label when provided", () => {
  render(<Harness />);
  // Chunks has count 12 — the count is a sibling span inside the tab.
  const chunks = screen.getByRole("tab", { name: /Chunks/i });
  expect(chunks.textContent).toMatch(/Chunks.*12/);
});

test("inline variant is structurally the same tablist", () => {
  render(<Tabs items={ITEMS} onChange={() => {}} value="chunks" variant="inline" />);
  expect(screen.getByRole("tablist")).toBeDefined();
});
