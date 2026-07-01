import { fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VerifyResults, verdictSummaryRegister } from "./VerifyResults";
import type { ClaimDisposition } from "./claimDisposition";
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
      verify: vi.fn(),
      markSealed: vi.fn(),
      cancel: vi.fn()
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

describe("VerifyResults seal records the pair on the engine", () => {
  it("sealing calls engine.markSealed with the cert fingerprint AND its timestamp", async () => {
    // The mutation review proved this wiring was a surviving mutant: deleting
    // the markSealed call failed zero tests while being the only guard against
    // the seal silently downgrading after a remount. This pins it, including
    // the timestamp half of the pair (a reopened exhibit must re-render the
    // ORIGINAL seal date, never mint a fresh one).
    const engine = engineWith([noRecordClaim]);
    render(<VerifyResults engine={engine} draft="" />);
    fireEvent.click(screen.getByText("Export certification"));
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

  it("does not fabricate a coverage statement when the engine reported no coverage block (LLM path)", () => {
    render(<VerifyResults engine={engineNoFindings(null)} draft="" />);
    expect(screen.queryByText(/no checkable claims/i)).toBeNull();
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
