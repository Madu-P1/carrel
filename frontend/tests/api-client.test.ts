import { afterEach, expect, test, vi } from "vitest";

import { ApiTimeoutError, BackendOfflineError, api } from "../src/services/api/client";

afterEach(() => {
  vi.useRealTimers();
  delete (window as Window & { __CARREL_LOCAL_API_TOKEN?: string }).__CARREL_LOCAL_API_TOKEN;
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

test("api attaches local token header to mutating requests", async () => {
  const fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(json({ ok: true }))
  );
  vi.stubGlobal("fetch", fetch);

  await api("/json", { method: "POST", body: { title: "Bonds" } });

  const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(init?.headers).toMatchObject({
    "X-Carrel-Local-Token": "test-local-token"
  });
});

test("api does not attach local token header to safe requests", async () => {
  const fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(json({ ok: true }))
  );
  vi.stubGlobal("fetch", fetch);

  await api("/json");

  const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(init?.headers).not.toMatchObject({
    "X-Carrel-Local-Token": expect.any(String)
  });
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

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" }
  });
}
