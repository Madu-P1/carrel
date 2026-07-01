import { describe, expect, it } from "vitest";

import { displaySafe, NEUTRAL_PLACEHOLDER } from "./displaySafe";

// Compose every special character from its code point so this source file stays
// plain ASCII and never embeds a literal control character.
const ch = (code: number) => String.fromCharCode(code);
const REPLACEMENT = ch(0xfffd);

describe("displaySafe", () => {
  it("replaces the object-replacement character (the PDF-paste tofu) with U+FFFD", () => {
    const input = `observing that ${ch(0xfffc)}quote`;
    expect(displaySafe(input)).toBe(`observing that ${REPLACEMENT}quote`);
  });

  it("replaces C0 control and zero-width characters", () => {
    const input = `a${ch(0x07)}b${ch(0x200b)}c`;
    expect(displaySafe(input)).toBe(`a${REPLACEMENT}b${REPLACEMENT}c`);
  });

  it("is 1-to-1 length-preserving so claim-span offsets stay aligned", () => {
    const input = `x${ch(0x00)}y${ch(0xfeff)}z`;
    expect(displaySafe(input)).toHaveLength(input.length);
    expect(displaySafe(input)).toBe(`x${REPLACEMENT}y${REPLACEMENT}z`);
  });

  it("preserves tab, newline, carriage return, and ordinary text", () => {
    const input = `Line one.${ch(0x0a)}${ch(0x09)}Indented quote, 95,000.${ch(0x0d)}`;
    expect(displaySafe(input)).toBe(input);
  });

  it("leaves clean prose untouched", () => {
    expect(displaySafe("The fee was upheld as lawful.")).toBe("The fee was upheld as lawful.");
  });

  it("never throws for null, undefined, and a plain object; null/undefined map to the neutral placeholder, not the empty string", () => {
    expect(() => displaySafe(null)).not.toThrow();
    expect(() => displaySafe(undefined)).not.toThrow();
    expect(() => displaySafe({ foo: "bar" })).not.toThrow();
    expect(displaySafe(null)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(undefined)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe({ foo: "bar" })).toBe("");
  });

  it("coerces a number to its string form instead of throwing", () => {
    expect(displaySafe(42)).toBe("42");
  });

  it("strips C0 controls including BEL and ESC without throwing", () => {
    const input = `a${ch(0x00)}b${ch(0x07)}c${ch(0x1b)}d`;
    expect(() => displaySafe(input)).not.toThrow();
    expect(displaySafe(input)).toBe(`a${REPLACEMENT}b${REPLACEMENT}c${REPLACEMENT}d`);
  });

  it("bounds an extremely long string instead of returning it unbounded", () => {
    const input = "a".repeat(100_000);
    expect(() => displaySafe(input)).not.toThrow();
    expect(displaySafe(input).length).toBeLessThan(input.length);
  });

  it("neutralizes an HTML/script payload so no live tag substring survives", () => {
    const scriptPayload = "before<script>alert(1)</script>after";
    expect(() => displaySafe(scriptPayload)).not.toThrow();
    const result = displaySafe(scriptPayload);
    expect(result).not.toContain("<script>");
    expect(result).not.toContain("</script>");

    const imgPayload = "<img src=x onerror=alert(1)>";
    expect(displaySafe(imgPayload)).not.toContain("<img");
  });

  it("leaves a lone less-than/greater-than sign in ordinary prose untouched", () => {
    const input = "income < 50,000 and balance > 10,000";
    expect(displaySafe(input)).toBe(input);
  });

  it("coerces a genuine falsy number (0) to its string form, but maps non-finite numbers to the neutral placeholder", () => {
    expect(() => displaySafe(0)).not.toThrow();
    expect(() => displaySafe(NaN)).not.toThrow();
    expect(displaySafe(0)).toBe("0");
    expect(displaySafe(NaN)).toBe(NEUTRAL_PLACEHOLDER);
  });

  it("coerces booleans to their string form instead of throwing", () => {
    expect(() => displaySafe(true)).not.toThrow();
    expect(() => displaySafe(false)).not.toThrow();
    expect(displaySafe(true)).toBe("true");
    expect(displaySafe(false)).toBe("false");
  });

  it("falls back to an empty string for an array instead of throwing", () => {
    expect(() => displaySafe([])).not.toThrow();
    expect(() => displaySafe(["<script>alert(1)</script>"])).not.toThrow();
    expect(displaySafe([])).toBe("");
    expect(displaySafe(["<script>alert(1)</script>"])).toBe("");
  });

  it("coerces a bigint to its string form instead of throwing", () => {
    expect(() => displaySafe(BigInt(42))).not.toThrow();
    expect(displaySafe(BigInt(42))).toBe("42");
  });

  it("coerces a symbol to its descriptive string form instead of throwing", () => {
    const sym = Symbol("claim-id");
    expect(() => displaySafe(sym)).not.toThrow();
    expect(displaySafe(sym)).toBe("Symbol(claim-id)");
  });

  it("never throws for an object whose toString/valueOf are hostile", () => {
    const hostile = {
      toString() {
        throw new Error("toString exploded");
      },
      valueOf() {
        throw new Error("valueOf exploded");
      }
    };
    expect(() => displaySafe(hostile)).not.toThrow();
    expect(displaySafe(hostile)).toBe("");
  });

  it("never throws for any malformed or non-string input across a type-safety sweep", () => {
    const badInputs: unknown[] = [null, undefined, 0, NaN, {}, [], true, false];
    for (const bad of badInputs) {
      expect(() => displaySafe(bad)).not.toThrow();
      expect(typeof displaySafe(bad)).toBe("string");
    }
  });

  it("neutralizes a javascript: URI payload so no raw tag or handler attribute is introduced", () => {
    const uriPayload = "javascript:void(0)";
    expect(() => displaySafe(uriPayload)).not.toThrow();
    const result = displaySafe(uriPayload);
    expect(result).not.toContain("<script");
    expect(result).not.toContain("onerror=");
  });

  it("does not re-introduce a live tag from an already-escaped HTML entity", () => {
    const escapedPayload = "&lt;script&gt;alert(1)&lt;/script&gt;";
    expect(() => displaySafe(escapedPayload)).not.toThrow();
    const result = displaySafe(escapedPayload);
    expect(result).not.toContain("<script");
    expect(result).not.toContain("onerror=");
  });

  it("strips the onerror handler along with the rest of an img payload's tag", () => {
    const imgPayload = "<img src=x onerror=alert(1)>";
    expect(() => displaySafe(imgPayload)).not.toThrow();
    const result = displaySafe(imgPayload);
    expect(result).not.toContain("<img");
    expect(result).not.toContain("onerror=");
  });
});

