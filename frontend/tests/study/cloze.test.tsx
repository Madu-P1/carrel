import { render, screen } from "@testing-library/preact";
import { describe, expect, test } from "vitest";

import { isClozeText, renderClozeBody } from "@/features/study/cloze";

/*
 * PR 5.1 of flashcards-focus (ADR 0002) — cloze rendering unit tests.
 *
 * Pins the contract:
 *   - Front face hides the marker (renders a placeholder).
 *   - Back face reveals the marker's inner term in accent color.
 *   - Multi-marker sentences render all markers correctly.
 *   - Non-cloze text passes through unchanged.
 *   - isClozeText detects markers reliably.
 */

describe("cloze rendering (PR 5.1)", () => {
  test("isClozeText detects single-occlusion markers", () => {
    expect(isClozeText("The {{c1::powerhouse}} of the cell.")).toBe(true);
    expect(isClozeText("plain text without markers")).toBe(false);
    expect(isClozeText(null)).toBe(false);
    expect(isClozeText("")).toBe(false);
  });

  test("isClozeText accepts multi-digit indices", () => {
    expect(isClozeText("Foo {{c12::bar}} baz")).toBe(true);
  });

  test("isClozeText rejects malformed markers", () => {
    expect(isClozeText("Foo {{c1:bar}} baz")).toBe(false); // single colon
    expect(isClozeText("Foo {{::bar}} baz")).toBe(false); // no index
  });

  test("front face hides the cloze term behind a placeholder", () => {
    const body = renderClozeBody(
      "The mitochondrion is the {{c1::powerhouse}} of the cell.",
      "front",
    );
    const { container } = render(<>{body}</>);
    // The hidden term must NOT appear on the front face.
    expect(container.textContent).not.toContain("powerhouse");
    // The surrounding prose must appear.
    expect(container.textContent).toContain("The mitochondrion is the");
    expect(container.textContent).toContain("of the cell");
    // The placeholder span has the right aria-label.
    expect(screen.getByLabelText("blanked term")).toBeTruthy();
  });

  test("back face reveals the cloze term", () => {
    const body = renderClozeBody(
      "The mitochondrion is the {{c1::powerhouse}} of the cell.",
      "back",
    );
    const { container } = render(<>{body}</>);
    expect(container.textContent).toBe(
      "The mitochondrion is the powerhouse of the cell.",
    );
  });

  test("multi-marker sentences hide all markers on the front", () => {
    const body = renderClozeBody(
      "{{c1::Mitochondria}} produce {{c2::ATP}} via {{c3::oxidative}} phosphorylation.",
      "front",
    );
    const { container } = render(<>{body}</>);
    expect(container.textContent).not.toContain("Mitochondria");
    expect(container.textContent).not.toContain("ATP");
    expect(container.textContent).not.toContain("oxidative");
    expect(container.textContent).toContain("phosphorylation");
    // Three placeholders.
    expect(screen.getAllByLabelText("blanked term")).toHaveLength(3);
  });

  test("multi-marker sentences reveal all markers on the back", () => {
    const body = renderClozeBody(
      "{{c1::Mitochondria}} produce {{c2::ATP}} via {{c3::oxidative}} phosphorylation.",
      "back",
    );
    const { container } = render(<>{body}</>);
    expect(container.textContent).toBe(
      "Mitochondria produce ATP via oxidative phosphorylation.",
    );
  });

  test("renders empty/null source safely", () => {
    expect(renderClozeBody("", "front")).toBeNull();
    expect(renderClozeBody("", "back")).toBeNull();
  });

  test("source without markers degrades to literal text", () => {
    const body = renderClozeBody("just a plain sentence.", "front");
    const { container } = render(<>{body}</>);
    expect(container.textContent).toBe("just a plain sentence.");
  });
});
