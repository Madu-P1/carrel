import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { ImportDropzone } from "../../src/features/library/components/ImportDropzone";
import { getFetchCalls, mockJson } from "../support/mockFetch";

test("ImportDropzone uploads dropped files and calls onUploaded", async () => {
  const onUploaded = vi.fn();
  mockJson("POST", "/api/documents/upload", () => ({
    confidence: 0.88,
    doc_id: crypto.randomUUID(),
    filename: "uploaded.pdf"
  }));

  render(<ImportDropzone onUploaded={onUploaded} />);

  const files = [
    new File(["alpha"], "alpha.txt", { type: "text/plain" }),
    new File(["beta"], "beta.txt", { type: "text/plain" })
  ];

  fireEvent.drop(screen.getByText(/Drop files here to ingest them/i).closest("div")!, {
    dataTransfer: { files }
  });

  await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
  expect(getFetchCalls().filter((call) => call.url.endsWith("/api/documents/upload"))).toHaveLength(2);
});

test("ImportDropzone choose-files flow triggers the hidden input and uploads on change", async () => {
  const onUploaded = vi.fn();
  mockJson("POST", "/api/documents/upload", {
    confidence: 0.88,
    doc_id: "doc-1",
    filename: "uploaded.pdf"
  });

  render(<ImportDropzone onUploaded={onUploaded} />);

  const input = document.getElementById("library-import-input") as HTMLInputElement;
  const clickSpy = vi.spyOn(input, "click");

  fireEvent.click(screen.getByRole("button", { name: /Or choose files/i }));
  expect(clickSpy).toHaveBeenCalledTimes(1);

  Object.defineProperty(input, "files", {
    configurable: true,
    value: [new File(["hello"], "hello.txt", { type: "text/plain" })]
  });
  fireEvent.change(input);

  await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
});
