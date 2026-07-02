import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { useState } from "preact/hooks";
import { describe, expect, it } from "vitest";

import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { ExaminationDrawer, checksFor } from "./ExaminationDrawer";

// The four-checks derivation is trust-critical: it is the drawer's whole claim
// to honesty (four signals shown separately, at their true weights). These
// tests lock the register rules: a bounded-corpus miss is never an accusation,
// an AI holding judgment never wears the deterministic flag, and a multi-cite
// claim is judged on ALL its cases, not cases[0].

function card(verdicts: Array<Record<string, unknown>>): VerifyClaimVerdict {
  return {
    claim_index: 0,
    claim_text: "claim",
    verdict: "verified",
    citations: [],
    case_verdicts: [{ claim_index: 0, ok: true, verdicts }],
    unsupported_reason: null
  } as unknown as VerifyClaimVerdict;
}

function rowByName(c: VerifyClaimVerdict, name: string) {
  const row = checksFor(c).find((r) => r.name === name);
  if (!row) throw new Error(`missing check row: ${name}`);
  return row;
}

describe("checksFor — cited case exists", () => {
  it("aggregates over ALL cases: one real case never hides a second missing one", () => {
    const c = card([
      { citation: "1 U.S. 1", status: 200, exists: true },
      { citation: "2 U.S. 2", status: 404, exists: false }
    ]);
    expect(rowByName(c, "Cited case exists").state).toBe("flag");
  });

  it("a bounded-corpus miss is could-not-check (unknown), never the flag accusation", () => {
    const c = card([{ citation: "999 F.3d 1", status: 404, exists: false, bounded_corpus: true }]);
    const row = rowByName(c, "Cited case exists");
    expect(row.state).toBe("unknown");
    expect(row.detail).toMatch(/outside the offline corpus/i);
  });

  it("a caption mismatch is the flag even though the number resolved", () => {
    const c = card([
      { citation: "1 U.S. 1", status: 200, exists: true, caption_mismatch: true }
    ]);
    const row = rowByName(c, "Cited case exists");
    expect(row.state).toBe("flag");
    expect(row.detail).toMatch(/different case/i);
  });

  it("all cases real -> pass; no cases -> unknown", () => {
    expect(
      rowByName(card([{ citation: "1 U.S. 1", status: 200, exists: true }]), "Cited case exists")
        .state
    ).toBe("pass");
    expect(rowByName(card([]), "Cited case exists").state).toBe("unknown");
  });

  it("an ambiguous citation (300) is unknown, not a flag", () => {
    const c = card([{ citation: "1 U.S. 1", status: 300, exists: false }]);
    expect(rowByName(c, "Cited case exists").state).toBe("unknown");
  });
});

describe("checksFor — holding match (assistive register)", () => {
  it("a holding contradiction is a query for review, NEVER the deterministic flag", () => {
    // An AI judgment about a real source must not wear the oxblood flag the
    // fabricated-citation check wears. Same rule claimDisposition locks for
    // proposition_unsupported; the drawer's check row must match.
    const c = card([
      { citation: "1 U.S. 1", status: 200, exists: true, holding_match: false }
    ]);
    const row = rowByName(c, "Holding matches the claim");
    expect(row.state).toBe("query");
    expect(row.weight).toBe("Assistive");
    expect(row.detail).toMatch(/for your review/i);
  });

  it("a supporting holding stays a query (confirm against the source), not a confident pass", () => {
    const c = card([
      { citation: "1 U.S. 1", status: 200, exists: true, holding_match: true }
    ]);
    expect(rowByName(c, "Holding matches the claim").state).toBe("query");
  });

  it("any contradiction across multiple cases surfaces, not just cases[0]", () => {
    const c = card([
      { citation: "1 U.S. 1", status: 200, exists: true, holding_match: true },
      { citation: "2 U.S. 2", status: 200, exists: true, holding_match: false }
    ]);
    const row = rowByName(c, "Holding matches the claim");
    expect(row.state).toBe("query");
    expect(row.detail).toMatch(/may not stand/i);
  });

  it("no holding signal -> unknown (not assessed)", () => {
    const c = card([{ citation: "1 U.S. 1", status: 200, exists: true }]);
    expect(rowByName(c, "Holding matches the claim").state).toBe("unknown");
  });
});

