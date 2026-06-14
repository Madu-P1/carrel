import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { useState } from "preact/hooks";
import { describe, expect, it } from "vitest";

import { useFocusTrap } from "./useFocusTrap";

function Trapped({ onDismiss }: { onDismiss: () => void }) {
  const ref = useFocusTrap<HTMLDivElement>(true);
  return (
    <div ref={ref} role="dialog" tabIndex={-1}>
      <button type="button">field-a</button>
      <button type="button">field-b</button>
      <button type="button" onClick={onDismiss}>
        dismiss
      </button>
    </div>
  );
}

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        opener
      </button>
      {open ? <Trapped onDismiss={() => setOpen(false)} /> : null}
    </div>
  );
}

describe("useFocusTrap", () => {
  it("moves focus into the panel on activate and restores it to the opener on deactivate", async () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "opener" });
    opener.focus();
    fireEvent.click(opener);

    const first = await screen.findByRole("button", { name: "field-a" });
    await waitFor(() => expect(document.activeElement).toBe(first));

    fireEvent.click(screen.getByRole("button", { name: "dismiss" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "field-a" })).toBeNull());
    expect(document.activeElement).toBe(opener);
  });

  it("wraps Tab in both directions and pulls focus back when it drifts outside", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "opener" }));
    const first = screen.getByRole("button", { name: "field-a" });
    const last = screen.getByRole("button", { name: "dismiss" });

    // Forward from the last focusable wraps to the first.
    last.focus();
    const forward = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(forward);
    expect(forward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);

    // Backward from the first wraps to the last.
    const backward = new KeyboardEvent("keydown", {
      key: "Tab",
      shiftKey: true,
      bubbles: true,
      cancelable: true
    });
    document.dispatchEvent(backward);
    expect(backward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(last);

    // Focus drifted outside the panel: forward Tab pulls it back in.
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    outside.focus();
    const pull = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(pull);
    expect(pull.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);
    outside.remove();
  });
});
