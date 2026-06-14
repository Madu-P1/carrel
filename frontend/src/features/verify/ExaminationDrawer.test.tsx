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
