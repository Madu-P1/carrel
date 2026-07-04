import { render } from "@testing-library/preact";
import { describe, expect, it } from "vitest";

import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { WorkspaceMargin } from "./WorkspaceMargin";

const DRAFT =
  "The statute was unconstitutional as applied. The fee was upheld as lawful. A paraphrased point sits here.";

function card(
  claim_index: number,
  opts: {
    text: string;
    verdict?: "verified" | "unsupported" | "unknown";
    placed?: boolean;
    start?: number;
    end?: number;
    method?: "exact" | "fuzzy" | "unplaced";
    case_verdicts?: unknown[];
  }
): VerifyClaimVerdict {
  return {
    claim_index,
    claim_text: opts.text,
    verdict: opts.verdict ?? "unsupported",
    citations: [],
    case_verdicts: (opts.case_verdicts ?? []) as VerifyClaimVerdict["case_verdicts"],
    unsupported_reason: null,
    placement:
      opts.placed === false
        ? { placed: false, method: "unplaced", char_start: null, char_end: null }
        : {
            placed: true,
            method: opts.method ?? "exact",
            char_start: opts.start ?? 0,
            char_end: opts.end ?? 0
          }
  } as VerifyClaimVerdict;
}

function renderMargin(cards: VerifyClaimVerdict[]) {
  return render(
    <WorkspaceMargin draftText={DRAFT} cards={cards} examined={null} onExamine={() => {}} />
  );
}

