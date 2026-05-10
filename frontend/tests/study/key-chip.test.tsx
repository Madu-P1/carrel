import { render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, test } from "vitest";

import { KeyChip } from "@/features/study/components/KeyChip";

describe("KeyChip (PR 3)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("renders one chip per key", () => {
    render(<KeyChip keys={["Space"]} />);
    expect(screen.getByText("Space")).toBeDefined();
  });

  test("renders four chips for the rating keys", () => {
    const { container } = render(<KeyChip keys={["1", "2", "3", "4"]} />);
    ["1", "2", "3", "4"].forEach((k) => {
      expect(screen.getByText(k)).toBeDefined();
    });
    // The brackets are visual via CSS border, not text content — the
    // accessibility tree should not pronounce them. The wrapper carries
    // aria-hidden so SR users skip the cue entirely (they already know
    // the keys via aria-keyshortcuts on the rating buttons themselves).
    const wrap = container.firstElementChild as HTMLElement | null;
    expect(wrap?.getAttribute("aria-hidden")).toBe("true");
  });

  test("optional label renders before the chips", () => {
    render(<KeyChip keys={["Space"]} label="reveal" />);
    expect(screen.getByText("reveal")).toBeDefined();
  });

  test("dimmed prop toggles the dimmed class on the wrapper", () => {
    const { container, rerender } = render(<KeyChip keys={["Space"]} />);
    const wrapNoDim = container.firstElementChild as HTMLElement;
    expect(wrapNoDim.className.includes("dimmed")).toBe(false);

    rerender(<KeyChip keys={["Space"]} dimmed={true} />);
    const wrapDim = container.firstElementChild as HTMLElement;
    expect(wrapDim.className.includes("dimmed")).toBe(true);
  });

  test("empty keys array renders nothing", () => {
    const { container } = render(<KeyChip keys={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
