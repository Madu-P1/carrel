import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { briefs as briefsApi, verify as verifyApi } from "@/services/api/endpoints";

import { createVerifyStore, useVerify, type VerifyStore } from "./useVerify";
import { VerifyResults } from "./VerifyResults";

// The full seal-survival chain with a REAL engine, not stubs: verify -> open
// the certification -> set the seal -> the host unmounts (the rail click) ->
// remounts. The adversarial review proved the markSealed wiring was a
// surviving mutant (deleting it failed zero tests) and that a reopened
// exhibit minted a FRESH timestamp onto a sealed filing-grade artifact. This
// file is the mutant killer for both: after the remount the quiet Save must
// stay hidden (its upsert silently downgrades the seal) and the reopened
// exhibit must carry the ORIGINAL seal date.

vi.mock("@/services/api/endpoints", () => ({
  briefs: { get: vi.fn(), save: vi.fn(), list: vi.fn(), remove: vi.fn() },
  verify: { draft: vi.fn(), draftStream: vi.fn() },
  documents: { list: vi.fn() }
}));

const mockDraftStream = vi.mocked(verifyApi.draftStream);
const mockSave = vi.mocked(briefsApi.save);

afterEach(() => vi.clearAllMocks());

const DRAFT = "The NDA term is three years.";
const RESPONSE = {
  draft_text: DRAFT,
  claim_verdicts: [
    {
      claim_index: 0,
      claim_text: DRAFT,
      verdict: "verified",
      citations: [],
      case_verdicts: [],
      placement: { placed: true, method: "exact", char_start: 0, char_end: DRAFT.length }
    }
  ],
  summary: { total: 1, verified: 1, unsupported: 0, unknown: 0 },
  latency_ms: 1,
  model: "deterministic",
  ok: true,
  error: null,
  provider: "deterministic",
  quote_results: [],
  unplaced: []
};

function Host({ store }: { store: VerifyStore }) {
  const engine = useVerify({ store });
  return (
    <div>
      <button type="button" onClick={() => void engine.verify(DRAFT)}>
        Run the check
      </button>
      <VerifyResults engine={engine} draft={DRAFT} />
    </div>
  );
}

describe("seal survival across a host remount (real engine, persistent store)", () => {
  it("keeps the quiet Save hidden and re-renders the ORIGINAL seal date", async () => {
    mockDraftStream.mockReturnValue(
      (async function* () {
        yield { type: "result", verify: RESPONSE };
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      })() as any
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockSave.mockResolvedValue({} as any);

    const store = createVerifyStore();
    const first = render(<Host store={store} />);
    fireEvent.click(first.getByText("Run the check"));
    await first.findByText("All 1 statements are supported by the sources you provided.");

    // Open the certification and set the seal.
    fireEvent.click(first.getByText("Export certification"));
    fireEvent.click(await first.findByRole("button", { name: "Set the seal" }));
    const sealedCaption = (await first.findByText(/^Sealed /)).textContent ?? "";
    expect(sealedCaption).toMatch(/^Sealed .+ UTC$/);
    await waitFor(() =>
      expect(mockSave).toHaveBeenCalledWith(expect.objectContaining({ seal_state: "sealed" }))
    );
    fireEvent.click(first.getByRole("button", { name: "Close" }));

    // The rail click: unmount, then return.
    first.unmount();
    render(<Host store={store} />);
    expect(
      await screen.findByText("All 1 statements are supported by the sources you provided.")
    ).toBeTruthy();

    // The seal survived: no quiet Save (its upsert would downgrade the seal)...
    expect(screen.queryByText("Save to Shelf")).toBeNull();

    // ...and the reopened exhibit shows the seal SET with the ORIGINAL date,
    // not a freshly minted one.
    fireEvent.click(screen.getByText("Export certification"));
    const reopenedCaption = (await screen.findByText(/^Sealed /)).textContent ?? "";
    expect(reopenedCaption).toBe(sealedCaption);
    const sealButton = screen.getByRole("button", { name: /Sealed|Set the seal/ });
    expect((sealButton as HTMLButtonElement).disabled).toBe(true);
  });
});
