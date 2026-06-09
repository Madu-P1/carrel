import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VerifyResults, verdictSummaryRegister } from "./VerifyResults";
import type { ClaimDisposition } from "./claimDisposition";
import { initialStreamState } from "./streamProgress";
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

// The summary register (D1: could-not-check is not an alarm). These five cases
// were pinned in VerifyView.test.tsx before the headline moved into
// VerifyResults; they live on here against the exported pure function so a
// regression that folds honest refusals into the oxblood alarm (alert fatigue,
// main #154) or mutes the fabrication alarm cannot pass the suite.
describe("verdictSummaryRegister", () => {
  const d = (kind: ClaimDisposition["kind"]): ClaimDisposition => ({
    kind,
    tier: kind === "supported" ? "pass" : kind === "assessed" ? "assistive" : "flag",
    label: kind,
    detail: ""
  });

  it("does NOT raise the alarm when every claim is only could_not_check", () => {
    const r = verdictSummaryRegister([d("could_not_check"), d("could_not_check")]);
    expect(r.flagged).toBe(0);
    expect(r.headline).toBe("2 of 2 statements could not be verified against your sources.");
  });

  it("citation_not_found raises the alarm headline", () => {
    const r = verdictSummaryRegister([d("citation_not_found"), d("supported")]);
    expect(r.flagged).toBe(1);
    expect(r.headline).toBe("1 of 2 statements need your review.");
  });

  it("claim_unsupported raises the alarm headline", () => {
    const r = verdictSummaryRegister([d("claim_unsupported")]);
    expect(r.flagged).toBe(1);
    expect(r.headline).toBe("1 of 1 statements need your review.");
  });

  it("proposition_unsupported and assessed do not raise the alarm", () => {
    const r = verdictSummaryRegister([d("proposition_unsupported"), d("assessed")]);
    expect(r.flagged).toBe(0);
    expect(r.headline).toBe("2 of 2 statements could not be verified against your sources.");
  });

  it("all supported affirms, and the alarm counts only the flagged set", () => {
    expect(verdictSummaryRegister([d("supported"), d("supported")]).headline).toBe(
      "All 2 statements are supported by the sources you provided."
    );
    const mixed = verdictSummaryRegister([
      d("citation_not_found"),
      d("could_not_check"),
      d("could_not_check"),
      d("supported")
    ]);
    expect(mixed.flagged).toBe(1);
    expect(mixed.headline).toBe("1 of 4 statements need your review.");
  });
});
