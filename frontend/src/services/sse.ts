/**
 * Shared SSE multiplexer.
 *
 * Before this module, four separate features (jobs feed, plan view,
 * dashboard insertions, companion alarm) each built their own stream
 * connection + reconnect + handler tree against the same backend
 * stream. That meant up to 4 simultaneous connections to one URL,
 * 4 reconnect loops, 4 separate sets of bugs to keep in sync.
 *
 * Now everything that wants to listen calls `subscribeSse(url, event,
 * cb)` and gets an unsubscribe function back. The multiplexer keeps a
 * single fetch stream per URL, fans events out, and auto-reconnects
 * with exponential backoff when the underlying socket dies. When the
 * last subscriber for a URL leaves, the connection is closed and the
 * URL slot is freed.
 *
 * Auth uses the same `X-Carrel-Local-Token` header as normal API
 * calls. EventSource cannot send that header, so this module consumes
 * SSE over fetch + ReadableStream instead of putting the long-lived
 * token in the URL.
 */

import { LOCAL_TOKEN_HEADER, resolveLocalApiToken } from "./api/client";

interface Channel {
  controller: AbortController | null;
  /** Map of event-name → set of callbacks. Outer map is keyed by
   *  event name so dispatch can fan out without each callback having
   *  to filter the event type itself. */
  listeners: Map<string, Set<(ev: MessageEvent) => void>>;
  /** Backoff schedule for the next reconnect attempt. Resets on a
   *  successful open. */
  reconnectMs: number;
  reconnectTimer: number | null;
  lastEventId: string | null;
}

const channels = new Map<string, Channel>();
const INITIAL_RECONNECT_MS = 1_500;
const MAX_RECONNECT_MS = 30_000;

function open(url: string): void {
  const channel = channels.get(url);
  if (!channel || channel.controller) return;
  if (typeof fetch === "undefined" || typeof ReadableStream === "undefined") {
    dispatchTransportError(channel);
    scheduleReconnect(url);
    return;
  }

  const controller = new AbortController();
  channel.controller = controller;
  void runFetchStream(url, channel, controller);
}

async function runFetchStream(
  url: string,
  channel: Channel,
  controller: AbortController
): Promise<void> {
  try {
    const token = await resolveLocalApiToken();
    if (controller.signal.aborted || channel.controller !== controller) return;

    const response = await fetch(url, {
      headers: {
        accept: "text/event-stream",
        ...(token ? { [LOCAL_TOKEN_HEADER]: token } : {}),
        ...(channel.lastEventId ? { "Last-Event-ID": channel.lastEventId } : {})
      },
      signal: controller.signal
    });

    if (!response.ok || !response.body) {
      throw new Error(`SSE stream failed: ${response.status} ${response.statusText}`);
    }

    channel.reconnectMs = INITIAL_RECONNECT_MS;
    await readSseBody(response.body, channel);
    if (!controller.signal.aborted) dispatchTransportError(channel);
  } catch {
    if (!controller.signal.aborted) dispatchTransportError(channel);
  } finally {
    if (channel.controller === controller) {
      channel.controller = null;
    }
    if (!controller.signal.aborted && channel.listeners.size > 0) {
      scheduleReconnect(url);
    }
  }
}

async function readSseBody(body: ReadableStream<Uint8Array>, channel: Channel): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let frameEnd = buffer.indexOf("\n\n");
      while (frameEnd !== -1) {
        const frame = buffer.slice(0, frameEnd);
        buffer = buffer.slice(frameEnd + 2);
        dispatchFrame(frame, channel);
        frameEnd = buffer.indexOf("\n\n");
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // The browser may already have released the reader when aborting.
    }
  }
}

function dispatchFrame(frame: string, channel: Channel): void {
  let eventName = "message";
  let nextId: string | null = null;
  const dataLines: string[] = [];

  for (const rawLine of frame.split("\n")) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") eventName = value;
    if (field === "data") dataLines.push(value);
    if (field === "id") nextId = value;
  }

  if (nextId !== null) channel.lastEventId = nextId;
  if (dataLines.length === 0) return;

  dispatchEvent(channel, eventName, dataLines.join("\n"));
}

function dispatchEvent(channel: Channel, eventName: string, data: string): void {
  const listeners = channel.listeners.get(eventName);
  if (!listeners || listeners.size === 0) return;
  const event = new MessageEvent(eventName, {
    data,
    lastEventId: channel.lastEventId ?? ""
  });
  for (const cb of Array.from(listeners)) cb(event);
}

function dispatchTransportError(channel: Channel): void {
  dispatchEvent(channel, "error", "");
}

function scheduleReconnect(url: string): void {
  const channel = channels.get(url);
  if (!channel) return;
  if (channel.reconnectTimer !== null) return;
  const delay = channel.reconnectMs;
  channel.reconnectMs = Math.min(channel.reconnectMs * 2, MAX_RECONNECT_MS);
  channel.reconnectTimer = window.setTimeout(() => {
    channel.reconnectTimer = null;
    open(url);
  }, delay);
}

/**
 * Listen to one event on the SSE stream at `url`. Returns an
 * unsubscribe function — call it on cleanup. Repeated subscribes to
 * the same url+event are deduped at the socket level: only one
 * fetch stream is opened per URL.
 */
export function subscribeSse(
  url: string,
  event: string,
  cb: (ev: MessageEvent) => void
): () => void {
  let channel = channels.get(url);
  if (!channel) {
    channel = {
      controller: null,
      listeners: new Map(),
      reconnectMs: INITIAL_RECONNECT_MS,
      reconnectTimer: null,
      lastEventId: null,
    };
    channels.set(url, channel);
  }
  let set = channel.listeners.get(event);
  if (!set) {
    set = new Set();
    channel.listeners.set(event, set);
  }
  set.add(cb);
  open(url);
  return () => {
    const ch = channels.get(url);
    if (!ch) return;
    const s = ch.listeners.get(event);
    if (s) {
      s.delete(cb);
      if (s.size === 0) ch.listeners.delete(event);
    }
    if (ch.listeners.size === 0) {
      ch.controller?.abort();
      ch.controller = null;
      if (ch.reconnectTimer !== null) {
        window.clearTimeout(ch.reconnectTimer);
        ch.reconnectTimer = null;
      }
      channels.delete(url);
    }
  };
}
