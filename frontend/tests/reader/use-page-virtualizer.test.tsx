import { render, screen, waitFor } from "@testing-library/preact";
import { useRef } from "preact/hooks";
import { expect, test } from "vitest";

import { usePageVirtualizer } from "../../src/features/reader/hooks/usePageVirtualizer";

function VirtualizerProbe() {
  const ref = useRef<HTMLDivElement>(null);
  const { visiblePages } = usePageVirtualizer({
    containerRef: ref,
    pageCount: 50,
    pageHeight: 100
  });

  return (
    <div
      data-testid="viewport"
      ref={(node) => {
        ref.current = node;
        if (node) {
          Object.defineProperty(node, "clientHeight", {
            configurable: true,
            value: 300
          });
        }
      }}
      style={{ height: "300px", overflow: "auto" }}
    >
      <output data-testid="visible">{visiblePages.join(",")}</output>
    </div>
  );
}

test("usePageVirtualizer computes a visible page window from scroll position", async () => {
  render(<VirtualizerProbe />);

  await waitFor(() => {
    expect(screen.getByTestId("visible").textContent).toContain("1,2,3,4,5");
  });

  const viewport = screen.getByTestId("viewport");
  Object.defineProperty(viewport, "scrollTop", {
    configurable: true,
    value: 400,
    writable: true
  });
  viewport.dispatchEvent(new Event("scroll"));

  await waitFor(() => {
    expect(screen.getByTestId("visible").textContent).toContain("4,5,6,7,8");
  });
});
