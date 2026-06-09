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

describe("CaseVerdictLine register (the sub-line must match the claim-level honesty)", () => {
  // The per-case sub-line renders on the LIVE streaming cards (the settled
  // view is the Workspace/Margin layout, which carries no case sub-lines), so
  // these tests drive a mid-stream engine whose cite_verdict has landed.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function liveEngineWithCase(caseVerdict: Record<string, unknown>): VerifyEngine {
    const skeleton = {
      claim_index: 0,
      claim_text: "The court so held in Doe.",
      verdict: "verified",
      citations: [],
      case_verdicts: [],
      unsupported_reason: null
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
    let s = initialStreamState();
    s = reduceStreamEvent(s, { type: "claims", claim_verdicts: [skeleton] });
    s = reduceStreamEvent(s, {
      type: "cite_verdict",
      claim_index: 0,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      case_verdict: { claim_index: 0, ok: true, verdicts: [caseVerdict] } as any
    });
    return {
      response: null,
      stream: s,
      loading: true,
      hydrating: false,
      error: null,
      sealedSeed: null,
      certAtSeed: null,
      hydratedDraft: null,
      verify: vi.fn()
    };
  }

  it("a bounded-corpus miss reads as coverage, never the accusatory 'Case not found'", () => {
    // The claim-level disposition for this card is the honest could-not-check;
    // the per-case sub-line beneath it must not contradict that with an
    // oxblood "Case not found" accusation the engine never made.
    const engine = liveEngineWithCase({
      citation: "999 F.3d 1",
      status: 404,
      exists: false,
      bounded_corpus: true
    });
    render(<VerifyResults engine={engine} draft="" />);
    expect(screen.queryByText(/Case not found/)).toBeNull();
    expect(screen.getByText(/Outside the offline corpus checked/)).toBeTruthy();
  });

  it("a caption mismatch is named for what it is, not shown as a clean 'Case found'", () => {
    // The citation number resolves, but to a different case than the draft
    // names. Rendering "Case found · <the wrong case>" in the quiet ink
    // register under a "Citation not found" claim badge is a mixed signal.
    const engine = liveEngineWithCase({
      citation: "100 U.S. 1",
      status: 200,
      exists: true,
      case_name: "Entirely Different Co. v. Other",
      caption_mismatch: true,
      bounded_corpus: true
    });
    render(<VerifyResults engine={engine} draft="" />);
    expect(screen.queryByText(/·\s*Case found/)).toBeNull();
    expect(screen.getByText(/Resolves to a different case/)).toBeTruthy();
  });
});

describe("VerifyResults command spine (cachet:command)", () => {
  it("opens the certification exhibit on the export command", async () => {
    render(<VerifyResults engine={engineWith([noRecordClaim])} draft="" />);
    fireEvent(window, new CustomEvent("cachet:command", { detail: { id: "export" } }));
    expect(await screen.findByRole("dialog", { name: "Verification certification" })).toBeTruthy();
  });

  it("opens the exhibit on the seal command but never sets the seal itself", async () => {
    // Sealing is the human's attestation. A palette verb may carry the lawyer
    // to the seal; it must never press it for them.
    render(<VerifyResults engine={engineWith([noRecordClaim])} draft="" />);
    fireEvent(window, new CustomEvent("cachet:command", { detail: { id: "seal" } }));
    expect(await screen.findByRole("dialog", { name: "Verification certification" })).toBeTruthy();
    const sealButton = screen.getByRole("button", { name: "Set the seal" });
    expect((sealButton as HTMLButtonElement).disabled).toBe(false);
  });

  it("opens nothing when there is no settled verdict to certify", () => {
    const engine = { ...engineWith([noRecordClaim]), response: null };
    render(<VerifyResults engine={engine} draft="" />);
    fireEvent(window, new CustomEvent("cachet:command", { detail: { id: "export" } }));
    expect(screen.queryByRole("dialog", { name: "Verification certification" })).toBeNull();
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
