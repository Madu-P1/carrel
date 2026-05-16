import { vi } from "vitest";

/**
 * `mockFetch` intercepts `fetch` only. The upload-with-progress path
 * uses `XMLHttpRequest` because `fetch` cannot report upload progress.
 * This stub proxies XHR requests through the global `fetch` mock so the
 * same handler registry covers both transports. Production code keeps
 * using the real XHR.
 *
 * Behaviour:
 *   - `setRequestHeader` is recorded and forwarded to `fetch`.
 *   - `send(body)` calls `fetch(url, { method, headers, body })`; the
 *     response status/text is then exposed via `status`, `statusText`,
 *     `responseText`, and `response`.
 *   - A single upload `progress` event (100%) fires before `load` so any
 *     UI that listens for progress sees at least one tick. Real per-byte
 *     progress is not simulated; tests asserting bytes-mid-stream are
 *     out of scope for this stub.
 *   - `abort()` triggers the `abort` listener and skips `load`.
 *
 * Implements only the surface uploadWithProgress uses. Add more as
 * other XHR callers appear.
 */

type Listener = (event: Event) => void;

interface UploadTarget {
  addEventListener: (event: string, fn: Listener) => void;
  removeEventListener: (event: string, fn: Listener) => void;
}

class FakeXhr {
  readyState = 0;
  status = 0;
  statusText = "";
  responseText = "";
  response: unknown = null;
  withCredentials = false;

  private _method = "GET";
  private _url = "";
  private _headers: Record<string, string> = {};
  private _aborted = false;
  private _listeners: Record<string, Listener[]> = {};
  private _uploadListeners: Record<string, Listener[]> = {};

  upload: UploadTarget = {
    addEventListener: (event, fn) => {
      this._uploadListeners[event] = [...(this._uploadListeners[event] ?? []), fn];
    },
    removeEventListener: (event, fn) => {
      this._uploadListeners[event] = (this._uploadListeners[event] ?? []).filter((other) => other !== fn);
    }
  };

  open(method: string, url: string): void {
    this._method = method;
    this._url = url;
  }

  setRequestHeader(name: string, value: string): void {
    this._headers[name] = value;
  }

  addEventListener(event: string, fn: Listener): void {
    this._listeners[event] = [...(this._listeners[event] ?? []), fn];
  }

  removeEventListener(event: string, fn: Listener): void {
    this._listeners[event] = (this._listeners[event] ?? []).filter((other) => other !== fn);
  }

  abort(): void {
    this._aborted = true;
    this._dispatch("abort");
  }

  send(body?: Document | XMLHttpRequestBodyInit | null): void {
    void this._send(body ?? null);
  }

  private async _send(body: Document | XMLHttpRequestBodyInit | null): Promise<void> {
    try {
      const bodySize = this._approxBodySize(body);
      // Synthesize a single 100% upload progress event so any listener
      // can fire at least once. Real per-byte streaming is not
      // simulated; that would need a different test harness.
      this._dispatchUpload("progress", {
        lengthComputable: bodySize > 0,
        loaded: bodySize,
        total: bodySize
      });

      const init: RequestInit = {
        method: this._method,
        headers: this._headers,
        body: body as BodyInit | null
      };
      const response = await fetch(this._url, init);
      if (this._aborted) return;

      this.status = response.status;
      this.statusText = response.statusText;
      this.responseText = await response.text();
      this.response = this.responseText;
      this.readyState = 4;
      this._dispatch("load");
    } catch (cause) {
      if (this._aborted) return;
      this._dispatch("error");
      // Swallow: error listeners are how the caller learns about this.
      void cause;
    }
  }

  private _approxBodySize(body: Document | XMLHttpRequestBodyInit | null): number {
    if (body === null) return 0;
    if (typeof body === "string") return body.length;
    if (body instanceof Blob) return body.size;
    if (body instanceof ArrayBuffer) return body.byteLength;
    // FormData and other shapes: no cheap size; report 0 and let
    // `lengthComputable: false` carry the truth.
    return 0;
  }

  private _dispatch(event: string): void {
    const ev = new Event(event);
    for (const fn of this._listeners[event] ?? []) {
      fn(ev);
    }
  }

  private _dispatchUpload(event: string, init: { lengthComputable: boolean; loaded: number; total: number }): void {
    const ev = Object.assign(new Event(event), init) as unknown as Event;
    for (const fn of this._uploadListeners[event] ?? []) {
      fn(ev);
    }
  }
}

export function installXhrMock(): void {
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
}
