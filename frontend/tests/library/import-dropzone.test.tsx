import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { ImportDropzone } from "../../src/features/library/components/ImportDropzone";
import { getFetchCalls, jsonResponse, mockJson, registerFetchHandler } from "../support/mockFetch";

function jobResponse(id: string, filename: string, documentId: string | null = null) {
  return {
    job: {
      id,
      kind: "import",
      status: "queued",
      stage: "importing",
      filename,
      subject_name: "General",
      document_id: documentId,
      error: null,
      progress: 0,
      created_at: null,
      updated_at: null,
      started_at: null,
      finished_at: null
    }
  };
}

test("ImportDropzone uploads dropped files and calls onUploaded", async () => {
  const onUploaded = vi.fn();
  mockJson("POST", "/api/jobs/import", () =>
    jobResponse(crypto.randomUUID(), "uploaded.pdf", crypto.randomUUID())
  );

  render(<ImportDropzone onUploaded={onUploaded} />);

  const files = [
    new File(["alpha"], "alpha.txt", { type: "text/plain" }),
    new File(["beta"], "beta.txt", { type: "text/plain" })
  ];

  fireEvent.drop(screen.getByText(/Drop files here to ingest them/i).closest("div")!, {
    dataTransfer: { files }
  });

  await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
  expect(getFetchCalls().filter((call) => call.url.endsWith("/api/jobs/import"))).toHaveLength(2);
});

test("ImportDropzone sends the selected subject folder with uploads", async () => {
  const onUploaded = vi.fn();
  mockJson("POST", "/api/jobs/import", jobResponse("job-1", "uploaded.csv", "doc-1"));

  render(<ImportDropzone onUploaded={onUploaded} />);

  fireEvent.input(screen.getByLabelText(/Subject folder/i), {
    currentTarget: { value: "Finance" },
    target: { value: "Finance" }
  });
  fireEvent.drop(screen.getByText(/Drop files here to ingest them/i).closest("div")!, {
    dataTransfer: { files: [new File(["review,score\nMilan,5"], "milan_reviews.csv", { type: "text/csv" })] }
  });

  await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
  const importCall = getFetchCalls().find((call) => call.url.endsWith("/api/jobs/import"));
  expect(importCall?.body).toBeInstanceOf(FormData);
  expect((importCall?.body as FormData).get("subject_name")).toBe("Finance");
});

test("ImportDropzone can create a subject folder before import", async () => {
  const onSubjectCreated = vi.fn().mockResolvedValue(undefined);

  render(
    <ImportDropzone
      onSubjectCreated={onSubjectCreated}
      onUploaded={vi.fn()}
      subjectOptions={["General", "Finance"]}
    />
  );

  fireEvent.input(screen.getByLabelText(/Subject folder/i), {
    currentTarget: { value: "Marketing" },
    target: { value: "Marketing" }
  });
  fireEvent.click(screen.getByRole("button", { name: /Create folder/i }));

  await waitFor(() => expect(onSubjectCreated).toHaveBeenCalledWith("Marketing"));
});

test("ImportDropzone choose-files flow triggers the hidden input and uploads on change", async () => {
  const onUploaded = vi.fn();
  mockJson("POST", "/api/jobs/import", jobResponse("job-1", "uploaded.pdf", "doc-1"));

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

test("ImportDropzone shows backend upload detail instead of a generic bad-request label", async () => {
  const onUploaded = vi.fn();
  registerFetchHandler((url, init) => {
    if (!url.pathname.endsWith("/api/jobs/import") || init.method !== "POST") {
      return undefined;
    }
    return jsonResponse(
      { detail: "Unsupported file type. Supported types: .csv, .pdf, .xlsx." },
      400
    );
  });

  render(<ImportDropzone onUploaded={onUploaded} />);

  fireEvent.drop(screen.getByText(/Drop files here to ingest them/i).closest("div")!, {
    dataTransfer: { files: [new File(["x"], "milan_reviews.csv", { type: "text/csv" })] }
  });

  expect(await screen.findByText(/Unsupported file type/i)).toBeDefined();
  expect(screen.queryByText(/API 400 Bad Request/i)).toBeNull();
});

test("ImportDropzone surfaces a Retry button after a failed upload; clicking it re-uploads just the failed files", async () => {
  const onUploaded = vi.fn();
  let uploadAttempts = 0;
  // First upload call fails with 500; second (the retry) succeeds.
  registerFetchHandler((url, init) => {
    if (!url.pathname.endsWith("/api/jobs/import") || init.method !== "POST") {
      return undefined;
    }
    uploadAttempts += 1;
    if (uploadAttempts === 1) {
      return jsonResponse({ detail: "server went sideways" }, 500);
    }
    return jsonResponse(jobResponse("job-retry-ok", "retry.txt", "doc-retry-ok"));
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
    if (!url.pathname.endsWith("/api/jobs/import") || init.method !== "POST") {
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
