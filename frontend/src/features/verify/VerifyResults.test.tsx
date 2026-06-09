import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VerifyResults } from "./VerifyResults";
import { initialStreamState, reduceStreamEvent } from "./streamProgress";
import type { VerifyEngine } from "./useVerify";

// VerifyResults reaches the briefs API only on Save/Seal (not exercised here);
// mock the module so importing it never touches the real client.
vi.mock("@/services/api/endpoints", () => ({
  briefs: { get: vi.fn(), save: vi.fn(), list: vi.fn(), remove: vi.fn() },
  verify: { draft: vi.fn(), draftStream: vi.fn() },
  documents: { list: vi.fn() }
}));

afterEach(() => vi.clearAllMocks());

const CTA = "Open the Vault to load it";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function engineWith(claimVerdicts: any[]): VerifyEngine {
  return {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    response: {
      draft_text: claimVerdicts.map((c) => c.claim_text).join(" "),
      claim_verdicts: claimVerdicts,
      summary: { total: claimVerdicts.length, verified: 0, unsupported: 0, unknown: claimVerdicts.length },
      latency_ms: 1,
      model: "claude-sonnet-4-6",
      ok: true,
      error: null,
      provider: "claude",
      quote_results: [],
      unplaced: []
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any,
    stream: initialStreamState(),
    loading: false,
    hydrating: false,
    error: null,
    sealedSeed: null,
    certAtSeed: null,
    hydratedDraft: null,
    verify: vi.fn()
  };
}

// verdict "unknown" with no anchors -> could_not_check, and resolvable: the check
// could not run for want of a record. This is the actionable refusal.
const noRecordClaim = {
  claim_index: 0,
  claim_text: "The agreement caps total liability at $250,000.",
  verdict: "unknown",
  citations: [],
  case_verdicts: [],
  placement: { placed: true, method: "exact", char_start: 0, char_end: 10 }
};

// verdict "verified" but the cited case is ambiguous (status 300) -> also
// could_not_check, but NOT resolvable by loading a record. The CTA must not show.
const ambiguousCiteClaim = {
  claim_index: 0,
  claim_text: "The court so held in Smith.",
  verdict: "verified",
  citations: [],
  case_verdicts: [
    { claim_index: 0, ok: true, verdicts: [{ citation: "1 U.S. 1", status: 300, exists: false }] }
  ],
  placement: { placed: true, method: "exact", char_start: 0, char_end: 10 }
};

describe("VerifyResults mid-stream error (invariant #6)", () => {
  // A live stream that errored after one of two cite checks landed. The
  // skeleton cards carry verdict "verified" with no case verdicts, so any
  // render path that releases the unchecked card shows "Supported" for a
  // claim whose cite check never ran.
  function erroredStreamEngine(): VerifyEngine {
    const skeleton = (claim_index: number) => ({
      claim_index,
      claim_text: `claim ${claim_index}`,
      verdict: "verified",
      citations: [],
      case_verdicts: [],
      unsupported_reason: null
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    }) as any;
    let s = initialStreamState();
    s = reduceStreamEvent(s, { type: "claims", claim_verdicts: [skeleton(0), skeleton(1)] });
    s = reduceStreamEvent(s, {
      type: "cite_verdict",
      claim_index: 0,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      case_verdict: { claim_index: 0, ok: true, verdicts: [] } as any
    });
    s = reduceStreamEvent(s, { type: "error", error: "the verification stream failed" });
    return {
      response: null,
      stream: s,
      loading: true,
      hydrating: false,
      error: "the verification stream failed",
      sealedSeed: null,
      certAtSeed: null,
      hydratedDraft: null,
      verify: vi.fn()
    };
  }

  it("never renders an unchecked claim as Supported once the stream has errored", () => {
    render(<VerifyResults engine={erroredStreamEngine()} draft="" />);
    expect(screen.queryByText("Supported")).toBeNull();
    expect(screen.getByText("the verification stream failed")).toBeTruthy();
  });

  it("drops the live skeleton list on error (the banner is the only verdict)", () => {
    render(<VerifyResults engine={erroredStreamEngine()} draft="" />);
    expect(screen.queryByText("claim 0")).toBeNull();
    expect(screen.queryByText("claim 1")).toBeNull();
  });
});

describe("VerifyResults refusal CTA (onResolve)", () => {
  it("offers the resolve action when a statement could not be checked for want of its record, and fires onResolve", () => {
    const onResolve = vi.fn();
    render(<VerifyResults engine={engineWith([noRecordClaim])} draft="" onResolve={onResolve} />);
    fireEvent.click(screen.getByText(CTA));
    expect(onResolve).toHaveBeenCalledTimes(1);
  });

  it("never renders the CTA when no onResolve is provided (Carrel has no Sources surface)", () => {
    render(<VerifyResults engine={engineWith([noRecordClaim])} draft="" />);
    expect(screen.queryByText(CTA)).toBeNull();
  });

  it("does not point an unresolvable refusal at Sources (ambiguous citation, not a missing record)", () => {
    const onResolve = vi.fn();
    render(<VerifyResults engine={engineWith([ambiguousCiteClaim])} draft="" onResolve={onResolve} />);
    // The summary still reports a could-not-verify, but loading a record would not
    // fix an ambiguous citation, so the honest surface offers no Sources CTA.
    expect(screen.queryByText(CTA)).toBeNull();
  });
});
