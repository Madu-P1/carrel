import { fireEvent, render, screen } from "@testing-library/preact";
import { describe, expect, test, vi } from "vitest";

import { CertificationExhibit } from "./CertificationExhibit";
import type { CertificationModel } from "./certification";
import styles from "./VerifyView.module.css";

// PR2 locks the certification cover + human seal states. The seal is set by the
// human, captures the draft fingerprint, and reads "cracked" when a later draft
// no longer matches — a quiet dimmed re-verify nudge, never an oxblood flag.
// WAAPI motion is shimmed globally (tests/setup.ts); these assert deterministic
// state, never animation frames.

function model(fingerprint: string): CertificationModel {
  const flagged = [
    {
      index: 1,
      kind: "citation_not_found" as const,
      label: "Citation not found",
      claimText: "Cites a fake case.",
      sources: ["999 U.S. 999"],
      sourceFingerprints: ["0".repeat(64)]
    }
  ];
  return {
    generatedAtISO: "2026-05-29T12:00:00.000Z",
    fingerprint,
    provider: "claude",
    localExecution: false,
    attestation: "Verification ran via claude in the cloud.",
    totalStatements: 2,
    needsReviewCount: 1,
    counts: {
      supported: 1,
      citation_not_found: 1,
      proposition_unsupported: 0,
      claim_unsupported: 0,
      could_not_check: 0,
      assessed: 0
    },
    flagged,
    allItems: [
      ...flagged,
      {
        index: 2,
        kind: "supported",
        label: "Supported",
        claimText: "A grounded statement.",
        sources: ["Brief.pdf, p. 12"],
        sourceFingerprints: ["0".repeat(64)]
      }
    ]
  };
}

function noop(): void {}

describe("CertificationExhibit cover + seal", () => {
  test("renders the warm cover attestation and an unsealed Set the seal control", () => {
    render(<CertificationExhibit model={model("aaaa")} onClose={noop} />);
    expect(screen.getByText(/attests to grounding/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Set the seal" })).toBeTruthy();
    // Unsealed: no seal caption yet, sealed or cracked.
    expect(screen.queryByText(/^Sealed \d/)).toBeNull();
    expect(screen.queryByText(/re-verify/i)).toBeNull();
  });

  test("clicking Set the seal transitions to the sealed state", () => {
    render(<CertificationExhibit model={model("aaaa")} onClose={noop} />);
    fireEvent.click(screen.getByRole("button", { name: "Set the seal" }));
    expect(screen.getByRole("button", { name: "Sealed" })).toBeTruthy();
    expect(screen.getByText(/^Sealed \d/)).toBeTruthy();
    const seal = screen.getByRole("img", { name: "Certification seal, set" });
    expect(seal.className).toContain(styles.sealSet);
    expect(seal.className).not.toContain(styles.sealCracked);
    // The success is announced to assistive tech via the polite live region.
    expect(screen.getByRole("status").textContent).toMatch(/^Sealed \d/);
  });

  test("setting the seal moves focus off the now-disabled button, staying in the dialog", () => {
    render(<CertificationExhibit model={model("aaaa")} onClose={noop} />);
    const setBtn = screen.getByRole("button", { name: "Set the seal" });
    // Start with focus ON the seal button so the assertion observes a real MOVE,
    // not the mount default (Close is focused first, which would pass vacuously).
    setBtn.focus();
    expect(document.activeElement).toBe(setBtn);
    fireEvent.click(setBtn);
    // On seal the button disables; focus must move to a stable in-dialog control,
    // never strand on the disabled button or fall to <body> out of the trap.
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close" }));
  });

  test("under prefers-reduced-motion, sealing runs no animation and rests on the static sealed state", () => {
    const reduceMql = {
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false
    } as MediaQueryList;
    const matchMediaSpy = vi.spyOn(window, "matchMedia").mockReturnValue(reduceMql);
    const animateSpy = vi.spyOn(Element.prototype, "animate");
    try {
      render(<CertificationExhibit model={model("aaaa")} onClose={noop} />);
      animateSpy.mockClear();
      fireEvent.click(screen.getByRole("button", { name: "Set the seal" }));
      // The seal-set WAAPI is gated behind prefersReducedMotion(); the sealed look
      // is class-derived, so the state is reached with no animation at all.
      expect(animateSpy).not.toHaveBeenCalled();
      expect(screen.getByRole("img", { name: "Certification seal, set" }).className).toContain(
        styles.sealSet
      );
    } finally {
      animateSpy.mockRestore();
      matchMediaSpy.mockRestore();
    }
  });

  test("a draft change after sealing cracks the seal with a quiet re-verify caption", () => {
    const sealed = model("aaaa");
    const { rerender } = render(<CertificationExhibit model={sealed} onClose={noop} />);
    fireEvent.click(screen.getByRole("button", { name: "Set the seal" }));
    // The cracked render contract: the SAME model with ONLY its fingerprint changed
    // (what a reopened persisted seal produces in PR6) renders cracked, so the crack
    // is provably driven by the fingerprint delta. sealStateFor's unit test locks the logic.
    rerender(<CertificationExhibit model={{ ...sealed, fingerprint: "bbbb" }} onClose={noop} />);
    const seal = screen.getByRole("img", { name: /cracked/i });
    expect(seal.className).toContain(styles.sealCracked);
    const caption = screen.getByText(/re-verify/i);
    // The cracked caption wears the quiet "stale" register, not a verification flag.
    expect(caption.className).toContain(styles.stale);
  });

  test("the cold register still renders the fingerprint, the review section, and a flagged item", () => {
    render(<CertificationExhibit model={model("c0ffee")} onClose={noop} />);
    expect(screen.getByText("c0ffee")).toBeTruthy();
    expect(screen.getByText("Items requiring attorney review")).toBeTruthy();
    // The fabricated claim appears in both the flagged and all-statements sections.
    expect(screen.getAllByText("Cites a fake case.").length).toBeGreaterThan(0);
  });

  // Cachet PR6b: reopening a saved brief seeds the seal from a STORED fingerprint
  // (no click). A matching fingerprint shows sealed; a differing one (the draft
  // changed since sealing) shows cracked. Locks the persisted-seal prop seam.
  test("a persisted sealedFingerprint that matches shows the sealed register with no click", () => {
    render(
      <CertificationExhibit model={model("aaaa")} sealedFingerprint="aaaa" onClose={noop} />
    );
    expect(screen.getByRole("img", { name: "Certification seal, set" }).className).toContain(
      styles.sealSet
    );
    // Nothing to click: the seal arrives already set from the stored value.
    expect(screen.queryByRole("button", { name: "Set the seal" })).toBeNull();
  });

  test("a persisted sealedFingerprint that differs shows cracked with the quiet stale caption", () => {
    render(
      <CertificationExhibit model={model("bbbb")} sealedFingerprint="aaaa" onClose={noop} />
    );
    const seal = screen.getByRole("img", { name: /cracked/i });
    expect(seal.className).toContain(styles.sealCracked);
    const caption = screen.getByText(/re-verify/i);
    expect(caption.className).toContain(styles.stale);
  });

  test("omitting sealedFingerprint keeps the live unsealed-then-click behavior", () => {
    render(<CertificationExhibit model={model("aaaa")} onClose={noop} />);
    // Regression guard: the additive prop must not change the live verify flow.
    expect(screen.getByRole("button", { name: "Set the seal" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Certification seal, not yet set" })).toBeTruthy();
  });
});
