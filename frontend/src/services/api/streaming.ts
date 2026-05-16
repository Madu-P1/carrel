import {
  API_BASE,
  ApiError,
  BackendOfflineError,
  LOCAL_TOKEN_HEADER,
  resolveLocalApiToken
} from "./client";

/**
 * fetch-based Server-Sent Events consumer. Pattern imported from
 * Next.js examples/with-ai-sdk family (token-by-token streaming with
 * Suspense fallback), with the Suspense half stripped out: Carrel's
 * `preact/compat` `Suspense` + `lazy()` is broken under `file://`
 * (CLAUDE.md "Open debts"). Plain async iteration into a signal works
 * fine and is what the AskView pattern already uses.
 *
 * Why fetch and not `EventSource`: `EventSource` can't set custom
 * request headers, so it cannot carry the local-API token. The
 * backend gates `/api/*` (except `/api/health`) on the
 * `X-Carrel-Local-Token` header. fetch + ReadableStream is the only
 * path that keeps the auth invariant intact.
 */

export interface StreamSseOptions {
  signal?: AbortSignal;
  /** Override the default `JSON.parse`. Use to swap in lenient parsers
   *  for partial frames, or to keep raw strings without decoding. */
  decode?: (raw: string) => unknown;
}

/**
 * Open a streaming POST to `path` with `body`, and yield each decoded
 * SSE payload as it arrives. The stream is exhausted when the server
 * emits `data: [DONE]` or closes the connection.
 *
 * Throws on transport failure: `BackendOfflineError` for connect
 * failures, `ApiError` for non-2xx HTTP, or anything `decode` raises.
 */
export async function* streamSse<T = unknown>(
  path: string,
  body: object | undefined,
  opts: StreamSseOptions = {}
): AsyncGenerator<T, void, void> {
  const token = await resolveLocalApiToken();
  const decode = opts.decode ?? ((raw: string) => JSON.parse(raw));

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream",
        ...(token ? { [LOCAL_TOKEN_HEADER]: token } : {})
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: opts.signal
    });
  } catch (cause) {
    throw new BackendOfflineError(cause);
  }

  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = undefined;
    }
    throw new ApiError(response.status, response.statusText, payload);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new ApiError(500, "no response body", undefined);
  }

  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let frameEnd = buffer.indexOf("\n\n");
      while (frameEnd !== -1) {
        const frame = buffer.slice(0, frameEnd);
        buffer = buffer.slice(frameEnd + 2);
        for (const line of frame.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (payload === "") continue;
          if (payload === "[DONE]") return;
          yield decode(payload) as T;
        }
        frameEnd = buffer.indexOf("\n\n");
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // releaseLock can throw if the reader was already closed; ignore.
    }
  }
}

/**
 * Sugar over `streamSse` for the Carrel tutor stream shape, where
 * each chunk is `{"text": "..."}` or `{"error": "..."}`. Yields just
 * the text deltas; throws on the first `error` frame.
 */
export async function* streamTextDeltas(
  path: string,
  body: object,
  opts?: StreamSseOptions
): AsyncGenerator<string, void, void> {
  for await (const chunk of streamSse<{ text?: string; error?: string }>(path, body, opts)) {
    if (chunk.error) {
      throw new Error(chunk.error);
    }
    if (typeof chunk.text === "string" && chunk.text.length > 0) {
      yield chunk.text;
    }
  }
}