describe("checksFor — grounded reflects the engine's actual finding", () => {
  // A contract claim carries no cases; its grounding verdict + reason ride the
  // top-line verdict + unsupported_reason. The drawer must surface that specific
  // reason, never the blanket "Nothing in the loaded sources supports this
  // statement" — which is flatly wrong for a sentence that is verbatim except one
  // altered figure (the reported demo failure).
  function contractCard(
    verdict: "verified" | "unsupported" | "unknown",
    reason: string | null
  ): VerifyClaimVerdict {
    return {
      claim_index: 0,
      claim_text: "Allocation key: turnover (10% Italy, 20% France, 10% Spain, 10% Germany)",
      verdict,
      citations: [],
      case_verdicts: [],
      unsupported_reason: reason
    } as unknown as VerifyClaimVerdict;
  }

  it("a flagged contract claim shows the specific contradiction, not the blanket lie", () => {
    const c = contractCard(
      "unsupported",
      "The summary states 20% for France; the loaded source states 10%."
    );
    const row = rowByName(c, "Grounded in your sources");
    expect(row.state).toBe("flag");
    expect(row.detail).toBe("The summary states 20% for France; the loaded source states 10%.");
    expect(row.detail).not.toMatch(/Nothing in the loaded sources/i);
  });

  it("a supported contract claim shows its present-hedge reason when one is attached", () => {
    const c = contractCard("verified", "Present in your sources, in the allocation-key clause.");
    const row = rowByName(c, "Grounded in your sources");
    expect(row.state).toBe("pass");
    expect(row.detail).toBe("Present in your sources, in the allocation-key clause.");
  });

  it("falls back to generic copy only when the engine attached no reason", () => {
    const flag = rowByName(contractCard("unsupported", null), "Grounded in your sources");
    expect(flag.state).toBe("flag");
    expect(flag.detail).toMatch(/do not support this statement/i);
    const pass = rowByName(contractCard("verified", null), "Grounded in your sources");
    expect(pass.detail).toMatch(/A loaded source supports/i);
  });
});

// The drawer is aria-modal=false (the record behind stays readable, so Tab is
// NOT trapped), but it still owes the opener its focus back, and while closed it
// must be inert so its Close button is not a tabbable control stranded in an
// aria-hidden subtree (WCAG 4.1.2).
function emptyCard(): VerifyClaimVerdict {
  return {
    claim_index: 0,
    claim_text: "A claim with no attached source.",
    verdict: "verified",
    citations: [],
    case_verdicts: []
  } as unknown as VerifyClaimVerdict;
}

describe("ExaminationDrawer — focus + inert", () => {
  it("captures the opener on open and restores focus to it on close", async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <div>
          <button type="button" data-testid="opener" onClick={() => setOpen(true)}>
            examine
          </button>
          <ExaminationDrawer card={emptyCard()} open={open} onClose={() => setOpen(false)} />
        </div>
      );
    }
    render(<Harness />);

    const opener = screen.getByTestId("opener");
    opener.focus();
    fireEvent.click(opener);

    const close = await screen.findByRole("button", { name: "Close" });
    await waitFor(() => expect(document.activeElement).toBe(close));

    fireEvent.click(close);
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it("is inert + aria-hidden while closed and interactive while open", () => {
    const closed = render(
      <ExaminationDrawer card={emptyCard()} open={false} onClose={() => {}} />
    );
    const closedAside = closed.container.querySelector("aside[role='dialog']");
    expect(closedAside?.hasAttribute("inert")).toBe(true);
    expect(closedAside?.getAttribute("aria-hidden")).toBe("true");
    closed.unmount();

    const open = render(<ExaminationDrawer card={emptyCard()} open onClose={() => {}} />);
    const openAside = open.container.querySelector("aside[role='dialog']");
    expect(openAside?.hasAttribute("inert")).toBe(false);
    expect(openAside?.hasAttribute("aria-hidden")).toBe(false);
  });
});

// The lawyer opens this drawer at the exact moment scrutiny peaks. Every
// non-happy path must render explicit, human-readable text — never a blank
// panel, and never a state that could read as a completed, honest examination
// when it wasn't one.
describe("ExaminationDrawer — non-happy-path states", () => {
  it("(1) missing data: no card selected renders an explicit 'no source' message, not a blank body", () => {
    expect(() =>
      render(<ExaminationDrawer card={null} open onClose={() => {}} />)
    ).not.toThrow();
    expect(screen.getByText("No source to examine.")).toBeTruthy();
    expect(screen.getByText(/Select a claim to open its examination/i)).toBeTruthy();
  });

  it("(2) in-flight load: loading renders an explicit labeled loading affordance, not a blank body", () => {
    expect(() =>
      render(<ExaminationDrawer card={null} open loading onClose={() => {}} />)
    ).not.toThrow();
    // The Spinner primitive also carries role="status" for its own a11y
    // label, so assert on the visible text rather than a single-role query.
    expect(screen.getByText("Loading the source…")).toBeTruthy();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("(3) network/stream error: a load failure renders an explicit failure state, never a completed examination", () => {
    expect(() =>
      render(
        <ExaminationDrawer
          card={null}
          open
          loadError="The connection to the document service was lost."
          onClose={() => {}}
        />
      )
    ).not.toThrow();
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/could not be loaded/i);
    expect(
      screen.getByText("The connection to the document service was lost.")
    ).toBeTruthy();
    // Must not also render the four-checks section as if the claim were examined.
    expect(screen.queryByText("Four checks, shown separately")).toBeNull();
  });

  it("(4) malformed response: a card with an unexpected shape renders an explicit error instead of throwing", () => {
    const malformedCard = {
      claim_index: 0,
      claim_text: "A claim carrying a malformed payload.",
      verdict: "verified",
      citations: [],
      // case_verdicts is expected to be an array; a truncated/version-skewed
      // payload can hand this component an object instead, which breaks the
      // .flatMap access inside checksFor/dispositionForClaim.
      case_verdicts: {}
    } as unknown as VerifyClaimVerdict;

    expect(() =>
      render(<ExaminationDrawer card={malformedCard} open onClose={() => {}} />)
    ).not.toThrow();
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/could not be displayed/i);
  });
});
