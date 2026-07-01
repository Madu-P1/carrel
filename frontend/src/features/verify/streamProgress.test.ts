/**
 * INVARIANT (T71 / SCOPE clause 9(f), locked verbatim):
 * For any verify stream that has not fully and successfully completed,
 * streamProgress.ts must report a status that a consumer cannot interpret as
 * 'supported'/settled — an incomplete stream is surfaced as pending,
 * in-flight, interrupted, or incomplete, and a claim whose supporting
 * evidence has not fully arrived is never classified as supported.
 * Completion is affirmative-only: 'supported' requires the stream to have
 * reached its documented done/complete terminal state, not merely 'not yet
 * errored'.
 */
import { describe, expect, it } from "vitest";

import type {
  VerifyCaseVerdictBatch,
  VerifyClaimVerdict,
  VerifyStreamEvent
} from "@/services/api/endpoints";

import {
  checkedProgress,
  initialStreamState,
  isCardChecking,
  reduceStreamEvent,
  type StreamPhase,
  type VerifyStreamState
} from "./streamProgress";

function card(claim_index: number): VerifyClaimVerdict {
  return {
    claim_index,
    claim_text: `claim ${claim_index}`,
    verdict: "verified",
    citations: [],
    case_verdicts: [],
    unsupported_reason: null
  } as VerifyClaimVerdict;
}

/** Minimal valid case-verdict batch: a non-legal claim that was checked and
 *  carried nothing to verify (ok, empty verdicts). */
function caseVerdict(claim_index: number): VerifyCaseVerdictBatch {
  return {
    claim_index,
    ok: true,
    verdicts: [],
    error_code: null,
    error_message: null
  } as VerifyCaseVerdictBatch;
}

function fold(events: VerifyStreamEvent[]): VerifyStreamState {
  return events.reduce(reduceStreamEvent, initialStreamState());
}

describe("streamProgress reducer", () => {
  it("starts idle and advances to extracting on progress", () => {
    const s = fold([{ type: "progress", phase: "extracting" }]);
    expect(s.phase).toBe("extracting");
    expect(s.cards).toEqual([]);
  });

  it("claims event installs the skeleton and enters checking", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] }
    ]);
    expect(s.phase).toBe("checking");
    expect(s.cards).toHaveLength(2);
  });

  it("cite_verdict marks a claim checked without mutating prior state", () => {
    const before = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] }
    ]);
    const after = reduceStreamEvent(before, {
      type: "cite_verdict",
      claim_index: 0,
      case_verdict: caseVerdict(0)
    });
    expect(after.checked.has(0)).toBe(true);
    // immutability: the prior state's set is untouched
    expect(before.checked.has(0)).toBe(false);
    expect(after).not.toBe(before);
  });

  it("result event settles to done and carries the payload", () => {
    const verify = {
      draft_text: "d",
      claim_verdicts: [],
      summary: { total: 0, verified: 0, unsupported: 0, unknown: 0 },
      latency_ms: 1,
      model: "m",
      ok: true,
      error: null,
      provider: "claude"
    } as unknown as import("@/services/api/endpoints").VerifyResponse;
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) },
      { type: "result", verify }
    ]);
    expect(s.phase).toBe("done");
    expect(s.result).toBe(verify);
  });

  it("error event settles to error and records the message", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "error", error: "courtlistener exploded" }
    ]);
    expect(s.phase).toBe("error");
    expect(s.error).toBe("courtlistener exploded");
  });
});

