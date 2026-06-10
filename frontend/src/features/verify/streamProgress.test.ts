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
