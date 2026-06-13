import { render } from "@testing-library/preact";
import { describe, expect, it } from "vitest";

import { applyInert, inertSiblings, restoreInert, useInert } from "./useInert";

function SelfInert({ active }: { active: boolean }) {
  const ref = useInert<HTMLDivElement>(active);
  return (
    <div ref={ref} data-testid="self">
      content
    </div>
  );
}

describe("useInert", () => {
  it("marks the node inert + aria-hidden while active and restores on deactivate", () => {
    const { rerender, getByTestId } = render(<SelfInert active />);
    expect(getByTestId("self").hasAttribute("inert")).toBe(true);
    expect(getByTestId("self").getAttribute("aria-hidden")).toBe("true");

    rerender(<SelfInert active={false} />);
    expect(getByTestId("self").hasAttribute("inert")).toBe(false);
    expect(getByTestId("self").hasAttribute("aria-hidden")).toBe(false);
  });
});

describe("applyInert / restoreInert", () => {
  it("restores the exact prior attributes, not a blanket removal", () => {
    const el = document.createElement("div");
    el.setAttribute("aria-hidden", "false"); // a pre-existing value must survive
    const prior = applyInert(el);
    expect(el.getAttribute("inert")).toBe("");
    expect(el.getAttribute("aria-hidden")).toBe("true");
    restoreInert(prior);
    expect(el.hasAttribute("inert")).toBe(false);
    expect(el.getAttribute("aria-hidden")).toBe("false");
  });
});

describe("inertSiblings", () => {
  it("inerts every sibling (never the node itself) and the cleanup restores them", () => {
    const parent = document.createElement("div");
    const a = document.createElement("nav");
    const b = document.createElement("section");
    const overlay = document.createElement("div");
    parent.append(a, b, overlay);
    document.body.appendChild(parent);

    const cleanup = inertSiblings(overlay);
    expect(a.hasAttribute("inert")).toBe(true);
    expect(b.getAttribute("aria-hidden")).toBe("true");
    expect(overlay.hasAttribute("inert")).toBe(false);

    cleanup();
    expect(a.hasAttribute("inert")).toBe(false);
    expect(b.hasAttribute("aria-hidden")).toBe(false);

    parent.remove();
  });
});
