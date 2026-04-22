import { render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

vi.mock("pdfjs-dist", () => {
  const GlobalWorkerOptions = { workerSrc: "" };
  const pdf = {
    destroy: vi.fn(),
    getDestination: vi.fn(async () => [{ gen: 0, num: 1 }]),
    getOutline: vi.fn(async () => [{ dest: [{ gen: 0, num: 1 }], items: [], title: "Overview" }]),
    getPageIndex: vi.fn(async () => 1),
    numPages: 7
  };

  return {
    GlobalWorkerOptions,
    TextLayer: class {
      async render() {
        return undefined;
      }
    },
    getDocument: vi.fn(() => ({
      destroy: vi.fn(async () => undefined),
      promise: Promise.resolve(pdf)
    }))
  };
});

import { usePdfDocument } from "../../src/features/reader/hooks/usePdfDocument";

function Probe() {
  const state = usePdfDocument("http://127.0.0.1:8000/example.pdf");

  return (
    <div>
      <output data-testid="pages">{String(state.pageCount.value)}</output>
      <output data-testid="outline">{state.outline.value.map((item) => item.title).join(",")}</output>
      <output data-testid="loading">{String(state.loading.value)}</output>
    </div>
  );
}

test("usePdfDocument loads page count and outline from pdfjs", async () => {
  render(<Probe />);

  await waitFor(() => {
    expect(screen.getByTestId("pages").textContent).toBe("7");
  });

  await waitFor(() => {
    expect(screen.getByTestId("outline").textContent).toBe("Overview");
  });
  expect(screen.getByTestId("loading").textContent).toBe("false");
});
