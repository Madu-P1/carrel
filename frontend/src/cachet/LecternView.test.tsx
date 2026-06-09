import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { navigateTo } from "@/app/shell/useAppShell";
import { verify as verifyApi } from "@/services/api/endpoints";

import { LecternView } from "./LecternView";
import { liveDraft } from "./liveDraft";

// The lectern is the verify surface: verifying runs the check in place and the
// verdict unfolds beneath the sheet, so navigateTo must NOT fire (the operator's
// "false page" — a hand-off to a separate /verify form — is the regression these
// guard). documentsApi.list backs the record picker; verifyApi.draftStream backs
// the inline check.
vi.mock("@/app/shell/useAppShell", () => ({ navigateTo: vi.fn() }));
vi.mock("@/services/api/endpoints", () => ({
  verify: { draft: vi.fn(), draftStream: vi.fn() },
  briefs: { get: vi.fn(), save: vi.fn(), list: vi.fn(), remove: vi.fn() },
  documents: { list: vi.fn().mockResolvedValue([]), upload: vi.fn() }
}));

const mockNavigate = vi.mocked(navigateTo);
const mockDraftStream = vi.mocked(verifyApi.draftStream);

// Regression for the reported bug: paste on the lectern home, click off to the
// Shelf, click back -> the draft was gone and the page reset to the empty verify
// station. Root cause: the lectern kept its draft in component state, which the
// route-driven view swap destroyed on navigation. The draft now lives in the
// shared `liveDraft` signal, so it survives unmount and re-seeds on return.

afterEach(() => {
  liveDraft.value = "";
  vi.clearAllMocks();
});

const VERIFY_RESPONSE = {
  draft_text: "The NDA term is three years.",
  claim_verdicts: [
    {
      claim_index: 0,
      claim_text: "The NDA term is three years.",
      verdict: "verified",
      citations: [],
      case_verdicts: [],
      placement: { placed: true, method: "exact", char_start: 0, char_end: 28 }
    }
  ],
  summary: { total: 1, verified: 1, unsupported: 0, unknown: 0 },
  latency_ms: 10,
  model: "claude-sonnet-4-6",
  ok: true,
  error: null,
  provider: "claude",
  quote_results: [],
  unplaced: []
};

describe("LecternView inline verify (the unified surface)", () => {
  it("renders the verdict in place and never navigates to a separate page", async () => {
    mockDraftStream.mockReturnValue(
      (async function* () {
        yield { type: "result", verify: VERIFY_RESPONSE };
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      })() as any
    );
    liveDraft.value = "The NDA term is three years.";
    render(<LecternView />);

    fireEvent.click(screen.getByText("Verify"));

    // The verdict summary renders inside the lectern...
    expect(
      await screen.findByText("All 1 statements are supported by the sources you provided.")
    ).toBeTruthy();
    // ...the sheet is still on screen (we did not leave the lectern)...
    expect(screen.getByLabelText("Draft to verify")).toBeTruthy();
    // ...and crucially nothing navigated to a second compose page.
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("does not verify an empty draft", () => {
    liveDraft.value = "   ";
    render(<LecternView />);
    fireEvent.click(screen.getByText("Verify"));
    expect(mockDraftStream).not.toHaveBeenCalled();
  });
});

describe("LecternView command spine (cachet:command)", () => {
  // The ⌘K palette dispatches cachet:command and dismisses itself. A verb that
  // dispatches into the void looks like it worked (the palette closes) while
  // doing nothing — on this surface a silent no-op is a trust defect.
  it("runs the inline verify when the palette dispatches verify-draft", async () => {
    mockDraftStream.mockReturnValue(
      (async function* () {
        yield { type: "result", verify: VERIFY_RESPONSE };
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      })() as any
    );
    liveDraft.value = "The NDA term is three years.";
    render(<LecternView />);
    fireEvent(window, new CustomEvent("cachet:command", { detail: { id: "verify-draft" } }));
    expect(
      await screen.findByText("All 1 statements are supported by the sources you provided.")
    ).toBeTruthy();
    expect(mockDraftStream).toHaveBeenCalledTimes(1);
  });

  it("ignores the verify command when the draft is empty (same guard as the button)", () => {
    liveDraft.value = "   ";
    render(<LecternView />);
    fireEvent(window, new CustomEvent("cachet:command", { detail: { id: "verify-draft" } }));
    expect(mockDraftStream).not.toHaveBeenCalled();
  });
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
