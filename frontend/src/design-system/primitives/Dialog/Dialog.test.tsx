import { fireEvent, render, screen } from "@testing-library/preact";
import { useState } from "preact/hooks";
import { expect, test } from "vitest";

import { Button } from "../Button";
import { Dialog } from "./Dialog";

function Harness() {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <Button onClick={() => setOpen(true)}>Open dialog</Button>
      <Dialog
        actions={<button type="button">Confirm</button>}
        onClose={() => setOpen(false)}
        open={open}
        title="Dialog title"
      >
        <input aria-label="Dialog input" />
      </Dialog>
    </div>
  );
}

test("Dialog opens and renders content", () => {
  render(<Harness />);

  fireEvent.click(screen.getByRole("button", { name: "Open dialog" }));
  expect(screen.getByRole("dialog")).toBeDefined();
});

test("Dialog closes on escape and restores focus", () => {
  render(<Harness />);

  const trigger = screen.getByRole("button", { name: "Open dialog" });
  trigger.focus();
  fireEvent.click(trigger);
  fireEvent.keyDown(window, { key: "Escape" });

  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

test("Dialog traps focus inside", () => {
  render(<Harness />);

  fireEvent.click(screen.getByRole("button", { name: "Open dialog" }));
  const input = screen.getByLabelText("Dialog input");
  const confirm = screen.getByRole("button", { name: "Confirm" });

  expect(document.activeElement).toBe(input);
  fireEvent.keyDown(window, { key: "Tab" });
  expect(document.activeElement).toBe(confirm);
  fireEvent.keyDown(window, { key: "Tab" });
  expect(document.activeElement).toBe(input);
});
