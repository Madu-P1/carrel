import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  ApiTimeoutError,
  BackendOfflineError,
  api,
  readWindowApiBase
} from "../src/services/api/client";

const LOCAL_TOKEN_HEADER = "X-Carrel-Local-Token";
const TEST_TOKEN = "test-local-token";

beforeEach(() => {
  // setup.ts seeds window.__CARREL_LOCAL_API_TOKEN in beforeEach, but the
  // client caches the token in module scope after the first resolve. Reset
  // the global and re-seed so each test sees a clean cache state. We can't
  // easily clear the cache from outside the module; relying on the fact
  // that the cache is set in beforeEach in setup.ts is enough for now.
  (window as Window & { __CARREL_LOCAL_API_TOKEN?: string }).__CARREL_LOCAL_API_TOKEN = TEST_TOKEN;
});

afterEach(() => {
  vi.useRealTimers();
});

test("readWindowApiBase reads the injected same-origin base, else null", () => {
  const w = window as Window & { __CARREL_API_BASE?: unknown };
  delete w.__CARREL_API_BASE;
  expect(readWindowApiBase()).toBeNull();
  // The Cachet web-serving backend injects "" so calls go same-origin.
  w.__CARREL_API_BASE = "";
  expect(readWindowApiBase()).toBe("");
  w.__CARREL_API_BASE = "http://127.0.0.1:9000";
  expect(readWindowApiBase()).toBe("http://127.0.0.1:9000");
  delete w.__CARREL_API_BASE;
});

test("api serializes JSON request bodies", async () => {
  const fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(json({ ok: true }))
  );
  vi.stubGlobal("fetch", fetch);

  await expect(api("/json", { method: "POST", body: { title: "Bonds" } })).resolves.toEqual({ ok: true });

  const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(init).toBeDefined();
  expect(init?.headers).toMatchObject({ "content-type": "application/json" });
  expect(init?.body).toBe(JSON.stringify({ title: "Bonds" }));
});

test("api leaves FormData bodies untouched", async () => {
  const fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(json({ ok: true }))
  );
  vi.stubGlobal("fetch", fetch);
  const body = new FormData();
  body.append("file", new Blob(["hello"]), "notes.txt");

  await api("/upload", { method: "POST", body });

  const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(init).toBeDefined();
  expect(init?.headers).not.toMatchObject({ "content-type": expect.any(String) });
  expect(init?.body).toBe(body);
});

test("api returns undefined for 204 responses", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))));

  await expect(api("/empty")).resolves.toBeUndefined();
});

test("api handles non-json error payloads", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(new Response("not-json", { status: 500, statusText: "Server Error" }))
    )
  );

  await expect(api("/broken")).rejects.toMatchObject({
    name: "ApiError",
    status: 500,
    body: undefined
  });
});

test("api distinguishes timeout from backend offline", async () => {
  vi.useFakeTimers();
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      })
    )
  );

  const request = api("/slow", { timeoutMs: 5 });
  const expectation = expect(request).rejects.toBeInstanceOf(ApiTimeoutError);
  await vi.advanceTimersByTimeAsync(10);

  await expectation;
});

test("api maps network failure to BackendOfflineError", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("connection refused"))));

  await expect(api("/offline")).rejects.toBeInstanceOf(BackendOfflineError);
});

test("api sends the local-API token on GET requests", async () => {
  // PR-S1: the token used to be optional on safe methods, leaving GETs
  // unauthenticated. The backend now gates all /api/* paths except
  // /api/health, so the client must send the token on every call.
  const fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(json({ ok: true }))
  );
  vi.stubGlobal("fetch", fetch);

  await api("/api/documents");

  const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(init?.headers).toMatchObject({ [LOCAL_TOKEN_HEADER]: TEST_TOKEN });
});

test("api sends the local-API token on POST requests", async () => {
  const fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(json({ ok: true }))
  );
  vi.stubGlobal("fetch", fetch);

  await api("/api/documents", { method: "POST", body: { title: "Notes" } });

  const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(init?.headers).toMatchObject({ [LOCAL_TOKEN_HEADER]: TEST_TOKEN });
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" }
  });
}
