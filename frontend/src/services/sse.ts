/**
 * Shared SSE multiplexer.
 *
 * Before this module, four separate features (jobs feed, plan view,
 * dashboard insertions, companion alarm) each built their own
 * EventSource + reconnect + handler tree against the same backend
 * stream. That meant up to 4 simultaneous connections to one URL,
 * 4 reconnect loops, 4 separate sets of bugs to keep in sync.
 *
 * Now everything that wants to listen calls `subscribeSse(url, event,
 * cb)` and gets an unsubscribe function back. The multiplexer keeps a
 * single EventSource per URL, fans events out, and auto-reconnects
 * with exponential backoff when the underlying socket dies. When the
 * last subscriber for a URL leaves, the connection is closed and the
 * URL slot is freed.
 *
 * No queueing: SSE is fire-and-forget by design and EventSource
 * reconnect already includes the `Last-Event-ID` header. Listeners
 * that need durability can fall back to polling — every existing
 * caller already does this naturally via window-focus refetches.
 */

interface Channel {
  source: EventSource | null;
  /** Map of event-name → set of callbacks. Outer map is keyed by
   *  event name so EventSource.addEventListener fires each cb directly
   *  and we don't have to filter inside the handler. */
  listeners: Map<string, Set<(ev: MessageEvent) => void>>;
  /** Backoff schedule for the next reconnect attempt. Resets on a
   *  successful open. */
  reconnectMs: number;
  reconnectTimer: number | null;
}

const channels = new Map<string, Channel>();
const INITIAL_RECONNECT_MS = 1_500;
const MAX_RECONNECT_MS = 30_000;

function open(url: string): void {
  const channel = channels.get(url);
  if (!channel || channel.source) return;
  if (typeof EventSource === "undefined") return;
  let source: EventSource;
  try {
    source = new EventSource(url);
  } catch {
    scheduleReconnect(url);
    return;
  }
  channel.source = source;
  // Re-attach all known listeners to the new socket.
  for (const [event, set] of channel.listeners) {
    for (const cb of set) source.addEventListener(event, cb as EventListener);
  }
  source.onopen = () => {
    channel.reconnectMs = INITIAL_RECONNECT_MS;
  };
  source.onerror = () => {
    source.close();
    channel.source = null;
    if (channel.listeners.size === 0) return;
    scheduleReconnect(url);
  };
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
 * EventSource is opened per URL.
 */
export function subscribeSse(
  url: string,
  event: string,
  cb: (ev: MessageEvent) => void
): () => void {
  let channel = channels.get(url);
  if (!channel) {
    channel = {
      source: null,
      listeners: new Map(),
      reconnectMs: INITIAL_RECONNECT_MS,
      reconnectTimer: null,
    };
    channels.set(url, channel);
  }
  let set = channel.listeners.get(event);
  if (!set) {
    set = new Set();
    channel.listeners.set(event, set);
  }
  set.add(cb);
  if (channel.source) {
    channel.source.addEventListener(event, cb as EventListener);
  } else {
    open(url);
  }
  return () => {
    const ch = channels.get(url);
    if (!ch) return;
    ch.source?.removeEventListener(event, cb as EventListener);
    const s = ch.listeners.get(event);
    if (s) {
      s.delete(cb);
      if (s.size === 0) ch.listeners.delete(event);
    }
    if (ch.listeners.size === 0) {
      ch.source?.close();
      ch.source = null;
      if (ch.reconnectTimer !== null) {
        window.clearTimeout(ch.reconnectTimer);
        ch.reconnectTimer = null;
      }
      channels.delete(url);
    }
  };
}
