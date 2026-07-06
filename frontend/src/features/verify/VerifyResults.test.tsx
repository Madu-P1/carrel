import { fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { caseLineRegister } from "./ExaminationDrawer";
import {
  VerifyResults,
  crossDocumentStatusLabel,
  structuralStatusLabel,
  verdictSummaryRegister
} from "./VerifyResults";
import type { ClaimDisposition } from "./claimDisposition";
import { initialStreamState, reduceStreamEvent } from "./streamProgress";
import type { VerifyEngine } from "./useVerify";
import styles from "./VerifyView.module.css";

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
    streamInterrupted: false,
    verify: vi.fn(),
    markSealed: vi.fn(),
    cancel: vi.fn()
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

describe("VerifyResults — SI-5 structure check panel", () => {
  const flaggedFinding = {
    kind: "defined_term_unused",
    disposition: "flagged",
    detail: 'The term "Indemnified Party" is defined but never used in this document.',
    span: "Indemnified Party",
    start: 0,
    end: 1,
    target: "Indemnified Party"
  };
  const reviewFinding = {
    kind: "dangling_cross_reference",
    disposition: "could_not_check",
    detail: "Section 12.3 is referenced but was not found among this document's declared sections.",
    span: "Section 12.3",
    start: 2,
    end: 3,
    target: "12.3"
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function engineWithStructural(findings: any[]): VerifyEngine {
    const engine = engineWith([noRecordClaim]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (engine.response as any).structural_findings = findings;
    return engine;
  }

  it("renders a flagged finding in the oxblood register and a review finding quietly", () => {
    render(<VerifyResults engine={engineWithStructural([flaggedFinding, reviewFinding])} draft="" />);
    expect(screen.getByText("Structure check")).toBeTruthy();
    const flagged = screen.getByText("Defined term unused").closest("li");
    expect(flagged?.className).toContain(styles.structureFlag);
    const review = screen.getByText("Reference unverified").closest("li");
    expect(review?.className).toContain(styles.structureReview);
    expect(review?.className).not.toContain(styles.structureFlag);
  });

  it("renders no panel when there are no structural findings", () => {
    render(<VerifyResults engine={engineWithStructural([])} draft="" />);
    expect(screen.queryByText("Structure check")).toBeNull();
  });

  it("labels each finding kind", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(structuralStatusLabel(flaggedFinding as any)).toBe("Defined term unused");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(structuralStatusLabel(reviewFinding as any)).toBe("Reference unverified");
    expect(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      structuralStatusLabel({ kind: "internal_contradiction", disposition: "could_not_check" } as any)
    ).toBe("Possible inconsistency");
  });

  it("falls back to the disposition for an unknown kind", () => {
    // A future engine kind must still get a sane label, not crash or blank.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(structuralStatusLabel({ kind: "future_kind", disposition: "flagged" } as any)).toBe(
      "Flagged"
    );
    expect(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      structuralStatusLabel({ kind: "future_kind", disposition: "could_not_check" } as any)
    ).toBe("Could not check");
  });
});

describe("VerifyResults — cross-document conflict panel", () => {
  const conflictFinding = {
    kind: "cross_document_conflict",
    disposition: "flagged",
    label: "Purchase Price",
    dimension: "money_usd",
    detail:
      'The term "Purchase Price" is bound to conflicting values: agreement.pdf states $5,000; amendment.pdf states $6,000.',
    figures: [
      { document: "agreement.pdf", surface: "$5,000", normalized: "5000", start: 0, end: 6, snippet: "…" },
      { document: "amendment.pdf", surface: "$6,000", normalized: "6000", start: 0, end: 6, snippet: "…" }
    ]
  };
  const refuseFinding = {
    kind: "cross_document_unresolved",
    disposition: "could_not_check",
    label: "Fee",
    dimension: "money_eur+money_usd",
    detail: 'The term "Fee" carries values in different currencies that cannot be compared.',
    figures: [
      { document: "a.pdf", surface: "€40,000", normalized: "40000", start: 0, end: 7, snippet: "…" },
      { document: "b.pdf", surface: "$35,000", normalized: "35000", start: 0, end: 7, snippet: "…" }
    ]
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function engineWithCrossDoc(findings: any[]): VerifyEngine {
    const engine = engineWith([noRecordClaim]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (engine.response as any).cross_document_findings = findings;
    return engine;
  }

  it("renders a conflict in the oxblood register and a refusal quietly, naming both documents", () => {
    render(<VerifyResults engine={engineWithCrossDoc([conflictFinding, refuseFinding])} draft="" />);
    expect(screen.getByText("Cross-document check")).toBeTruthy();
    const flagged = screen.getByText("Conflicting values").closest("li");
    expect(flagged?.className).toContain(styles.crossDocFlag);
    const review = screen.getByText("Not comparable").closest("li");
    expect(review?.className).toContain(styles.crossDocReview);
    expect(review?.className).not.toContain(styles.crossDocFlag);
    // The figure sub-list names which document said which surface.
    expect(screen.getByText("agreement.pdf")).toBeTruthy();
    expect(screen.getByText("$5,000")).toBeTruthy();
    expect(screen.getByText("amendment.pdf")).toBeTruthy();
  });

  it("renders no panel when there are no cross-document findings", () => {
    render(<VerifyResults engine={engineWithCrossDoc([])} draft="" />);
    expect(screen.queryByText("Cross-document check")).toBeNull();
  });

  it("labels a conflict and a refusal", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(crossDocumentStatusLabel(conflictFinding as any)).toBe("Conflicting values");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(crossDocumentStatusLabel(refuseFinding as any)).toBe("Not comparable");
  });
});

describe("VerifyResults — acceptance and refusal both visible on a segmented draft", () => {
  // The demo failure: a slide pasted as one blob verified as ONE claim, so the
  // surface only ever showed the refusal and never a supported statement beside
  // it. With the draft segmented per bullet (services.legal.sentences), the same
  // case study is three statements: two altered figures flag, the untampered
  // result line is supported. This locks the council ruling — the refusal lands
  // because acceptance is visible next to it, as a count, no green badge.
  function segmentedEngine(): VerifyEngine {
    const claims = [
      {
        claim_index: 0,
        claim_text: "For Covered Group, 6% (60 billion for 6%= 1,2 billion) are extra margins.",
        verdict: "unsupported",
        citations: [],
        case_verdicts: [],
        unsupported_reason: "The summary states 60 billion; the loaded source states 20 billion.",
        placement: null
      },
      {
        claim_index: 1,
        claim_text: "Allocation key: turnover (10% Italy, 20% France, 10% Spain, 10% Germany).",
        verdict: "unsupported",
        citations: [],
        case_verdicts: [],
        unsupported_reason: "The summary states 20% for France; the loaded source states 10%.",
        placement: null
      },
      {
        claim_index: 2,
        claim_text: "Result: 30 mln Amount A taxable in Italy, France, Spain, Germany.",
        verdict: "verified",
        citations: [],
        case_verdicts: [],
        unsupported_reason: "Present in your sources, in the allocation result line.",
        placement: null
      }
    ];
    const base = engineWith(claims);
    return {
      ...base,
      response: base.response
        ? { ...base.response, coverage: { statements: 3, treated: 3, untreated: 0 } }
        : null
    };
  }

  it("shows the flagged count AND the supported count side by side", () => {
    render(<VerifyResults engine={segmentedEngine()} draft="" />);
    // Refusal: the problem headline counts only the two altered figures.
    expect(screen.getByText("2 of 3 statements need your review.")).toBeTruthy();
    // Acceptance, as a count, beside the refusal — the whole point.
    const summary = screen.getByRole("status");
    expect(within(summary).getByText("Supported")).toBeTruthy();
    expect(within(summary).getByText("Unsupported")).toBeTruthy();
    // No "All N supported" green headline, no percentage: a finding, not a score.
    expect(screen.queryByText(/All \d+ statements are supported/)).toBeNull();
  });
});

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
      streamInterrupted: false,
      verify: vi.fn(),
      markSealed: vi.fn(),
      cancel: vi.fn()
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

  it("announces the error banner assertively (role=alert) so a reviewer never misses a failure", () => {
    render(<VerifyResults engine={erroredStreamEngine()} draft="" />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("the verification stream failed");
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
      streamInterrupted: false,
      verify: vi.fn(),
      markSealed: vi.fn(),
      cancel: vi.fn()
    };
  }

  it("a bounded-corpus miss reads as coverage, never the accusatory 'Case not found'", () => {
    // The per-case register moved to the Examination drawer (handoff §6): the
    // live rail cards carry the disposition only, and the drawer names each
    // cited case. The register itself is unchanged: a bounded-corpus miss is a
    // coverage statement, never an oxblood accusation the engine never made.
    expect(
      caseLineRegister({ status: 404, exists: false, bounded_corpus: true })
    ).toEqual({ label: "Outside the offline corpus checked", kind: "unknown" });
  });

  it("a caption mismatch is named for what it is, not shown as a clean 'Case found'", () => {
    // The citation number resolves, but to a different case than the draft
    // names. Naming it "Case found · <the wrong case>" would be a mixed
    // signal; the drawer register must call the mismatch by name.
    expect(
      caseLineRegister({ status: 200, exists: true, caption_mismatch: true, bounded_corpus: true })
    ).toEqual({ label: "Resolves to a different case", kind: "flag" });
    const engine = liveEngineWithCase({
      citation: "100 U.S. 1",
      status: 200,
      exists: true,
      case_name: "Entirely Different Co. v. Other",
      caption_mismatch: true,
      bounded_corpus: true
    });
    render(<VerifyResults engine={engine} draft="" />);
    // The live rail card never names the wrong case as found; the full
    // per-case line lives in the drawer (asserted via the register above).
    expect(screen.queryByText(/·\s*Case found/)).toBeNull();
  });
});

describe("VerifyResults streaming announcement (screen-reader honesty)", () => {
  it("announces the start of verification once, with fixed text", () => {
    // The visual working indicator is aria-hidden by design (per-cite progress
    // would spam a screen reader), but silence until the settled summary means
    // a non-sighted user cannot tell a check is running at all. One status
    // region with CONSTANT text announces the start and never re-fires.
    const engine: VerifyEngine = {
      response: null,
      stream: initialStreamState(),
      loading: true,
      hydrating: false,
      error: null,
      sealedSeed: null,
      certAtSeed: null,
      hydratedDraft: null,
      streamInterrupted: false,
      verify: vi.fn(),
      markSealed: vi.fn(),
      cancel: vi.fn()
    };
    render(<VerifyResults engine={engine} draft="" />);
    expect(
      screen.getByText("Verifying the draft against your sources.")
    ).toBeTruthy();
  });
});

describe("VerifyResults summary counts", () => {
  it("an assessed claim appears in the stat row (counts always sum to the total)", () => {
    const assessedClaim = {
      claim_index: 0,
      claim_text: "An anchor-free claim a local model assessed.",
      verdict: "unknown",
      assessed_confidence: 0.93,
      assessed_label: "support",
      citations: [],
      case_verdicts: [],
      placement: { placed: true, method: "exact", char_start: 0, char_end: 10 }
    };
    render(<VerifyResults engine={engineWith([assessedClaim])} draft="" />);
    // Scoped to the summary's own status region: the margin note carries the
    // same label, and matching it would pass vacuously.
    const summary = screen.getByRole("status");
    expect(within(summary).getByText("Assessed (local model)")).toBeTruthy();
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

describe("VerifyResults stale-draft register", () => {
  // The verdict persists across navigation and the composer stays editable,
  // so an edited draft above a confident summary the engine never saw is the
  // product's worst failure. The stale notice is the counterweight.
  it("a draft edited after the check shows the stale notice", () => {
    render(
      <VerifyResults
        engine={engineWith([noRecordClaim])}
        draft="Entirely new text the engine never saw."
      />
    );
    expect(screen.getByText(/The draft has changed since this check/)).toBeTruthy();
  });

  it("offers to verify the current draft again, wired to the CURRENT text", () => {
    const engine = engineWith([noRecordClaim]);
    render(<VerifyResults engine={engine} draft="Entirely new text." />);
    fireEvent.click(screen.getByText("Verify the draft again"));
    expect(engine.verify).toHaveBeenCalledWith("Entirely new text.");
  });

  it("no notice when the draft matches the checked text (modulo whitespace)", () => {
    const engine = engineWith([noRecordClaim]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const checked = (engine.response as any).draft_text as string;
    render(<VerifyResults engine={engine} draft={`${checked}\n`} />);
    expect(screen.queryByText(/has changed since this check/)).toBeNull();
  });

  it("no notice on an empty composer (the brief-hydration seeding window)", () => {
    render(<VerifyResults engine={engineWith([noRecordClaim])} draft="" />);
    expect(screen.queryByText(/has changed since this check/)).toBeNull();
  });
});

describe("VerifyResults honesty backstops (O5, O7)", () => {
  it("O7: a non-provider payload error surfaces an honest failure banner, not a blank surface", () => {
    const base = engineWith([noRecordClaim]);
    const engine: VerifyEngine = {
      ...base,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      response: { ...(base.response as any), error: "weak_coverage" } as any
    };
    const { container } = render(<VerifyResults engine={engine} draft="x" />);
    const banner = container.querySelector('[data-response-error="weak_coverage"]');
    expect(banner).not.toBeNull();
    expect(banner?.getAttribute("role")).toBe("alert");
    expect(banner?.textContent).toMatch(/nothing here is confirmed/i);
  });

  it("O5: a malformed claim card is dropped safely, but its loss is stated, not silent", () => {
    const base = engineWith([noRecordClaim]);
    const engine: VerifyEngine = {
      ...base,
      // one valid card + one malformed (null) card the render must not crash on
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      response: { ...(base.response as any), claim_verdicts: [noRecordClaim, null] } as any
    };
    const { container } = render(<VerifyResults engine={engine} draft="x" />);
    const note = container.querySelector("[data-dropped-claims]");
    expect(note).not.toBeNull();
    expect(note?.getAttribute("data-dropped-claims")).toBe("1");
  });
});

describe("VerifyResults seal records the pair on the engine", () => {
  it("sealing calls engine.markSealed with the cert fingerprint AND its timestamp", async () => {
    // The mutation review proved this wiring was a surviving mutant: deleting
    // the markSealed call failed zero tests while being the only guard against
    // the seal silently downgrading after a remount. This pins it, including
    // the timestamp half of the pair (a reopened exhibit must re-render the
    // ORIGINAL seal date, never mint a fresh one).
    const engine = engineWith([noRecordClaim]);
    render(<VerifyResults engine={engine} draft="" />);
    fireEvent.click(screen.getByText("Open exhibit"));
    fireEvent.click(await screen.findByRole("button", { name: "Set the seal" }));
    expect(engine.markSealed).toHaveBeenCalledTimes(1);
    const [fingerprint, generatedAtISO] = vi.mocked(engine.markSealed).mock.calls[0];
    expect(fingerprint).toMatch(/^[0-9a-f]{64}$/);
    expect(typeof generatedAtISO).toBe("string");
    expect(generatedAtISO.length).toBeGreaterThan(0);
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

// The zero-finding state. A verify that produces no cards (a clean prose draft
// where every sentence is anchor-free) used to render as silent draft read-back:
// no summary, no scope line, nothing. To the user that reads as "the tool did
// nothing." The deterministic engine still reports HOW MUCH it examined via the
// `coverage` block, so we surface an honest, non-alarm coverage statement rather
// than silence. This is the documented "anchor-free prose gets a COVERAGE
// statement" decision; it is NOT the per-claim "needs review" alert fatigue that
// main #154/#155 removed.
describe("VerifyResults empty-coverage (anchor-free prose is an honest result, not silence)", () => {
  function engineNoFindings(
    coverage: { statements: number; treated: number; untreated: number } | null
  ): VerifyEngine {
    const e = engineWith([]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e.response as any).coverage = coverage;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e.response as any).provider = "deterministic";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e.response as any).draft_text = "Our team will deliver excellent results for every client.";
    return e;
  }

  it("anchor-free prose renders an honest coverage statement instead of silence", () => {
    render(<VerifyResults engine={engineNoFindings({ statements: 2, treated: 0, untreated: 2 })} draft="" />);
    expect(screen.getByText(/no checkable claims/i)).toBeTruthy();
    expect(screen.getByText(/read 2 statements/i)).toBeTruthy();
    expect(screen.getByText(/nothing to verify against your sources/i)).toBeTruthy();
  });

  it("the coverage statement is a quiet status, never the oxblood alarm", () => {
    const { container } = render(
      <VerifyResults engine={engineNoFindings({ statements: 1, treated: 0, untreated: 1 })} draft="" />
    );
    const panel = container.querySelector("[data-empty-coverage]");
    expect(panel).toBeTruthy();
    // Must be a polite status region (announced once), never the problem headline.
    expect(panel?.getAttribute("role")).toBe("status");
    expect(container.querySelector("[data-empty-coverage] [class*='Problem']")).toBeNull();
  });

  it("singular copy when exactly one statement was read", () => {
    render(<VerifyResults engine={engineNoFindings({ statements: 1, treated: 0, untreated: 1 })} draft="" />);
    expect(screen.getByText(/read 1 statement\b/i)).toBeTruthy();
  });

  it("does not show the coverage statement when there ARE findings", () => {
    render(<VerifyResults engine={engineWith([noRecordClaim])} draft="" />);
    expect(screen.queryByText(/no checkable claims/i)).toBeNull();
  });

  it("shows the generic empty-claims state, not a fabricated statement count, when the engine reported no coverage block (LLM path)", () => {
    // No coverage block means no honest count to quote — but zero claims must
    // still say so explicitly. A bare blank container here would read as a
    // silent all-clear to a lawyer watching the run.
    render(<VerifyResults engine={engineNoFindings(null)} draft="" />);
    expect(screen.getByText(/no checkable claims found in this document/i)).toBeTruthy();
    expect(screen.queryByText(/cachet read/i)).toBeNull();
  });

  it("does not show the coverage statement on an engine error", () => {
    const e = engineNoFindings({ statements: 2, treated: 0, untreated: 2 });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e as any).error = "Verification did not finish.";
    render(<VerifyResults engine={e} draft="" />);
    expect(screen.queryByText(/no checkable claims/i)).toBeNull();
    // Both the banner's ruling label and the engine message carry the failure;
    // assert on the alert region as a whole rather than a unique text node.
    expect(screen.getByRole("alert").textContent).toMatch(/did not finish/i);
  });
});

// The failed check's recovery: the banner names one verb-led action and re-runs
// the same draft through the engine. Voice rule: an error names its concrete
// recovery, never a bare failure line the user must interpret.
describe("VerifyResults error recovery action", () => {
  function erroredEngine(): VerifyEngine {
    return {
      ...engineWith([]),
      response: null,
      error: "Backend offline"
    };
  }

  it("offers Run the check again when a draft is present, and re-verifies it", () => {
    const engine = erroredEngine();
    render(<VerifyResults engine={engine} draft="The fund totals $360 million." />);
    const retry = screen.getByRole("button", { name: /run the check again/i });
    fireEvent.click(retry);
    expect(engine.verify).toHaveBeenCalledWith("The fund totals $360 million.");
  });

  it("withholds the recovery action when there is no draft to re-run", () => {
    render(<VerifyResults engine={erroredEngine()} draft="   " />);
    expect(screen.queryByRole("button", { name: /run the check again/i })).toBeNull();
  });

  it("withholds the recovery action while a re-run is already in flight", () => {
    const engine = { ...erroredEngine(), loading: true };
    render(<VerifyResults engine={engine} draft="The fund totals $360 million." />);
    expect(screen.queryByRole("button", { name: /run the check again/i })).toBeNull();
  });
});

// The quote autopsy: an altered quote rendered with its genuine words in ink and
// its fabricated words struck through in oxblood. The render is driven entirely
// by the engine's per-phrase `segments`, so the strike can never disagree with
// the verdict, can never over-accuse a genuine word, and reconstructs the exact
// quote. This is the fabricated-quote moment an existence-only citation checker
// would pass.
describe("VerifyResults quote autopsy", () => {
  function engineWithQuote(quote: Record<string, unknown>): VerifyEngine {
    const base = engineWith([noRecordClaim]);
    return {
      ...base,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      response: { ...(base.response as any), quote_results: [quote] } as any
    };
  }

  const alteredQuote = {
    index: 0,
    quote: "due process requires notice ... the court awarded treble damages",
    status: "altered",
    segments: [
      { text: "due process requires notice", kind: "verbatim" },
      { text: " ... the court awarded ", kind: "neutral" },
      { text: "treble damages", kind: "altered" }
    ]
  };

  it("strikes the fabricated words and leaves the genuine words in ink", () => {
    const { container } = render(<VerifyResults engine={engineWithQuote(alteredQuote)} draft="" />);
    expect(container.querySelector('[data-kind="altered"]')?.textContent).toBe("treble damages");
    expect(container.querySelector('[data-kind="verbatim"]')?.textContent).toContain(
      "due process requires notice"
    );
  });

  it("reconstructs the exact quote from its segments (no dropped or reordered words)", () => {
    const { container } = render(<VerifyResults engine={engineWithQuote(alteredQuote)} draft="" />);
    expect(container.querySelector("blockquote")?.textContent).toContain(
      "due process requires notice ... the court awarded treble damages"
    );
  });

  it("never strikes a genuine word (the autopsy cannot over-accuse)", () => {
    const { container } = render(<VerifyResults engine={engineWithQuote(alteredQuote)} draft="" />);
    const struck = Array.from(container.querySelectorAll('[data-kind="altered"]'))
      .map((n) => n.textContent)
      .join(" ");
    expect(struck).not.toContain("due process");
  });

  it("a quote with no segments renders plainly (a could-not-check refusal is never struck)", () => {
    const noSegments = {
      index: 0,
      quote: "the statute was unconstitutional as applied",
      status: "could_not_check",
      segments: []
    };
    const { container } = render(<VerifyResults engine={engineWithQuote(noSegments)} draft="" />);
    expect(container.querySelector('[data-kind="altered"]')).toBeNull();
    expect(screen.getByText("Could not check")).toBeTruthy();
  });
});

// Three non-success-state invariants for the live Cachet verify UI. A lawyer
// watching a verification run must never see a misleading state: a silent
// blank that reads as an all-clear, a definitive "all supported" headline
// while claims are still arriving, or a crash from one bad entry in the
// claims array.
describe("VerifyResults non-success-state invariants", () => {
  // (a) Zero claims is always an explicit empty state, never a blank container.
  describe("zero-claim results never render as a silent blank", () => {
    function engineZeroClaims(
      coverage: { statements: number; treated: number; untreated: number } | null
    ): VerifyEngine {
      const e = engineWith([]);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (e.response as any).coverage = coverage;
      return e;
    }

    it("no coverage block at all (LLM path): explicit empty state, no all-clear headline", () => {
      render(<VerifyResults engine={engineZeroClaims(null)} draft="" />);
      expect(screen.getByText(/no checkable claims found in this document/i)).toBeTruthy();
      expect(screen.queryByText(/All \d+ statements are supported/i)).toBeNull();
    });

    it("coverage block present but statements: 0: still an explicit empty state", () => {
      render(
        <VerifyResults
          engine={engineZeroClaims({ statements: 0, treated: 0, untreated: 0 })}
          draft=""
        />
      );
      const panel = screen.getByText(/no checkable claims found in this document/i);
      expect(panel).toBeTruthy();
      expect(screen.queryByText(/All \d+ statements are supported/i)).toBeNull();
    });

    it("coverage.statements > 0: the detailed coverage panel counts as the explicit empty state", () => {
      render(
        <VerifyResults
          engine={engineZeroClaims({ statements: 4, treated: 0, untreated: 4 })}
          draft=""
        />
      );
      expect(screen.getByText(/no checkable claims in this draft/i)).toBeTruthy();
      expect(screen.queryByText(/All \d+ statements are supported/i)).toBeNull();
    });
  });

  // (b) An in-progress/streaming result must show an in-progress affordance and
  // must never show a definitive "all supported" summary for claims still arriving.
  describe("a streaming result never shows a definitive all-supported summary", () => {
    function streamingEngine(): VerifyEngine {
      const skeleton = (claim_index: number) =>
        ({
          claim_index,
          claim_text: `streaming claim ${claim_index}`,
          verdict: "verified",
          citations: [],
          case_verdicts: [],
          unsupported_reason: null
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
        }) as any;
      let s = initialStreamState();
      s = reduceStreamEvent(s, {
        type: "claims",
        claim_verdicts: [skeleton(0), skeleton(1)]
      });
      // Only claim 0's cite check has landed; claim 1 is still in flight.
      s = reduceStreamEvent(s, {
        type: "cite_verdict",
        claim_index: 0,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        case_verdict: { claim_index: 0, ok: true, verdicts: [] } as any
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
        streamInterrupted: false,
        verify: vi.fn(),
        markSealed: vi.fn(),
        cancel: vi.fn()
      };
    }

    it("shows a visible in-progress affordance while claims are still arriving", () => {
      render(<VerifyResults engine={streamingEngine()} draft="" />);
      expect(screen.getByText(/checking citations/i)).toBeTruthy();
    });

    it("never renders the definitive 'All N statements are supported' headline mid-stream", () => {
      render(<VerifyResults engine={streamingEngine()} draft="" />);
      expect(screen.queryByText(/All \d+ statements are supported/i)).toBeNull();
    });

    it("never renders a settled verdict summary region while still streaming", () => {
      const { container } = render(<VerifyResults engine={streamingEngine()} draft="" />);
      // The settled summary/empty-state panels are response-gated; response is
      // still null mid-stream, so none of them may appear yet.
      expect(container.querySelector("[data-empty-coverage]")).toBeNull();
      expect(container.querySelector("[data-empty-claims]")).toBeNull();
      expect(screen.queryByText(/need your review|could not be verified against your sources/i)).toBeNull();
    });
  });

  // (c) A null or malformed entry in the claims array must be skipped
  // gracefully and must never throw or crash the component.
  describe("malformed claim entries are skipped gracefully, never crash the render", () => {
    const validClaim = {
      claim_index: 0,
      claim_text: "claim zero is a normal, well-formed verdict.",
      verdict: "verified",
      citations: [],
      case_verdicts: [],
      placement: null
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function engineWithRawClaims(claimVerdicts: any[]): VerifyEngine {
      return {
        response: {
          draft_text: "claim zero is a normal, well-formed verdict.",
          claim_verdicts: claimVerdicts,
          summary: { total: claimVerdicts.length, verified: 0, unsupported: 0, unknown: 0 },
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
        streamInterrupted: false,
        verify: vi.fn(),
        markSealed: vi.fn(),
        cancel: vi.fn()
      };
    }

    it("does not throw when the claims array contains null and undefined entries", () => {
      const engine = engineWithRawClaims([validClaim, null, undefined, validClaim]);
      expect(() => render(<VerifyResults engine={engine} draft="" />)).not.toThrow();
    });

    it("does not throw when the claims array contains a non-object (string) entry", () => {
      const engine = engineWithRawClaims([validClaim, "not a claim object"]);
      expect(() => render(<VerifyResults engine={engine} draft="" />)).not.toThrow();
    });

    it("skips the bad entries and counts only the valid claims toward the result", () => {
      // Both valid entries are clean "verified" claims with no case verdicts,
      // so a render that actually skipped the 3 bad entries (rather than,
      // say, silently dropping a valid one alongside them) settles on exactly
      // "All 2 statements are supported".
      const engine = engineWithRawClaims([validClaim, null, undefined, "garbage", validClaim]);
      render(<VerifyResults engine={engine} draft="" />);
      expect(
        screen.getByText("All 2 statements are supported by the sources you provided.")
      ).toBeTruthy();
    });
  });
});

// T71: honesty-on-screen at the badge level. A run that has not reached a
// clean, settled, error-free state must never render the affirmative
// "Supported" badge — the exact failure the round-3 postmortem named as the
// next false-green target. This block pins the three load-bearing cases: a
// non-terminal (loading/streaming, no response yet) run, a zero-claims
// settled run, an errored run, AND the positive control — a genuinely
// verified claim must still render "Supported", proving the guard does not
// over-fire into silence.
describe("VerifyResults — 'Supported' badge honesty (T71)", () => {
  // A claim whose disposition resolves to the plain "Supported" label: a
  // "verified" grounding verdict with no citations to check and no presence
  // hedge (see claimDisposition.ts's final fallthrough). Reused below both as
  // the positive control and as the payload for the loading/error races,
  // since the whole point is that the SAME claim must render differently
  // depending on the run's state, not the claim's own content.
  const plainSupportedClaim = {
    claim_index: 0,
    claim_text: "The agreement's initial term is five years.",
    verdict: "verified",
    citations: [],
    case_verdicts: [],
    placement: null
  };

  it("a loading/streaming run with no landed claims renders no 'Supported' badge", () => {
    const engine: VerifyEngine = {
      response: null,
      stream: initialStreamState(),
      loading: true,
      hydrating: false,
      error: null,
      sealedSeed: null,
      certAtSeed: null,
      hydratedDraft: null,
      streamInterrupted: false,
      verify: vi.fn(),
      markSealed: vi.fn(),
      cancel: vi.fn()
    };
    render(<VerifyResults engine={engine} draft="" />);
    expect(screen.queryByText("Supported")).toBeNull();
  });

  it("a zero-claims settled result renders no 'Supported' badge", () => {
    render(<VerifyResults engine={engineWith([])} draft="" />);
    expect(screen.queryByText("Supported")).toBeNull();
  });

  it("an errored run (response.error set, claims still attached) renders no 'Supported' badge", () => {
    // A payload-level error OTHER than the specially-handled
    // "provider_below_quality_bar" literal used to fall through untouched:
    // the items-based summary rendered unconditionally on items.length > 0,
    // with no regard for response.error. This pins the fix.
    const engine = engineWith([plainSupportedClaim]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (engine.response as any).error = "internal_error";
    render(<VerifyResults engine={engine} draft="" />);
    expect(screen.queryByText("Supported")).toBeNull();
  });

  it("an engine-level stream error (response null) renders no 'Supported' badge", () => {
    const engine: VerifyEngine = {
      response: null,
      stream: initialStreamState(),
      loading: false,
      hydrating: false,
      error: "Verification did not finish. No verdict was produced; nothing was marked supported.",
      sealedSeed: null,
      certAtSeed: null,
      hydratedDraft: null,
      streamInterrupted: false,
      verify: vi.fn(),
      markSealed: vi.fn(),
      cancel: vi.fn()
    };
    render(<VerifyResults engine={engine} draft="" />);
    expect(screen.queryByText("Supported")).toBeNull();
  });

  it("a genuinely settled, error-free, non-loading verified claim STILL renders 'Supported' (the guard does not over-fire)", () => {
    render(<VerifyResults engine={engineWith([plainSupportedClaim])} draft="" />);
    // "Supported" legitimately appears more than once for a real pass (the
    // stat-row count and the per-claim badge), so assert presence rather
    // than a single unique match.
    expect(screen.getAllByText("Supported").length).toBeGreaterThan(0);
  });
});
