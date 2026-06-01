import { describe, expect, it } from "vitest";

import { createQuery } from "./query";

// A promise the test resolves or rejects on demand, so we can hold a fetch
// "in flight" and control the order two overlapping fetches settle in.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// A fetcher that hands out a different (controllable) promise per call, and
// records how many times it was actually invoked.
function sequence<T>(...gates: Array<{ promise: Promise<T> }>) {
  let calls = 0;
  const fetcher = () => {
    const gate = gates[Math.min(calls, gates.length - 1)];
    calls += 1;
    return gate.promise;
  };
  return { fetcher, calls: () => calls };
}

describe("createQuery", () => {
  it("starts idle: no data, not loading, no error", () => {
    const query = createQuery(async () => 1);
    expect(query.data.value).toBeUndefined();
    expect(query.loading.value).toBe(false);
    expect(query.error.value).toBeNull();
  });

  it("a subscribed refetch is loading in flight, then holds the result", async () => {
    const gate = deferred<number>();
    const query = createQuery(() => gate.promise);
    query.subscribe();

    const settled = query.refetch();
    expect(query.loading.value).toBe(true); // set synchronously before the await

    gate.resolve(42);
    await settled;

    expect(query.data.value).toBe(42);
    expect(query.loading.value).toBe(false);
    expect(query.error.value).toBeNull();
  });

  it("a rejection records the error and stops loading without wiping already-loaded data", async () => {
    const ok = deferred<number>();
    const bad = deferred<number>();
    const { fetcher } = sequence(ok, bad);
    const query = createQuery(fetcher);
    query.subscribe();

    // Seed a committed success first, so the error assertions are not vacuous.
    const first = query.refetch();
    ok.resolve(7);
    await first;
    expect(query.data.value).toBe(7);

    const second = query.refetch();
    const failure = new Error("fetch failed");
    bad.reject(failure);
    await second;

    expect(query.error.value).toBe(failure);
    expect(query.loading.value).toBe(false);
    expect(query.data.value).toBe(7); // prior data is preserved, not cleared, on error
  });

  it("a refetch clears a previously recorded error, synchronously and on success", async () => {
    const bad = deferred<number>();
    const ok = deferred<number>();
    const { fetcher } = sequence(bad, ok);
    const query = createQuery(fetcher);
    query.subscribe();

    // Seed a committed error first, so "error cleared" is a real transition.
    const first = query.refetch();
    bad.reject(new Error("first failed"));
    await first;
    expect(query.error.value).toBeInstanceOf(Error);

    const second = query.refetch();
    expect(query.error.value).toBeNull(); // cleared synchronously at refetch start
    expect(query.loading.value).toBe(true);

    ok.resolve(9);
    await second;
    expect(query.error.value).toBeNull();
    expect(query.data.value).toBe(9);
  });

  it("keeps previously loaded data visible while the next refetch is in flight", async () => {
    const ok = deferred<number>();
    const pending = deferred<number>();
    const { fetcher } = sequence(ok, pending);
    const query = createQuery(fetcher);
    query.subscribe();

    const first = query.refetch();
    ok.resolve(1);
    await first;
    expect(query.data.value).toBe(1);

    query.refetch(); // in flight, never resolved here
    expect(query.loading.value).toBe(true);
    expect(query.data.value).toBe(1); // stale data stays visible during reload
  });

  it("drops a stale response even when the stale fetch completes before the newer one", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const { fetcher } = sequence(first, second);
    const query = createQuery(fetcher);
    query.subscribe();

    const settledA = query.refetch(); // generation -> 1
    const settledB = query.refetch(); // generation -> 2

    first.resolve("old"); // stale resolves FIRST, while the newer fetch is still pending
    await settledA;
    expect(query.data.value).toBeUndefined(); // dropped: requestGeneration 1 !== generation 2

    second.resolve("new");
    await settledB;
    expect(query.data.value).toBe("new");
  });

  it("drops a stale rejection from a superseded fetch", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const { fetcher } = sequence(first, second);
    const query = createQuery(fetcher);
    query.subscribe();

    const settledA = query.refetch(); // generation -> 1
    const settledB = query.refetch(); // generation -> 2

    first.reject(new Error("stale failure"));
    await settledA;
    expect(query.error.value).toBeNull(); // superseded rejection must not surface

    second.resolve("new");
    await settledB;
    expect(query.data.value).toBe("new");
    expect(query.error.value).toBeNull();
  });

  it("reset clears committed data, loading, and error synchronously", async () => {
    const ok = deferred<number>();
    const query = createQuery(() => ok.promise);
    query.subscribe();

    const settled = query.refetch();
    ok.resolve(5);
    await settled;
    expect(query.data.value).toBe(5);

    query.reset();
    expect(query.data.value).toBeUndefined();
    expect(query.loading.value).toBe(false);
    expect(query.error.value).toBeNull();
  });

  it("reset cancels an in-flight refetch", async () => {
    const gate = deferred<string>();
    const query = createQuery(() => gate.promise);
    query.subscribe();

    const settled = query.refetch();
    query.reset();
    expect(query.loading.value).toBe(false); // loading cleared the instant reset runs

    gate.resolve("arrived after reset");
    await settled;
    expect(query.data.value).toBeUndefined(); // the post-reset result is dropped
  });

  it("drops the result once the last subscriber unsubscribes mid-flight", async () => {
    const gate = deferred<number>();
    const seq = sequence(gate);
    const query = createQuery(seq.fetcher);

    const unsubscribe = query.subscribe();
    const settled = query.refetch();
    unsubscribe(); // active subscribers -> 0, which bumps generation

    gate.resolve(5);
    await settled;

    expect(seq.calls()).toBe(1); // the fetcher really ran
    expect(query.data.value).toBeUndefined(); // but the result is discarded
  });

  it("keeps delivering while at least one subscriber remains", async () => {
    const gate = deferred<number>();
    const query = createQuery(() => gate.promise);

    const unsubscribeA = query.subscribe();
    query.subscribe();
    const settled = query.refetch();
    unsubscribeA(); // one subscriber remains, so generation is NOT bumped

    gate.resolve(9);
    await settled;
    expect(query.data.value).toBe(9);
  });

  it("runs the fetcher but discards the result when there are no subscribers", async () => {
    const gate = deferred<number>();
    const seq = sequence(gate);
    const query = createQuery(seq.fetcher);
    // intentionally never subscribe()

    const settled = query.refetch();
    gate.resolve(7);
    await settled;

    expect(seq.calls()).toBe(1); // fetcher invoked
    expect(query.data.value).toBeUndefined(); // result dropped (activeSubscribers === 0)
  });
});
