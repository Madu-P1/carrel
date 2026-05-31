import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test } from "vitest";

// Source-level invariants for the scoped lawyer-grade verify mode (PR3). These
// guard the two properties the founder-approved DESIGN.md deviation rests on:
// the scope must not leak to global tokens, and the surface must add no motion
// that would ignore prefers-reduced-motion.
const css = readFileSync(resolve(__dirname, "VerifyView.module.css"), "utf8");

describe("verify visual mode is scoped and motion-safe", () => {
  test("defines a scoped .verifyScope token layer and adds no global :root override", () => {
    expect(css).toContain(".verifyScope");
    // No :root rule: the global dark study tokens, the rest of the app, and the
    // verify chain stay untouched. The deviation is confined to the verify route.
    expect(css).not.toMatch(/^\s*:root\b/m);
  });

  test("introduces no keyframe or animation (near-zero motion, reduced-motion safe)", () => {
    // The verify surface uses only Tier-1 CSS transitions (globally clamped under
    // prefers-reduced-motion); it must not add narrative keyframe motion.
    expect(css).not.toMatch(/@keyframes/);
    expect(css).not.toMatch(/\banimation\s*:/);
  });

  test("the cracked seal caption is dimmed ink, never the reserved oxblood flag accent", () => {
    // PR2: a cracked seal is a quiet re-verify nudge, not a verification flag, so its
    // caption must use the dimmed ink register and never the --verify-flag oxblood.
    const stale = css.match(/\.sealCaption\.stale\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(stale).toContain("--text-secondary");
    expect(stale).not.toContain("--verify-flag");
  });
});

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function contrast(fg: string, bg: string): number {
  const a = luminance(fg) + 0.05;
  const b = luminance(bg) + 0.05;
  return Math.max(a, b) / Math.min(a, b);
}

function token(block: string, name: string): string {
  const match = block.match(new RegExp(`${name}\\s*:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`token not found: ${name}`);
  return match[1];
}

describe("verify paper palette meets WCAG AA text contrast", () => {
  // The scoped paper text must stay legible for a skeptical credentialed buyer.
  // Locks the regression the re-rate caught: 12px tertiary text below 4.5:1.
  const block = css.match(/\.verifyScope\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  const surfaces: Record<string, string> = {
    background: token(block, "background"),
    "--surface-0": token(block, "--surface-0"),
    "--surface-1": token(block, "--surface-1"),
    "--surface-2": token(block, "--surface-2")
  };

  test("paper ink tokens clear 4.5:1 on every paper surface at body size", () => {
    for (const tokenName of ["--text-tertiary", "--text-secondary", "--text-primary"]) {
      const ink = token(block, tokenName);
      for (const [surfaceName, surface] of Object.entries(surfaces)) {
        expect(
          contrast(ink, surface),
          `${tokenName} (${ink}) on ${surfaceName} (${surface})`
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  });
});

describe("verify interactive controls restore a visible focus ring", () => {
  // appearance:none plus the global reset strip the native focus affordance, so
  // each such control must restore box-shadow: var(--shadow-focus) on
  // :focus-visible (the tokens.css convention; WCAG 2.4.7 Focus Visible).
  test("every appearance:none control defines a :focus-visible ring using --shadow-focus", () => {
    const blocks = [...css.matchAll(/\.([A-Za-z][\w-]*)\s*\{([^}]*)\}/g)];
    const needsRing = blocks
      .filter(([, , body]) => /appearance\s*:\s*none/.test(body))
      .map(([, name]) => name);
    expect(needsRing.length).toBeGreaterThan(0);
    for (const name of needsRing) {
      const focusBlock = css.match(new RegExp(`\\.${name}:focus-visible\\s*\\{([^}]*)\\}`));
      expect(focusBlock, `.${name} must define a :focus-visible block`).not.toBeNull();
      expect(
        focusBlock?.[1] ?? "",
        `.${name}:focus-visible must restore var(--shadow-focus)`
      ).toContain("--shadow-focus");
    }
  });
});