describe("displaySafe — degenerate-input honesty (never blank, never affirmative-looking)", () => {
  it("maps null and undefined to the neutral placeholder, never the empty string", () => {
    expect(displaySafe(null)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(undefined)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(null)).not.toBe("");
    expect(displaySafe(undefined)).not.toBe("");
  });

  it("maps NaN and (positive/negative) Infinity to the neutral placeholder instead of a confusing literal token", () => {
    expect(displaySafe(NaN)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(Infinity)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(-Infinity)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(NaN)).not.toBe("");
    expect(displaySafe(Infinity)).not.toBe("");
  });

  it("never returns the empty string for any type-degenerate input, across a sweep", () => {
    const degenerate: unknown[] = [null, undefined, NaN, Infinity, -Infinity];
    for (const value of degenerate) {
      const result = displaySafe(value);
      expect(result).not.toBe("");
      expect(result).toBe(NEUTRAL_PLACEHOLDER);
    }
  });

  it("still passes a genuine finite number and a genuine boolean through unchanged (non-regression)", () => {
    expect(displaySafe(0)).toBe("0");
    expect(displaySafe(42)).toBe("42");
    expect(displaySafe(-3.5)).toBe("-3.5");
    expect(displaySafe(true)).toBe("true");
    expect(displaySafe(false)).toBe("false");
  });

  // displaySafe is applied per-character to slices of the lawyer's own
  // draft_text in WorkspaceMargin.tsx (e.g. the single space between two
  // adjacent claim spans is a real, common segment). A literal empty or
  // whitespace-only STRING is genuine document content, not a missing value,
  // so — unlike the type-degenerate cases above — it is intentionally exempt
  // from placeholder substitution and must stay byte-for-byte unchanged to
  // keep claim-span offsets aligned (the 1-to-1 length-preserving contract
  // documented at the top of displaySafe.ts).
  it("still passes genuine string content through unchanged, including a real empty or whitespace-only segment (non-regression)", () => {
    expect(displaySafe("")).toBe("");
    expect(displaySafe("   ")).toBe("   ");
    expect(displaySafe("The fee was upheld as lawful.")).toBe("The fee was upheld as lawful.");
  });
});

