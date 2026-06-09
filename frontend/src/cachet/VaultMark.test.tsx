import { render } from "@testing-library/preact";
import { describe, expect, it } from "vitest";

import { VaultMark } from "./VaultMark";

// The mark's gradients and clip are wired by SVG url(#id) references. Those ids
// must be render-pure: minting a new id on every render churns the defs and can
// strand paint-server references mid-update. They must also be unique per
// instance so two folders on one screen never cross-reference fills.

function gradientId(container: Element): string {
  return container.querySelector("linearGradient")?.getAttribute("id") ?? "";
}

describe("VaultMark id stability", () => {
  it("keeps its gradient ids stable across re-renders (render purity)", () => {
    const { container, rerender } = render(<VaultMark size={28} />);
    const first = gradientId(container);
    expect(first).not.toBe("");
    rerender(<VaultMark size={34} />);
    expect(gradientId(container)).toBe(first);
  });

  it("gives two instances distinct ids (no cross-instance fill bleed)", () => {
    const a = render(<VaultMark />);
    const b = render(<VaultMark />);
    expect(gradientId(a.container)).not.toBe(gradientId(b.container));
  });

  it("the face fill actually references the instance's own gradient", () => {
    const { container } = render(<VaultMark />);
    const id = gradientId(container);
    const fills = Array.from(container.querySelectorAll("path")).map(
      (p) => p.getAttribute("fill") ?? ""
    );
    expect(fills.some((f) => f === `url(#${id})`)).toBe(true);
  });
});
