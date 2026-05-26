import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { CitationChip } from "./CitationChip";
import type { CitationRecord } from "../types";

function makeCitation(overrides: Partial<CitationRecord> = {}): CitationRecord {
  return {
    node_id: "node-1",
    document_id: "doc-1",
    document_name: "Source.pdf",
    section: "Intro",
    page_num: 2,
    snippet: "Mitosis separates chromosomes.",
    content: "Mitosis separates chromosomes.",
    score: 0.5,
    label: "Source.pdf · Intro",
    node_type: "body",
    ...overrides,
  };
}

// Carrel V2 visibility: body cites stay uncluttered (no badge),
// non-prose cites surface a short uppercase tag so a verifier can
// tell at a glance that a claim is backed by a table cell, figure
// caption, equation, or footnote rather than running prose.

test("body cite renders no source-type badge", () => {
  render(<CitationChip citation={makeCitation({ node_type: "body" })} index={1} />);
  expect(screen.queryByText(/^Table$|^Figure$|^Eq$|^Note$|^Heading$/)).toBeNull();
});

test("table_cell cite surfaces a Table badge", () => {
  render(<CitationChip citation={makeCitation({ node_type: "table_cell" })} index={1} />);
  expect(screen.getByText("Table")).toBeTruthy();
});

test("caption cite surfaces a Figure badge", () => {
  render(<CitationChip citation={makeCitation({ node_type: "caption" })} index={1} />);
  expect(screen.getByText("Figure")).toBeTruthy();
});

test("equation cite surfaces an Eq badge", () => {
  render(<CitationChip citation={makeCitation({ node_type: "equation" })} index={1} />);
  expect(screen.getByText("Eq")).toBeTruthy();
});

test("heading cite surfaces a Heading badge (defense-in-depth surfacing)", () => {
  // services.tutor.NON_CITABLE_NODE_TYPES should keep headings out
  // of the citation path entirely. If one ever leaks through, the
  // badge surfaces the leak instead of silently rendering as prose.
  render(<CitationChip citation={makeCitation({ node_type: "heading" })} index={1} />);
  expect(screen.getByText("Heading")).toBeTruthy();
});

test("unknown node_type renders no badge (forward-compatible default)", () => {
  render(<CitationChip citation={makeCitation({ node_type: "future_kind" })} index={1} />);
  expect(screen.queryByText(/^Table$|^Figure$|^Eq$|^Note$|^Heading$/)).toBeNull();
});
