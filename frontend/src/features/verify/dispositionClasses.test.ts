import { describe, expect, test } from "vitest";

import { holdingClass, tierBadgeClass } from "./VerifyResults";
import styles from "./VerifyView.module.css";

// PR1 locks the disposition TIER (claimDisposition.test.ts) AND the tier/holding
// to CSS-class render seam this PR created. A holding mismatch is an AI judgment,
// so it must reach the assistive classes and never the oxblood deterministic-flag
// classes. These mappings are deterministic and single-answer, so they are
// machine-locked here rather than left to the craft eye. (Whether the dotted
// achromatic treatment READS as a "for your review" pencil note stays the
// operator's craft call.)

describe("verify class-mapping seam", () => {
  test("the verify stylesheet defines distinct, non-empty class tokens (guards a vacuous CSS mock)", () => {
    for (const token of [
      styles.badgeAssistive,
      styles.badgeFlag,
      styles.holdingAssistive,
      styles.caseMissing
    ]) {
      expect(typeof token).toBe("string");
      expect(token.length).toBeGreaterThan(0);
    }
    expect(styles.badgeAssistive).not.toBe(styles.badgeFlag);
    expect(styles.holdingAssistive).not.toBe(styles.caseMissing);
  });

  test("the assistive tier renders the assistive badge, never the oxblood flag badge", () => {
    expect(tierBadgeClass("assistive")).toBe(styles.badgeAssistive);
    expect(tierBadgeClass("assistive")).not.toBe(styles.badgeFlag);
  });

  test("the deterministic flag tier keeps the oxblood flag badge; refusal and pass map to their own", () => {
    expect(tierBadgeClass("flag")).toBe(styles.badgeFlag);
    expect(tierBadgeClass("refusal")).toBe(styles.badgeRefusal);
    expect(tierBadgeClass("pass")).toBe(styles.badgePass);
  });

  test("a holding contradiction renders the assistive class, never the oxblood caseMissing", () => {
    expect(holdingClass("contradicts")).toBe(styles.holdingAssistive);
    expect(holdingClass("contradicts")).not.toBe(styles.caseMissing);
  });

  test("a supporting holding stays quiet case-exists ink, and no holding maps to no class", () => {
    expect(holdingClass("supports")).toBe(styles.caseExists);
    expect(holdingClass(null)).toBe("");
  });
});