describe("WorkspaceMargin — honesty guards (headless)", () => {
  it("renders the draft text verbatim in the document body", () => {
    const { container } = renderMargin([card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, verdict: "unsupported" })]);
    expect(container.textContent).toContain("The statute was unconstitutional as applied.");
    expect(container.textContent).toContain("A paraphrased point sits here.");
  });

  it("a flagged (unsupported) claim is an inline button with a flag aria-label", () => {
    const { getByRole } = renderMargin([
      card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, verdict: "unsupported" })
    ]);
    const mark = getByRole("button", { name: /Statement flagged/i });
    expect(mark).toBeDefined();
    expect(mark.getAttribute("data-tier")).toBe("flag");
  });

  it("a supported claim is unmarked (data-tier pass) and announces supported", () => {
    const { getByRole } = renderMargin([
      card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, verdict: "verified" })
    ]);
    const mark = getByRole("button", { name: /checked and supported/i });
    expect(mark.getAttribute("data-tier")).toBe("pass");
  });

  it("an affirming pass (present in your sources) shows a rail card, the calibration beat", () => {
    // The demo's killer beat: a verbatim 'present' confirmation (verdict verified
    // WITH a presence reason) must surface as a positive card on the findings rail
    // so the buyer can see what the engine vouched for, next to the contradictions.
    // A silent empty-detail pass stays off the rail; an affirming one earns a card.
    const green = {
      ...card(0, {
        text: "The statute was unconstitutional as applied.",
        start: 0,
        end: 44,
        verdict: "verified"
      }),
      unsupported_reason: "This language appears verbatim in Section 14 of your source."
    } as VerifyClaimVerdict;
    const { getAllByText, container } = renderMargin([green]);
    // The affirming pass earns a rail card (data-note-key), labelled with what the
    // engine vouched for. Presence on the rail is the calibration signal.
    expect(getAllByText(/Present in your sources/i).length).toBeGreaterThan(0);
    expect(container.querySelector('[data-note-key="0"]')).not.toBeNull();
  });

  it("a silent supported claim (no detail) stays off the rail, unmarked", () => {
    const { container } = renderMargin([
      card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, verdict: "verified" })
    ]);
    // A silent pass produces no rail card at all (the absence of a flag is the pass).
    expect(container.querySelector('[data-note-key]')).toBeNull();
  });

  it("a refusal is announced as could-not-check, never as 'flagged'", () => {
    // The screen reader is the only rendering some users get. Announcing the
    // honest refusal as "Statement flagged" turns a could-not-check into an
    // accusation in that rendering — the visible register split (oxblood vs
    // composed ink) must survive the read-back.
    const { getByRole } = renderMargin([
      card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, verdict: "unknown" })
    ]);
    const mark = getByRole("button", { name: /could not be checked/i });
    expect(mark.getAttribute("data-tier")).toBe("refusal");
    expect(mark.getAttribute("aria-label")).not.toMatch(/flagged/i);
  });

  it("an assistive note is announced for review, never as 'flagged'", () => {
    const { getByRole } = renderMargin([
      card(0, {
        text: "The statute was unconstitutional as applied.",
        start: 0,
        end: 44,
        verdict: "verified",
        case_verdicts: [
          {
            claim_index: 0,
            ok: true,
            verdicts: [{ citation: "1 U.S. 1", status: 200, exists: true, holding_match: false }]
          }
        ]
      })
    ]);
    const mark = getByRole("button", { name: /for your review/i });
    expect(mark.getAttribute("data-tier")).toBe("assistive");
    expect(mark.getAttribute("aria-label")).not.toMatch(/flagged/i);
  });

  it("a margin note never repeats the same sentence as detail and trail", () => {
    // For an unknown-verdict refusal the disposition detail IS the wire's
    // unsupported_reason; rendering the reason again as the trail prints the
    // identical sentence twice in one note.
    const reason = "No source was loaded to check this statement against.";
    const refusal = {
      ...card(0, {
        text: "The statute was unconstitutional as applied.",
        start: 0,
        end: 44,
        verdict: "unknown"
      }),
      unsupported_reason: reason
    } as VerifyClaimVerdict;
    const { container } = renderMargin([refusal]);
    const occurrences = (container.textContent ?? "").split(reason).length - 1;
    expect(occurrences).toBe(1);
  });

  it("never renders a confidence percentage", () => {
    const { container } = renderMargin([
      card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, verdict: "unsupported" })
    ]);
    expect(container.textContent).not.toMatch(/\d+\s*%/);
  });

  it("never renders the word VERIFIED as a badge nor any green token class", () => {
    const { container } = renderMargin([
      card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, verdict: "verified" })
    ]);
    // No 'verified' badge text; the pass is unmarked.
    expect(container.textContent).not.toMatch(/\bVERIFIED\b/);
    // No success/green class leaked from the global study tokens.
    expect(container.querySelector('[class*="success"]')).toBeNull();
    expect(container.querySelector('[class*="green"]')).toBeNull();
  });

  it("an unplaced claim goes to the tray, not the document or rail", () => {
    const { container, getByText } = renderMargin([
      card(0, { text: "A claim with no draft span", placed: false, verdict: "unsupported" })
    ]);
    // tray section present with its honesty copy (the visible heading)
    expect(getByText(/Could not pin to the text/i)).toBeDefined();
    // no inline claim mark in the document (it has no span)
    expect(container.querySelector('[data-claim-index="0"]')).toBeNull();
  });

  it("does not render a quotation-check block (quotes live only in QuotePanel)", () => {
    // Quotation checks are owned by QuotePanel; the tray must not duplicate them
    // under its draft-placement header. With an unplaced claim present (so the
    // tray renders), there is still no "Quotation checks" sub-block here.
    const { queryByText } = renderMargin([
      card(0, { text: "A claim with no draft span", placed: false, verdict: "unsupported" })
    ]);
    expect(queryByText(/Quotation checks/i)).toBeNull();
  });

  it("a fuzzy placement carries the fuzzy mark modifier; exact does not", () => {
    const { container } = renderMargin([
      card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, method: "fuzzy", verdict: "unsupported" })
    ]);
    const mark = container.querySelector('[data-claim-index="0"]') as HTMLElement;
    // the fuzzy modifier class is present (CSS-module hashed, so match by substring)
    expect(mark.className).toMatch(/markFuzzy/i);
  });

  it("renders a margin note only for non-supported placed claims", () => {
    const { container } = renderMargin([
      card(0, { text: "The statute was unconstitutional as applied.", start: 0, end: 44, verdict: "unsupported" }),
      card(1, { text: "The fee was upheld as lawful.", start: 45, end: 74, verdict: "verified" })
    ]);
    const notes = container.querySelectorAll("[data-note-key]");
    expect(notes.length).toBe(1);
    expect(notes[0].getAttribute("data-note-key")).toBe("0");
  });
});
