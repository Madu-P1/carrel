import { fireEvent, render } from "@testing-library/preact";
import { describe, expect, it, vi } from "vitest";

import { CommandPalette } from "./CommandPalette";
import type { Command } from "./commands";

function commands(run: () => void = () => {}): Command[] {
  return [
    { id: "verify", title: "Verify the draft", hint: "⌘↩", run },
    { id: "shelf", title: "Open the Shelf", keywords: "saved record", run }
  ];
}

describe("CommandPalette", () => {
  it("renders a modal dialog with a combobox and one option per command", () => {
    const { getByRole, getAllByRole } = render(
      <CommandPalette commands={commands()} onClose={() => {}} />
    );
    expect(getByRole("dialog").getAttribute("aria-modal")).toBe("true");
    expect(getByRole("combobox")).toBeTruthy();
    expect(getAllByRole("option").length).toBe(2);
  });

  it("filters the options as you type", () => {
    const { getByRole, getAllByRole } = render(
      <CommandPalette commands={commands()} onClose={() => {}} />
    );
    fireEvent.input(getByRole("combobox"), { target: { value: "shelf" } });
    const options = getAllByRole("option");
    expect(options.length).toBe(1);
    expect(options[0].textContent).toContain("Open the Shelf");
  });

  it("runs the active command on Enter", () => {
    const run = vi.fn();
    const { getByRole } = render(<CommandPalette commands={commands(run)} onClose={() => {}} />);
    fireEvent.keyDown(getByRole("dialog"), { key: "Enter" });
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    const { getByRole } = render(<CommandPalette commands={commands()} onClose={onClose} />);
    fireEvent.keyDown(getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("traps focus: Tab is prevented (one tab stop)", () => {
    const { getByRole } = render(<CommandPalette commands={commands()} onClose={() => {}} />);
    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    getByRole("dialog").dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("marks the active option via aria-activedescendant on the combobox", () => {
    const { getByRole } = render(<CommandPalette commands={commands()} onClose={() => {}} />);
    expect(getByRole("combobox").getAttribute("aria-activedescendant")).toBe("cachet-cmd-verify");
    fireEvent.keyDown(getByRole("dialog"), { key: "ArrowDown" });
    expect(getByRole("combobox").getAttribute("aria-activedescendant")).toBe("cachet-cmd-shelf");
  });
});
