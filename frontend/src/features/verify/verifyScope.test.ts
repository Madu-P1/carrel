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
});
