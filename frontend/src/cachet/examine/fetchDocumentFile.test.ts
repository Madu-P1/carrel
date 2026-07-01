import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchDocumentFile } from "./fetchDocumentFile";

function jsonHeaders(contentType: string | null): Headers {
  const headers = new Headers();
  if (contentType) headers.set("content-type", contentType);
  return headers;
}

describe("fetchDocumentFile", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("rejects with a typed, catchable error when the network request fails", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(fetchDocumentFile("doc-1")).rejects.toThrow(
      "The engine is not reachable. Start Cachet's engine, then reopen the record."
    );
  });

  it("rejects with a named-cause error on a 404 response", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(null, { status: 404, statusText: "Not Found" })
    );

    await expect(fetchDocumentFile("doc-1")).rejects.toThrow(
      "The original file for this record is no longer in the Vault."
    );
  });

  it("rejects with a named-cause error on a 500 response", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(null, { status: 500, statusText: "Internal Server Error" })
    );

    await expect(fetchDocumentFile("doc-1")).rejects.toThrow(
      "The record file could not be opened (HTTP 500)."
    );
  });

  it("rejects with a named-cause error on an ok response with an empty body", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(new ArrayBuffer(0), { status: 200, headers: jsonHeaders("application/pdf") })
    );

    await expect(fetchDocumentFile("doc-1")).rejects.toThrow(
      "The original file for this record is empty."
    );
  });

  it("rejects with a typed error when the body stream cannot be read", async () => {
    const response = new Response(new ArrayBuffer(4), { status: 200 });
    vi.spyOn(response, "arrayBuffer").mockRejectedValue(new Error("stream aborted"));
    vi.mocked(fetch).mockResolvedValue(response);

    await expect(fetchDocumentFile("doc-1")).rejects.toThrow(
      "The record file could not be read from the engine."
    );
  });

  it("resolves to the raw bytes on a valid 200 response with a real body", async () => {
    const bytes = new Uint8Array([1, 2, 3, 4]).buffer;
    vi.mocked(fetch).mockResolvedValue(
      new Response(bytes, { status: 200, headers: jsonHeaders("application/pdf") })
    );

    const result = await fetchDocumentFile("doc-1");

    expect(new Uint8Array(result)).toEqual(new Uint8Array([1, 2, 3, 4]));
  });

  it("never produces an unhandled rejection on any failure path", async () => {
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandled);

    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));
    await fetchDocumentFile("doc-1").catch(() => undefined);

    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 404 }));
    await fetchDocumentFile("doc-1").catch(() => undefined);

    vi.mocked(fetch).mockResolvedValue(new Response(new ArrayBuffer(0), { status: 200 }));
    await fetchDocumentFile("doc-1").catch(() => undefined);

    // Give the microtask queue a chance to surface any rejection we missed.
    await new Promise((resolve) => setTimeout(resolve, 0));

    process.off("unhandledRejection", onUnhandled);
    expect(unhandled).toEqual([]);
  });
});
