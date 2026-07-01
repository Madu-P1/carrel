import { act, renderHook, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { briefs as briefsApi, verify as verifyApi } from "@/services/api/endpoints";

import { isCardChecking } from "./streamProgress";
import { createVerifyStore, resetVerifyStore, useVerify } from "./useVerify";

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

/** A stream that yields some real events, then THROWS instead of yielding a
 *  clean end or a `result`. Models any transport-level failure mid-iteration
 *  (fetch rejecting, `reader.read()` throwing on a dropped connection, or the
 *  SSE decoder's `JSON.parse` failing on a malformed frame) — from the hook's
 *  vantage point these are indistinguishable: an exception surfaces out of
 *  the `for await` loop and must be caught, not an abort. */
function streamThatThrows(events: unknown[], failure: Error) {
  return (async function* () {
    for (const e of events) yield e;
    throw failure;
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

// T71: a dropped, errored, or truncated verify stream must never leave a claim
// the server had not yet returned a final verdict for reading as "verified".
// `streamInterrupted` is the explicit signal that lets a caller tell a
// completed run apart from an interrupted one.
describe("useVerify — T71: streamInterrupted honesty invariant", () => {
  const CLEAN_CASE_VERDICT = {
    ok: true,
    verdicts: [
      { status: 200, exists: true, holding_match: null, holding_error: null, holding_skipped: true }
    ]
  };

  function skeletonCards(indices: number[]) {
    return indices.map((claim_index) => ({
      claim_index,
      text: `claim ${claim_index}`,
      verdict: "verified",
      case_verdicts: []
    }));
  }

  it("ABORT MID-STREAM: resolved claims keep their verdicts, the in-flight claim is never verified, and streamInterrupted is true", async () => {
    const CARDS = skeletonCards([0, 1, 2]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockDraftStream.mockImplementation(((_payload: unknown, opts?: { signal?: AbortSignal }): any =>
      (async function* () {
        yield { type: "progress", phase: "extracting" };
        yield { type: "claims", claim_verdicts: CARDS };
        yield { type: "cite_verdict", claim_index: 0, case_verdict: CLEAN_CASE_VERDICT };
        yield { type: "cite_verdict", claim_index: 1, case_verdict: CLEAN_CASE_VERDICT };
        // claim_index 2's cite_verdict never lands: hang until the run is aborted.
        await new Promise<void>((_resolve, reject) => {
          const onAbort = () => reject(new DOMException("aborted", "AbortError"));
          if (opts?.signal?.aborted) {
            onAbort();
            return;
          }
          opts?.signal?.addEventListener("abort", onAbort);
        });
      })()) as never);
    const { result } = renderHook(() => useVerify());
    let p!: Promise<void>;
    act(() => {
      p = result.current.verify("three claims, one still in flight");
    });
    await waitFor(() => expect(result.current.stream.checked.size).toBe(2));
    act(() => result.current.cancel());
    await act(() => p);

    // The two claims that already landed a final cite_verdict are unchanged.
    expect(result.current.stream.checked.has(0)).toBe(true);
    expect(result.current.stream.checked.has(1)).toBe(true);
    const card0 = result.current.stream.cards.find((c) => c.claim_index === 0)!;
    const card1 = result.current.stream.cards.find((c) => c.claim_index === 1)!;
    expect(isCardChecking(result.current.stream, card0)).toBe(false);
    expect(isCardChecking(result.current.stream, card1)).toBe(false);

    // The third claim never received a final verdict: it must never read as verified.
    expect(result.current.stream.checked.has(2)).toBe(false);
    const card2 = result.current.stream.cards.find((c) => c.claim_index === 2)!;
    expect(isCardChecking(result.current.stream, card2)).toBe(true);

    expect(result.current.streamInterrupted).toBe(true);
    expect(result.current.response).toBeNull();
  });

  it("NETWORK ERROR: a transport failure thrown mid-stream (fetch rejects / reader.read() throws) sets streamInterrupted, and an unchecked claim never reads as verified", async () => {
    const CARDS = skeletonCards([0, 1]);
    mockDraftStream.mockReturnValue(
      streamThatThrows(
        [
          { type: "progress", phase: "extracting" },
          { type: "claims", claim_verdicts: CARDS },
          { type: "cite_verdict", claim_index: 0, case_verdict: CLEAN_CASE_VERDICT }
          // claim_index 1 never gets a cite_verdict: the connection drops here.
        ],
        new TypeError("network connection lost")
      )
    );
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("draft"));

    expect(result.current.error).toBe("network connection lost");
    expect(result.current.response).toBeNull();
    // The claim that already landed keeps its verdict; the one that didn't
    // must never read as verified just because the transport died.
    expect(result.current.stream.checked.has(0)).toBe(true);
    expect(result.current.stream.checked.has(1)).toBe(false);
    const card1 = result.current.stream.cards.find((c) => c.claim_index === 1)!;
    expect(isCardChecking(result.current.stream, card1)).toBe(true);
    expect(result.current.streamInterrupted).toBe(true);
  });

  it("TRUNCATION: a stream that ends without a completion event leaves no claim reading as verified, and streamInterrupted is true", async () => {
    const CARDS = skeletonCards([0, 1]);
    mockDraftStream.mockReturnValue(
      streamOf([
        { type: "progress", phase: "extracting" },
        { type: "claims", claim_verdicts: CARDS }
        // No cite_verdict, no result: the stream just closes.
      ])
    );
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("draft"));

    expect(result.current.stream.checked.size).toBe(0);
    for (const card of result.current.stream.cards) {
      expect(isCardChecking(result.current.stream, card)).toBe(true);
    }
    expect(result.current.streamInterrupted).toBe(true);
    expect(result.current.response).toBeNull();
  });

  it("MALFORMED CHUNK: an unparseable stream frame (JSON.parse failure) sets streamInterrupted, and an unchecked claim never reads as verified", async () => {
    const CARDS = skeletonCards([0, 1]);
    mockDraftStream.mockReturnValue(
      streamThatThrows(
        [
          { type: "progress", phase: "extracting" },
          { type: "claims", claim_verdicts: CARDS },
          { type: "cite_verdict", claim_index: 0, case_verdict: CLEAN_CASE_VERDICT }
          // claim_index 1 never gets a cite_verdict: the next frame fails to decode.
        ],
        new SyntaxError("Unexpected token in JSON at position 42")
      )
    );
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("draft"));

    expect(result.current.error).toBe("Unexpected token in JSON at position 42");
    expect(result.current.response).toBeNull();
    // The claim that already landed keeps its verdict; the one that didn't
    // must never read as verified just because the decoder choked.
    expect(result.current.stream.checked.has(0)).toBe(true);
    expect(result.current.stream.checked.has(1)).toBe(false);
    const card1 = result.current.stream.cards.find((c) => c.claim_index === 1)!;
    expect(isCardChecking(result.current.stream, card1)).toBe(true);
    expect(result.current.streamInterrupted).toBe(true);
  });

  it("STREAM ERROR: a surfaced error event sets streamInterrupted, and an unchecked claim never reads as verified", async () => {
    const CARDS = skeletonCards([0, 1]);
    mockDraftStream.mockReturnValue(
      streamOf([
        { type: "progress", phase: "extracting" },
        { type: "claims", claim_verdicts: CARDS },
        { type: "cite_verdict", claim_index: 0, case_verdict: CLEAN_CASE_VERDICT },
        // claim_index 1 never gets a cite_verdict: the transport fails first.
        { type: "error", error: "engine failed" }
      ])
    );
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("draft"));

    expect(result.current.error).toBe("engine failed");
    expect(result.current.response).toBeNull();
    // The claim that already landed keeps its verdict; the one that didn't
    // must never read as verified just because the stream moved past it.
    expect(result.current.stream.checked.has(0)).toBe(true);
    expect(result.current.stream.checked.has(1)).toBe(false);
    const card1 = result.current.stream.cards.find((c) => c.claim_index === 1)!;
    expect(isCardChecking(result.current.stream, card1)).toBe(true);
    expect(result.current.streamInterrupted).toBe(true);
  });

  it("CLEAN COMPLETION: a fully-completed stream settles every verdict and streamInterrupted is false", async () => {
    const CARDS = skeletonCards([0, 1]);
    mockDraftStream.mockReturnValue(
      streamOf([
        { type: "progress", phase: "extracting" },
        { type: "claims", claim_verdicts: CARDS },
        { type: "cite_verdict", claim_index: 0, case_verdict: CLEAN_CASE_VERDICT },
        { type: "cite_verdict", claim_index: 1, case_verdict: CLEAN_CASE_VERDICT },
        { type: "result", verify: RESPONSE }
      ])
    );
    const { result } = renderHook(() => useVerify());
    await act(() => result.current.verify("draft"));

    expect(result.current.stream.checked.has(0)).toBe(true);
    expect(result.current.stream.checked.has(1)).toBe(true);
    for (const card of result.current.stream.cards) {
      expect(isCardChecking(result.current.stream, card)).toBe(false);
    }
    expect(result.current.streamInterrupted).toBe(false);
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

describe("useVerify — external store (state survives unmount-on-nav)", () => {
  it("a host remount with the same store keeps the verdict without re-verifying", async () => {
    mockDraftStream.mockReturnValue(streamOf([{ type: "result", verify: RESPONSE }]));
    const store = createVerifyStore();
    const first = renderHook(() => useVerify({ store }));
    await act(() => first.result.current.verify("The NDA term is three years."));
    expect(first.result.current.response).toEqual(RESPONSE);

    // The route swap unmounts the host...
    first.unmount();

    // ...and the next mount reads the same engine state back.
    const second = renderHook(() => useVerify({ store }));
    expect(second.result.current.response).toEqual(RESPONSE);
    expect(second.result.current.stream.phase).toBe("done");
    expect(mockDraftStream).toHaveBeenCalledTimes(1);
  });

  it("instances WITHOUT a store stay isolated (Carrel hosts unchanged)", async () => {
    mockDraftStream.mockReturnValue(streamOf([{ type: "result", verify: RESPONSE }]));
    const a = renderHook(() => useVerify());
    const b = renderHook(() => useVerify());
    await act(() => a.result.current.verify("draft"));
    expect(a.result.current.response).toEqual(RESPONSE);
    expect(b.result.current.response).toBeNull();
  });

  it("markSealed records the live seal so a remount still hides the quiet save", async () => {
    const store = createVerifyStore();
    const first = renderHook(() => useVerify({ store }));
    act(() => first.result.current.markSealed("fp-live", "2026-06-09T10:00:00.000Z"));
    first.unmount();
    const second = renderHook(() => useVerify({ store }));
    expect(second.result.current.sealedSeed).toBe("fp-live");
    // The PAIR persists: a reopened exhibit re-renders the original seal date.
    expect(second.result.current.certAtSeed).toBe("2026-06-09T10:00:00.000Z");
    // A fresh verify is a NEW verification: the live seal clears like any seed.
    mockDraftStream.mockReturnValue(streamOf([{ type: "result", verify: RESPONSE }]));
    await act(() => second.result.current.verify("an edited draft"));
    expect(second.result.current.sealedSeed).toBeNull();
    expect(second.result.current.certAtSeed).toBeNull();
  });

  it("resetVerifyStore returns a persistent store to boot state", async () => {
    mockDraftStream.mockReturnValue(streamOf([{ type: "result", verify: RESPONSE }]));
    const persistent = createVerifyStore();
    const h = renderHook(() => useVerify({ store: persistent }));
    await act(() => h.result.current.verify("draft"));
    expect(h.result.current.response).toEqual(RESPONSE);
    act(() => resetVerifyStore(persistent));
    expect(h.result.current.response).toBeNull();
    expect(h.result.current.stream.phase).toBe("idle");
  });
});

/** A draftStream mock that honors the abort signal the way the real streamSse
 *  does (read() rejects with AbortError), gated on an external release. */
function gatedAbortableStream(gate: Promise<void>) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (_payload: unknown, opts?: { signal?: AbortSignal }): any =>
    (async function* () {
      await new Promise<void>((resolve, reject) => {
        const onAbort = () => reject(new DOMException("aborted", "AbortError"));
        if (opts?.signal?.aborted) {
          onAbort();
          return;
        }
        opts?.signal?.addEventListener("abort", onAbort);
        void gate.then(resolve);
      });
      yield { type: "result", verify: RESPONSE };
    })();
}

describe("useVerify — cancel and supersede lifecycle (persistent store)", () => {
  it("cancel() aborts a hung check and settles to idle: Verify is recoverable", async () => {
    // With a persistent store, loading survives navigation by design, so a
    // hung stream with no cancel would disable Verify until app relaunch.
    const gate = new Promise<void>(() => {}); // never releases: the hang
    mockDraftStream.mockImplementation(gatedAbortableStream(gate));
    const store = createVerifyStore();
    const h = renderHook(() => useVerify({ store }));
    let p!: Promise<void>;
    act(() => {
      p = h.result.current.verify("a draft whose stream hangs");
    });
    await waitFor(() => expect(h.result.current.loading).toBe(true));
    act(() => h.result.current.cancel());
    await act(() => p);
    expect(h.result.current.loading).toBe(false);
    // An honest idle state: the user stopped it; no verdict, no accusation.
    expect(h.result.current.response).toBeNull();
    expect(h.result.current.error).toBeNull();
  });

  it("a superseded check's cleanup never clears the successor's loading", async () => {
    // reset-then-reverify in one handler (resetVerifyStore's documented use):
    // check A is aborted while check B starts. A's unwinding finally must not
    // flip B's loading off — that would drop the Verifying chrome mid-check
    // and reopen the guard to a third concurrent check on the same store.
    const store = createVerifyStore();
    let releaseB!: () => void;
    const gateB = new Promise<void>((r) => (releaseB = r));
    let call = 0;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockDraftStream.mockImplementation(((_p: unknown, opts?: { signal?: AbortSignal }) => {
      call += 1;
      const gate = call === 1 ? new Promise<void>(() => {}) : gateB;
      return gatedAbortableStream(gate)(_p, opts);
    }) as never);
    const h = renderHook(() => useVerify({ store }));
    let pA!: Promise<void>;
    let pB!: Promise<void>;
    act(() => {
      pA = h.result.current.verify("check A");
    });
    await waitFor(() => expect(h.result.current.loading).toBe(true));
    act(() => resetVerifyStore(store)); // aborts A
    act(() => {
      pB = h.result.current.verify("check B");
    });
    await act(() => pA); // A fully unwinds while B is mid-stream
    expect(h.result.current.loading).toBe(true); // B's chrome must survive A's cleanup
    releaseB();
    await act(() => pB);
    expect(h.result.current.response).toEqual(RESPONSE);
    expect(h.result.current.loading).toBe(false);
  });

  it("an in-flight check survives a host unmount and lands on the next mount", async () => {
    // The 'still streaming' half of verdict survival: the rail click happens
    // MID-check. Kills the likeliest future regression — an abort-on-unmount
    // cleanup added to 'fix the leak' would silently kill every in-flight
    // lectern check on navigation.
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    mockDraftStream.mockImplementation(gatedAbortableStream(gate));
    const store = createVerifyStore();
    const first = renderHook(() => useVerify({ store }));
    let p!: Promise<void>;
    act(() => {
      p = first.result.current.verify("still streaming at nav time");
    });
    await waitFor(() => expect(first.result.current.loading).toBe(true));
    first.unmount(); // the rail click, mid-check
    release();
    await act(() => p);
    const second = renderHook(() => useVerify({ store }));
    expect(second.result.current.response).toEqual(RESPONSE);
    expect(second.result.current.loading).toBe(false);
    expect(mockDraftStream).toHaveBeenCalledTimes(1);
  });
});