// displaySafe's real contract is `displaySafe(text: unknown): string` — a pure
// display-text sanitizer with no verdict/discriminant shape (verdict
// interpretation lives in claimDisposition.ts, not here). Each class below is
// mapped onto this module's actual argument space; where a class describes a
// shape this module has no concept of (an object's "verdict" field, a
// "SUPPORTED" enum), the closest applicable behavior is asserted instead:
// displaySafe must never throw, must never fabricate an affirmative-looking
// value from a degenerate input, and must never mutate a verdict-shaped
// string into a different one, since interpreting verdicts is out of scope
// for a character sanitizer.
describe("displaySafe — exhaustive input-class contract (classes 1-10)", () => {
  it("class 1: argument is null — no throw, resolves to the neutral placeholder, not an affirmative string", () => {
    expect(() => displaySafe(null)).not.toThrow();
    const result = displaySafe(null);
    expect(typeof result).toBe("string");
    expect(result).toBe(NEUTRAL_PLACEHOLDER);
  });

  it("class 2: argument is undefined — no throw, resolves to the neutral placeholder, not an affirmative string", () => {
    expect(() => displaySafe(undefined)).not.toThrow();
    const result = displaySafe(undefined);
    expect(typeof result).toBe("string");
    expect(result).toBe(NEUTRAL_PLACEHOLDER);
  });

  it("class 3: argument is an empty object {} — no throw, resolves to a defined safe fallback, not an affirmative string", () => {
    expect(() => displaySafe({})).not.toThrow();
    const result = displaySafe({});
    expect(typeof result).toBe("string");
    expect(result).toBe("");
  });

  it("class 4: argument is an object with no recognizable/discriminant shape — no throw, safe fallback", () => {
    const noShape = { unrelated: "field", nested: { a: 1 } };
    expect(() => displaySafe(noShape)).not.toThrow();
    const result = displaySafe(noShape);
    expect(typeof result).toBe("string");
    expect(result).toBe("");
  });

  it("class 5: a malformed/unknown verdict-shaped enum string passes through verbatim as text, never mutated into a different rendering", () => {
    // displaySafe has no verdict semantics, so the honesty test here is that it
    // never SILENTLY REWRITES a verdict-shaped string into something else (which
    // would be the analogous failure to "rendering unsupported as verified") —
    // proving byte-for-byte equality is the strongest form of that guarantee.
    const enumLikeStrings = ["SUPPORTED", "maybe", "", "verified ", "VeRiFiEd"];
    for (const value of enumLikeStrings) {
      expect(() => displaySafe(value)).not.toThrow();
      const result = displaySafe(value);
      expect(typeof result).toBe("string");
      expect(result).toBe(value);
    }
  });

  it("class 6: wrong-type arguments (number, boolean, array, object, NaN) never throw and never render as an affirmative verified/supported string", () => {
    const wrongTyped: unknown[] = [42, true, false, [], {}, NaN];
    for (const value of wrongTyped) {
      expect(() => displaySafe(value)).not.toThrow();
      const result = displaySafe(value);
      expect(typeof result).toBe("string");
      expect(result).not.toMatch(/verified|supported/i);
    }
  });

  it("class 7: string-typed content — undefined/null/empty/wrong-type all resolve safely; genuine empty string passes through unchanged", () => {
    expect(displaySafe(undefined)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(null)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe("")).toBe(""); // genuine empty string content, not a missing value
    expect(displaySafe(123)).toBe("123"); // wrong type (number) coerces safely
    expect(displaySafe({})).toBe(""); // wrong type (object) falls back safely
  });

  it("class 8: numeric edge values (NaN, Infinity, -Infinity, non-number types) all resolve safely, never throw", () => {
    expect(() => displaySafe(NaN)).not.toThrow();
    expect(() => displaySafe(Infinity)).not.toThrow();
    expect(() => displaySafe(-Infinity)).not.toThrow();
    expect(() => displaySafe("not-a-number")).not.toThrow();
    expect(displaySafe(NaN)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(Infinity)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe(-Infinity)).toBe(NEUTRAL_PLACEHOLDER);
    expect(displaySafe("not-a-number")).toBe("not-a-number");
  });

  it("class 9: array-typed arguments — undefined, null, empty, and arrays containing null/malformed elements all resolve safely without throwing", () => {
    const arrayLikeInputs: unknown[] = [undefined, null, [], [null, undefined, {}, "text", 42], [[1, 2], [null]]];
    for (const value of arrayLikeInputs) {
      expect(() => displaySafe(value)).not.toThrow();
      expect(typeof displaySafe(value)).toBe("string");
    }
    expect(displaySafe([])).toBe("");
    expect(displaySafe([null, undefined, {}, "text", 42])).toBe("");
  });

  it("class 10: control characters and unusually long input never throw; truncation and control-char replacement both apply safely", () => {
    const controlHeavy = `${ch(0x00)}${ch(0x07)}${ch(0x1b)}`.repeat(1000);
    expect(() => displaySafe(controlHeavy)).not.toThrow();
    expect(displaySafe(controlHeavy)).toBe(REPLACEMENT.repeat(3000));

    const veryLong = "x".repeat(200_000);
    expect(() => displaySafe(veryLong)).not.toThrow();
    expect(displaySafe(veryLong).length).toBeLessThanOrEqual(50_000);

    const veryLongWithControls = `${ch(0x00)}`.repeat(60_000);
    expect(() => displaySafe(veryLongWithControls)).not.toThrow();
    const result = displaySafe(veryLongWithControls);
    expect(result.length).toBeLessThanOrEqual(50_000);
  });
});
