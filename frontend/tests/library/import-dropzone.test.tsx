import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { ImportDropzone } from "../../src/features/library/components/ImportDropzone";
import { getFetchCalls, jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

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

test("ImportDropzone surfaces a Retry button after a failed upload; clicking it re-uploads just the failed files", async () => {
  const onUploaded = vi.fn();
  let uploadAttempts = 0;
  // First upload call fails with 500; second (the retry) succeeds.
  registerFetchHandler((url, init) => {
    if (!url.pathname.endsWith("/api/documents/upload") || init.method !== "POST") {
      return undefined;
    }
    uploadAttempts += 1;
    if (uploadAttempts === 1) {
      return jsonResponse({ detail: "server went sideways" }, 500);
    }
    return jsonResponse({ confidence: 0.9, doc_id: "doc-retry-ok", filename: "retry.txt" });
  });

  render(<ImportDropzone onUploaded={onUploaded} />);

  const dropzone = screen.getByText(/Drop files here to ingest them/i).closest("div")!;
  fireEvent.drop(dropzone, {
    dataTransfer: { files: [new File(["boom"], "retry.txt", { type: "text/plain" })] }
  });

  // After the failure, a "Retry 1 failed file" button renders in the outcome.
  const retryBtn = await screen.findByRole("button", { name: /Retry 1 failed file/i });
  expect(retryBtn).toBeDefined();
  // onUploaded NOT called yet because the first attempt fully failed.
  expect(onUploaded).not.toHaveBeenCalled();

  fireEvent.click(retryBtn);
  await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
  expect(uploadAttempts).toBe(2);
});

test("ImportDropzone keeps duplicates behind a disclosure and doesn't offer Retry for them", async () => {
  const onUploaded = vi.fn();
  registerFetchHandler((url, init) => {
    if (!url.pathname.endsWith("/api/documents/upload") || init.method !== "POST") {
      return undefined;
    }
    return jsonResponse(
      {
        detail: {
          code: "duplicate_source",
          message: "Already in library",
          existing_doc_id: "doc-existing",
          existing_filename: "dup.txt",
          existing_subject: "Biology"
        }
      },
      409
    );
  });

  render(<ImportDropzone onUploaded={onUploaded} />);

  fireEvent.drop(screen.getByText(/Drop files here to ingest them/i).closest("div")!, {
    dataTransfer: { files: [new File(["x"], "dup.txt", { type: "text/plain" })] }
  });

  // The quiet disclosure summary is visible...
  const dupSummary = await screen.findByText(/1 duplicate skipped/);
  expect(dupSummary).toBeDefined();
  // ...and no Retry button appears because duplicates aren't retriable.
  expect(screen.queryByRole("button", { name: /Retry/i })).toBeNull();
});
