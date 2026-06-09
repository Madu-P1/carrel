import { act, renderHook, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { briefs as briefsApi, verify as verifyApi } from "@/services/api/endpoints";

import { useVerify } from "./useVerify";

// useVerify is the verification machine both hosts (Carrel's VerifyView and
// the Cachet lectern) trust: the streaming loop, the truncated-stream guard,
// the seal-seed lifecycle, and the no-reverify hydration path. It shipped
// untested; these lock the behaviors a regression would silently break.

vi.mock("@/services/api/endpoints", () => ({
  briefs: { get: vi.fn(), save: vi.fn(), list: vi.fn(), remove: vi.fn() },
  verify: { draft: vi.fn(), draftStream: vi.fn() }
}));

const mockDraftStream = vi.mocked(verifyApi.draftStream);
const mockBriefGet = vi.mocked(briefsApi.get);

afterEach(() => vi.clearAllMocks());

const RESPONSE = {
  draft_text: "The NDA term is three years.",
  claim_verdicts: [],
  summary: { total: 0, verified: 0, unsupported: 0, unknown: 0 },
  latency_ms: 1,
  model: "deterministic",
  ok: true,
  error: null,
  provider: "deterministic",
  quote_results: [],
  unplaced: []
};

function streamOf(events: unknown[]) {
  return (async function* () {
    for (const e of events) yield e;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  })() as any;
}

describe("useVerify — the streaming loop", () => {
  it("settles the response on a result event", async () => {
    mockDraftStream.mockReturnValue(
      streamOf([
        { type: "progress", phase: "extracting" },
        { type: "result", verify: RESPONSE }
      ])
    );
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("The NDA term is three years."));
    expect(result.current.response).toEqual(RESPONSE);
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.stream.phase).toBe("done");
  });

  it("TRUNCATED STREAM: an end without a result surfaces the refusal, never a partial pass", async () => {
    mockDraftStream.mockReturnValue(
      streamOf([
        { type: "progress", phase: "extracting" },
        { type: "claims", claim_verdicts: [] }
      ])
    );
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("draft"));
    expect(result.current.response).toBeNull();
    expect(result.current.error).toMatch(/did not finish/i);
    expect(result.current.error).toMatch(/nothing was marked supported/i);
    expect(result.current.loading).toBe(false);
  });

  it("an error event is surfaced verbatim and no response settles", async () => {
    mockDraftStream.mockReturnValue(streamOf([{ type: "error", error: "engine failed" }]));
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("draft"));
    expect(result.current.error).toBe("engine failed");
    expect(result.current.response).toBeNull();
  });

  it("ignores an empty draft (no request leaves the machine)", async () => {
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("   "));
    expect(mockDraftStream).not.toHaveBeenCalled();
  });

  it("ignores a second verify while one is in flight (no superseding mid-check)", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mockDraftStream.mockReturnValue(
      (async function* () {
        await gate;
        yield { type: "result", verify: RESPONSE };
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      })() as any
    );
    const { result } = renderHook(() => useVerify());
    let first!: Promise<void>;
    act(() => {
      first = result.current.verify("draft one");
    });
    await waitFor(() => expect(result.current.loading).toBe(true));
    await act(() => result.current.verify("draft two"));
    expect(mockDraftStream).toHaveBeenCalledTimes(1);
    release();
    await act(() => first);
    expect(result.current.response).toEqual(RESPONSE);
  });
});

describe("useVerify — hydration (open a saved brief, no re-verify)", () => {
  const DETAIL = {
    id: "b1",
    title: "The NDA term is three years.",
    draft: "The NDA term is three years.",
    fingerprint: "f1",
    seal_state: "sealed",
    response: RESPONSE,
    cert: { generatedAtISO: "2026-01-01T00:00:00.000Z" },
    created_at: null,
    updated_at: null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;

  it("re-hydrates the stored verdict, draft, and seal seeds without re-verifying", async () => {
    mockBriefGet.mockResolvedValue(DETAIL);
    const { result } = renderHook(() => useVerify({ briefId: "b1" }));
    await waitFor(() => expect(result.current.hydrating).toBe(false));
    expect(result.current.response).toEqual(RESPONSE);
    expect(result.current.hydratedDraft).toBe("The NDA term is three years.");
    expect(result.current.sealedSeed).toBe("f1");
    expect(result.current.certAtSeed).toBe("2026-01-01T00:00:00.000Z");
    expect(mockDraftStream).not.toHaveBeenCalled();
  });

  it("SEAL SEEDS: a fresh verify clears the reopened brief's seal and date", async () => {
    // The seeds may survive only an untouched re-export of that brief: a fresh
    // check is a NEW verification and must never export the prior seal or
    // timestamp onto a new result.
    mockBriefGet.mockResolvedValue(DETAIL);
    const { result } = renderHook(() => useVerify({ briefId: "b1" }));
    await waitFor(() => expect(result.current.sealedSeed).toBe("f1"));
    mockDraftStream.mockReturnValue(streamOf([{ type: "result", verify: RESPONSE }]));
    await act(() => result.current.verify("an edited draft"));
    expect(result.current.sealedSeed).toBeNull();
    expect(result.current.certAtSeed).toBeNull();
  });

  it("an unsealed brief seeds no seal", async () => {
    mockBriefGet.mockResolvedValue({ ...DETAIL, seal_state: "unsealed" });
    const { result } = renderHook(() => useVerify({ briefId: "b1" }));
    await waitFor(() => expect(result.current.hydrating).toBe(false));
    expect(result.current.sealedSeed).toBeNull();
  });

  it("a failed brief fetch surfaces its error and stops the opening state", async () => {
    mockBriefGet.mockRejectedValue(new Error("backend unreachable"));
    const { result } = renderHook(() => useVerify({ briefId: "b1" }));
    await waitFor(() => expect(result.current.hydrating).toBe(false));
    expect(result.current.error).toBe("backend unreachable");
    expect(result.current.response).toBeNull();
  });
});