describe("isCardChecking — invariant #6 (no card reads as a pass before its cite lands)", () => {
  it("an un-checked card is 'checking' during the checking phase", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] }
    ]);
    expect(isCardChecking(s, card(0))).toBe(true);
    expect(isCardChecking(s, card(1))).toBe(true);
  });

  it("a card stops 'checking' once its cite_verdict arrives", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) }
    ]);
    expect(isCardChecking(s, card(0))).toBe(false);
    expect(isCardChecking(s, card(1))).toBe(true);
  });

  it("DROPPED STREAM: a card that never got its cite_verdict is still 'checking' (never a pass)", () => {
    // stream dies after claims + one cite_verdict; no result event ever arrives.
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) }
    ]);
    // claim 1 never resolved: the live view holds it as checking, NOT supported.
    expect(s.phase).toBe("checking");
    expect(isCardChecking(s, card(1))).toBe(true);
    // and there is no settled result to read a pass from.
    expect(s.result).toBeNull();
  });

  it("MID-STREAM ERROR: an un-checked card is never released to its skeleton disposition", () => {
    // The skeleton card carries verdict "verified" with no case verdicts, so
    // releasing it on error would render "Supported" for a claim whose cite
    // check never ran — invariant #6's exact forbidden render.
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) },
      { type: "error", error: "courtlistener exploded" }
    ]);
    expect(s.phase).toBe("error");
    expect(isCardChecking(s, card(1))).toBe(true);
    // The card whose verdict DID land before the failure may settle.
    expect(isCardChecking(s, card(0))).toBe(false);
  });

  it("POSITIVE CONTROL: a fully-received stream releases a cleanly-checked card to its supported disposition", () => {
    // Proves the suite isn't trivially failing every path: a real, complete
    // fold (progress -> claims -> cite_verdict -> result) DOES release the
    // checked card and DOES carry its supported verdict through.
    const verify = {
      draft_text: "d",
      claim_verdicts: [],
      summary: { total: 1, verified: 1, unsupported: 0, unknown: 0 },
      latency_ms: 1,
      model: "m",
      ok: true,
      error: null,
      provider: "claude"
    } as unknown as import("@/services/api/endpoints").VerifyResponse;
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) },
      { type: "result", verify }
    ]);
    expect(s.phase).toBe("done");
    expect(s.error).toBeNull();
    expect(isCardChecking(s, card(0))).toBe(false);
    const settledCard = s.cards.find((c) => c.claim_index === 0);
    expect(settledCard?.verdict).toBe("verified");
    expect(settledCard?.case_verdicts).toEqual([caseVerdict(0)]);
  });

  it("a card with no claim_index is held as checking, never released by guesswork", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0)] }
    ]);
    const indexless = { ...card(0), claim_index: undefined } as unknown as VerifyClaimVerdict;
    expect(isCardChecking(s, indexless)).toBe(true);
  });

  it("once done, isCardChecking is false (the settled result governs)", () => {
    const s: VerifyStreamState = {
      phase: "done",
      cards: [card(0)],
      checked: new Set<number>(),
      result: null,
      quotes: [],
      error: null
    };
    expect(isCardChecking(s, card(0))).toBe(false);
  });
});

describe("isCardChecking is fail-closed by allow-list, not deny-list", () => {
  // The reducer never produces a populated `cards` array during "idle" or
  // "extracting" in practice (defense in depth, not the only guarantee): a
  // deny-list of "checking"/"error" would silently release a card on any
  // OTHER phase, including these and any phase this union gains later. Only
  // "done" may release a card; everything else must fall through to the
  // checked-set test and default to checking.

  it("a directly-constructed 'idle' state with a populated card still holds it as checking", () => {
    const s: VerifyStreamState = {
      phase: "idle",
      cards: [card(0)],
      checked: new Set<number>(),
      result: null,
      quotes: [],
      error: null
    };
    expect(isCardChecking(s, card(0))).toBe(true);
  });

  it("a directly-constructed 'extracting' state with a populated card still holds it as checking", () => {
    const s: VerifyStreamState = {
      phase: "extracting",
      cards: [card(0)],
      checked: new Set<number>(),
      result: null,
      quotes: [],
      error: null
    };
    expect(isCardChecking(s, card(0))).toBe(true);
  });

  it("an unrecognized/future phase value still holds a card as checking (allow-list default)", () => {
    const s = {
      phase: "reconnecting",
      cards: [card(0)],
      checked: new Set<number>(),
      result: null,
      quotes: [],
      error: null
    } as unknown as VerifyStreamState;
    expect(isCardChecking(s, card(0))).toBe(true);
  });
});

describe("checkedProgress", () => {
  it("counts checked over total skeleton cards", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1), card(2)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) },
      { type: "cite_verdict", claim_index: 2, case_verdict: caseVerdict(2) }
    ]);
    expect(checkedProgress(s)).toEqual({ checked: 2, total: 3 });
  });
});

