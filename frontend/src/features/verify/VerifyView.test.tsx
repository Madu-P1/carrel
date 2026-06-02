import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { briefs as briefsApi, verify as verifyApi } from "@/services/api/endpoints";

import { VerifyView } from "./VerifyView";

// Cachet PR6b: opening a saved brief re-hydrates the settled view from the STORED
// response with NO re-verify. Mock the endpoints module so the open path is
// driven deterministically; assert the stream is never invoked.
vi.mock("@/services/api/endpoints", () => ({
  briefs: { get: vi.fn(), save: vi.fn(), list: vi.fn(), remove: vi.fn() },
  verify: { draft: vi.fn(), draftStream: vi.fn() }
}));

const mockGet = vi.mocked(briefsApi.get);
const mockDraftStream = vi.mocked(verifyApi.draftStream);

const STORED_DRAFT = "The statute applies to this matter under controlling precedent.";

function storedResponse() {
  return {
    draft_text: STORED_DRAFT,
    claim_verdicts: [
      {
        claim_index: 0,
        claim_text: STORED_DRAFT,
        verdict: "verified",
        citations: [],
        case_verdicts: [],
        placement: { placed: true, method: "exact", char_start: 0, char_end: STORED_DRAFT.length }
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
}

function briefDetail(overrides: Record<string, unknown> = {}) {
  const resp = storedResponse();
  return {
    id: "b1",
    title: "Motion to Dismiss",
    fingerprint: "a".repeat(64),
    seal_state: "sealed",
    created_at: "2026-01-02T00:00:00+00:00",
    updated_at: "2026-01-02T00:00:00+00:00",
    draft: STORED_DRAFT,
    response: resp,
    cert: null,
    ...overrides
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("VerifyView re-hydration (open a saved brief)", () => {
  it("fetches the brief and re-hydrates the draft without ever re-verifying", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockGet.mockResolvedValue(briefDetail() as any);
    render(<VerifyView briefId="b1" />);

    // The stored draft is seeded into the editor (proves setDraft from the effect).
    await waitFor(() => {
      const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
      expect(textarea.value).toBe(STORED_DRAFT);
    });
    expect(mockGet).toHaveBeenCalledWith("b1", expect.objectContaining({ signal: expect.anything() }));
    // The whole point: re-hydration must NOT trigger a fresh verification.
    expect(mockDraftStream).not.toHaveBeenCalled();
  });

  it("does not fetch a brief on the live verify flow (briefId null)", async () => {
    render(<VerifyView briefId={null} />);
    // The effect's `if (!briefId) return` guard keeps the live flow untouched.
    expect(mockGet).not.toHaveBeenCalled();
    expect(mockDraftStream).not.toHaveBeenCalled();
  });

  it("shows a neutral 'Opening…' state during the fetch, never the verify chrome", async () => {
    // A never-resolving get keeps the fetch window open for the assertion.
    mockGet.mockReturnValue(new Promise<never>(() => {}));
    render(<VerifyView briefId="b1" />);

    expect(await screen.findByText("Opening saved brief…")).toBeTruthy();
    // The no-verify promise: opening a brief must never claim it is verifying.
    expect(screen.queryByText("Verifying…")).toBeNull();
    expect(screen.queryByText(/extracting claims/i)).toBeNull();
  });

  it("clears the reopened seal and date on a manual re-verify (no stale cracked export)", async () => {
    // Reopen a SEALED brief: seeds sealedSeed = its fingerprint, certAtSeed = its date.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockGet.mockResolvedValue(briefDetail({ seal_state: "sealed" }) as any);
    // The fresh re-verify streams a NEW response over an edited draft.
    const newDraft = "A substantially edited draft with entirely different content now.";
    const newResp = {
      ...storedResponse(),
      draft_text: newDraft,
      claim_verdicts: [
        {
          claim_index: 0,
          claim_text: newDraft,
          verdict: "verified",
          citations: [],
          case_verdicts: [],
          placement: { placed: true, method: "exact", char_start: 0, char_end: newDraft.length }
        }
      ]
    };
    mockDraftStream.mockReturnValue(
      (async function* () {
        yield { type: "result", verify: newResp };
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      })() as any
    );

    render(<VerifyView briefId="a1" />);
    await waitFor(() => {
      expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe(STORED_DRAFT);
    });

    // Edit the draft and re-verify: a NEW check, not a re-export of the brief.
    fireEvent.input(screen.getByRole("textbox"), { target: { value: newDraft } });
    fireEvent.click(screen.getByText("Verify the draft"));
    await screen.findByText("Export certification");

    // Open the certification on the fresh check.
    fireEvent.click(screen.getByText("Export certification"));

    // The fresh check must be UNSEALED — never the prior brief's stale "cracked"
    // seal. (Before the seed-clear fix this exported a false cracked seal.)
    expect(screen.getByRole("button", { name: "Set the seal" })).toBeTruthy();
    expect(screen.queryByRole("img", { name: /cracked/i })).toBeNull();
  });
});
