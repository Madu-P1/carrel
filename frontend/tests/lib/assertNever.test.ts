import { describe, expect, it } from "vitest";

import { assertNever } from "@/lib/assertNever";

describe("assertNever", () => {
  it("throws when reached at runtime (cast bypass)", () => {
    expect(() => assertNever("unexpected" as never)).toThrow(/Unhandled discriminant/);
  });

  it("rejects non-never values at the type level", () => {
    const x = "hello";
    // @ts-expect-error string is not assignable to never
    const fn = () => assertNever(x);
    expect(fn).toBeTypeOf("function");
  });

  it("compiles when every case of a 3-member union is handled", () => {
    type Color = "red" | "green" | "blue";
    function name(c: Color): string {
      switch (c) {
        case "red":
          return "R";
        case "green":
          return "G";
        case "blue":
          return "B";
        default:
          return assertNever(c);
      }
    }
    expect(name("red")).toBe("R");
    expect(name("green")).toBe("G");
    expect(name("blue")).toBe("B");
  });
});
