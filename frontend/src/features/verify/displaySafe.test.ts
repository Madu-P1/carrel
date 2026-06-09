import { describe, expect, it } from "vitest";

import { displaySafe } from "./displaySafe";

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
});
