import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { useState } from "preact/hooks";
import { describe, expect, it } from "vitest";

import { useModalDialog } from "./useModalDialog";

function Dialog({ onDismiss }: { onDismiss: () => void }) {
  const ref = useModalDialog<HTMLDivElement>(true);
  return (
    <div ref={ref} data-testid="scrim">
      <div role="dialog" tabIndex={-1}>
        <button type="button">field-a</button>
        <button type="button" onClick={onDismiss}>
          dismiss
        </button>
      </div>
    </div>
  );
}

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <nav data-testid="bg-rail">rail</nav>
      <button type="button" onClick={() => setOpen(true)}>
        opener
      </button>
      {open ? <Dialog onDismiss={() => setOpen(false)} /> : null}
    </div>
  );
}

describe("useModalDialog", () => {
  it("on open: inerts the sibling background and moves focus into the dialog", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "opener" }));

    const rail = screen.getByTestId("bg-rail");
    expect(rail.hasAttribute("inert")).toBe(true);
    expect(rail.getAttribute("aria-hidden")).toBe("true");
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "field-a" }))
    );
  });

  it("traps Tab inside the dialog, wrapping in both directions", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "opener" }));
    const first = screen.getByRole("button", { name: "field-a" });
    const last = screen.getByRole("button", { name: "dismiss" });

    last.focus();
    const forward = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(forward);
    expect(forward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);

    const backward = new KeyboardEvent("keydown", {
      key: "Tab",
      shiftKey: true,
      bubbles: true,
      cancelable: true
    });
    document.dispatchEvent(backward);
    expect(backward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(last);
  });

  // The ordering guard (addresses the "test can't catch the inert-ordering bug"
  // finding): the opener lives in an inerted sibling, so a correct close MUST
  // un-inert the background BEFORE restoring focus. We record the background's
  // inert state AT THE MOMENT focus is restored; if restore ran first this is
  // true, and in a real browser .focus() into an inert subtree is a no-op.
  it("on close: un-inerts the background BEFORE restoring focus to the opener", async () => {
    let railInertAtRestore: boolean | null = null;

    function OrderingHarness() {
      const [open, setOpen] = useState(false);
      return (
        <div>
          <nav data-testid="ord-rail">rail</nav>
          <button
            type="button"
            data-testid="ord-opener"
            // The opener is a sibling of the scrim, so it gets inerted on open.
            ref={(node) => {
              if (node) {
                node.addEventListener("focus", () => {
                  const rail = document.querySelector('[data-testid="ord-rail"]');
                  railInertAtRestore = rail?.hasAttribute("inert") ?? null;
                });
              }
            }}
            onClick={() => setOpen(true)}
          >
            opener
          </button>
          {open ? <Dialog onDismiss={() => setOpen(false)} /> : null}
        </div>
      );
    }

    render(<OrderingHarness />);
    const opener = screen.getByTestId("ord-opener");
    opener.focus();
    railInertAtRestore = null; // ignore the pre-open focus
    fireEvent.click(opener);

    await screen.findByRole("button", { name: "field-a" });
    fireEvent.click(screen.getByRole("button", { name: "dismiss" }));

    await waitFor(() => expect(document.activeElement).toBe(opener));
    expect(railInertAtRestore).toBe(false);
  });
});