describe("T71: dropped/aborted/empty/unterminated streams never read as supported, verified, or complete", () => {
  // "done" is the only StreamPhase the type's own JSDoc calls terminal/settled
  // (initialStreamState/reduceStreamEvent never produce "claims" — only
  // "idle" | "extracting" | "checking" | "done" | "error" occur in practice).
  // Anything outside this set is, by construction, not a value the verify UI
  // may treat as a settled pass.
  const COMPLETE_PHASES = new Set<StreamPhase>(["done"]);

  it("(a) a stream that ends before any terminal/done event surfaces an indeterminate state, never a pass", () => {
    // claim 1's cite_verdict never lands; no "result", no "error" follows.
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) }
    ]);
    expect(COMPLETE_PHASES.has(s.phase)).toBe(false);
    expect(s.result).toBeNull();
    expect(isCardChecking(s, card(1))).toBe(true);
  });

  it("(b) an aborted stream (cut off right after the skeleton, before any cite check lands) never releases a card to a pass", () => {
    // Mirrors useVerify.ts: AbortController.abort() only stops the for-await
    // loop — it never feeds a synthetic event into the reducer. The last
    // folded state is exactly what reduceStreamEvent last produced, and the
    // abort itself must not promote it to done/supported.
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] }
    ]);
    expect(COMPLETE_PHASES.has(s.phase)).toBe(false);
    expect(s.result).toBeNull();
    expect(isCardChecking(s, card(0))).toBe(true);
    expect(isCardChecking(s, card(1))).toBe(true);
  });

  it("(c) an empty stream (zero events) is the idle/indeterminate state, never a pass", () => {
    const s = fold([]);
    expect(s).toEqual(initialStreamState());
    expect(COMPLETE_PHASES.has(s.phase)).toBe(false);
    expect(s.result).toBeNull();
    expect(s.cards).toEqual([]);
  });

  it("(d) every card individually checked but the terminal result event never arrives: the brief-level state still reads as incomplete, never 'done'", () => {
    // checkedProgress can report 100% checked while phase/result correctly
    // withhold "done" — per-card checked-count must never be conflated with
    // a settled, complete verification.
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) },
      { type: "cite_verdict", claim_index: 1, case_verdict: caseVerdict(1) }
    ]);
    expect(checkedProgress(s)).toEqual({ checked: 2, total: 2 });
    expect(COMPLETE_PHASES.has(s.phase)).toBe(false);
    expect(s.result).toBeNull();
  });
});

describe("quote_batch + result quote reconciliation (Cachet PR4)", () => {
  it("quote_batch installs the brief-level quote results", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0)] },
      {
        type: "quote_batch",
        quotes: [
          { index: 0, quote: "altered run", status: "altered" },
          { index: 1, quote: "ok run", status: "verbatim" }
        ]
      }
    ]);
    expect(s.quotes).toHaveLength(2);
    expect(s.quotes[0].status).toBe("altered");
  });

  it("result reconciles quotes from the payload when no quote_batch arrived", () => {
    const verify = {
      draft_text: "d",
      claim_verdicts: [],
      summary: { total: 0, verified: 0, unsupported: 0, unknown: 0 },
      latency_ms: 1,
      model: "m",
      ok: true,
      error: null,
      provider: "claude",
      quote_results: [{ index: 0, quote: "x", status: "could_not_check" }]
    } as unknown as import("@/services/api/endpoints").VerifyResponse;
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [] },
      { type: "result", verify }
    ]);
    expect(s.quotes).toHaveLength(1);
    expect(s.quotes[0].status).toBe("could_not_check");
  });
});

describe("T71 SCOPE clause 9(f) — the five interruption categories, one assertion each", () => {
  const SETTLED: StreamPhase = "done";

  it("(1) DROPPED MID-WAY: chunks arrive then simply stop, no terminal done marker -> not settled", () => {
    // claims + one cite_verdict land, then the stream just stops (no result, no error).
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) }
    ]);
    expect(s.phase).not.toBe(SETTLED);
  });

  it("(2) ABORTED: an AbortController-style termination stops event delivery before completion -> not settled", () => {
    // Per useVerify.ts, AbortController.abort() only stops the for-await loop
    // consuming draftStream(); it never synthesizes an event into
    // reduceStreamEvent. The honest unit-level representation of an abort is
    // therefore identical to "events stop arriving": the fold below is exactly
    // the last state reduceStreamEvent produced before the loop was cut off,
    // and that must not read as settled/supported.
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] }
    ]);
    expect(s.phase).not.toBe(SETTLED);
  });

  it("(3) NETWORK ERROR MID-STREAM: an error event after partial data arrived -> not settled", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0), card(1)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) },
      { type: "error", error: "network error mid-stream" }
    ]);
    expect(s.phase).not.toBe(SETTLED);
  });

  it("(4) STILL IN-FLIGHT / PENDING: the stream is open with progress emitted but no terminal event yet -> not settled", () => {
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0)] }
    ]);
    expect(s.phase).not.toBe(SETTLED);
  });

  it("(5) HAPPY PATH: a fully-completed stream DOES reach the settled/complete state", () => {
    const verify = {
      draft_text: "d",
      claim_verdicts: [],
      summary: { total: 1, verified: 1, unsupported: 0, unknown: 0 },
      latency_ms: 1,
      model: "m",
      ok: true,
      error: null,
      provider: "claude"
    } as unknown as import("@/services/api/endpoints").VerifyResponse;
    const s = fold([
      { type: "progress", phase: "extracting" },
      { type: "claims", claim_verdicts: [card(0)] },
      { type: "cite_verdict", claim_index: 0, case_verdict: caseVerdict(0) },
      { type: "result", verify }
    ]);
    expect(s.phase).toBe(SETTLED);
  });
});
