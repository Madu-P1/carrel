import { describe, expect, it, vi } from "vitest";

import { registerFetchHandler } from "../../tests/support/mockFetch";
import { subscribeSse } from "./sse";

function eventStreamResponse(frame: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(frame));
      controller.close();
    }
  });
  return new Response(stream, {
    status: 200,
    headers: { "content-type": "text/event-stream" }
  });
}

function requireUrl(value: URL | null): URL {
  if (!value) throw new Error("Expected SSE fetch URL to be captured");
  return value;
}

describe("subscribeSse", () => {
  it("uses the local API header without putting the token in the URL", async () => {
    let capturedUrl: URL | null = null;
    let capturedHeaders: HeadersInit | undefined;

    registerFetchHandler((url, init) => {
      if (url.pathname !== "/api/jobs/stream") return undefined;
      capturedUrl = url;
      capturedHeaders = init.headers;
      return eventStreamResponse('id: 7\nevent: job\ndata: {"id":7}\n\n');
    });

    const onJob = vi.fn();
    const unsubscribe = subscribeSse("http://127.0.0.1:8000/api/jobs/stream?after_id=3", "job", onJob);

    await vi.waitFor(() => {
      expect(onJob).toHaveBeenCalledTimes(1);
    });
    unsubscribe();

    const url = requireUrl(capturedUrl);
    expect(url.searchParams.get("after_id")).toBe("3");
    expect(url.searchParams.has("token")).toBe(false);
    expect(capturedHeaders).toMatchObject({ "X-Carrel-Local-Token": "test-local-token" });
    expect(onJob.mock.calls[0]?.[0].data).toBe('{"id":7}');
    expect(onJob.mock.calls[0]?.[0].lastEventId).toBe("7");
  });
});
