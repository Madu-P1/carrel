import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, it } from "vitest";

import { LecternView } from "./LecternView";
import { liveDraft } from "./liveDraft";

// Regression for the reported bug: paste on the lectern home, click off to the
// Shelf, click back -> the draft was gone and the page reset to the empty verify
// station. Root cause: the lectern kept its draft in component state, which the
// route-driven view swap destroyed on navigation. The draft now lives in the
// shared `liveDraft` signal, so it survives unmount and re-seeds on return.

afterEach(() => {
  liveDraft.value = "";
});

describe("LecternView draft persistence (shared liveDraft)", () => {
  it("seeds the textarea from the persisted liveDraft on mount", () => {
    liveDraft.value = "A draft pasted earlier, before visiting the Shelf.";
    render(<LecternView />);
    const ta = screen.getByLabelText("Draft to verify") as HTMLTextAreaElement;
    expect(ta.value).toBe("A draft pasted earlier, before visiting the Shelf.");
  });

  it("writes edits to liveDraft and restores them after unmount + remount", () => {
    const first = render(<LecternView />);
    fireEvent.input(first.getByLabelText("Draft to verify"), {
      target: { value: "The NDA term is three years, not five." }
    });
    expect(liveDraft.value).toBe("The NDA term is three years, not five.");

    // Navigating to the Shelf unmounts the lectern. The draft must persist...
    first.unmount();
    expect(liveDraft.value).toBe("The NDA term is three years, not five.");

    // ...and clicking back to the home page re-seeds it (the bug was an empty box).
    render(<LecternView />);
    expect((screen.getByLabelText("Draft to verify") as HTMLTextAreaElement).value).toBe(
      "The NDA term is three years, not five."
    );
  });
});
