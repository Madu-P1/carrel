import { afterEach, describe, expect, it } from "vitest";

import {
  clearPersistedActiveRecord,
  loadedSource,
  sourcesFixtureRequested
} from "./source";

// source.ts holds the module-global signals the whole shell trusts: which
// record the next verify is checked against, persisted across app launches.
// These tests lock the fixture gate and the persistence seam around it.

afterEach(() => {
  loadedSource.value = null;
  globalThis.localStorage?.clear();
});

describe("sourcesFixtureRequested", () => {
  it("matches only the exact fixture=sources query", () => {
    expect(sourcesFixtureRequested("?fixture=sources")).toBe(true);
    expect(sourcesFixtureRequested("?fixture=sources&x=1")).toBe(true);
    expect(sourcesFixtureRequested("?fixture=other")).toBe(false);
    expect(sourcesFixtureRequested("?demo=verdicts")).toBe(false);
    expect(sourcesFixtureRequested("")).toBe(false);
  });
});

describe("active-record persistence", () => {
  it("setting loadedSource persists it for the next launch", () => {
    loadedSource.value = { docId: "d1", filename: "Executed MSA.pdf" };
    const raw = globalThis.localStorage?.getItem("cachet.activeRecord") ?? "";
    expect(JSON.parse(raw)).toEqual({ docId: "d1", filename: "Executed MSA.pdf" });
  });

  it("clearPersistedActiveRecord drops the stored record but keeps the session value", () => {
    // The dev fixture's contract: a fake record may live for the fixture page,
    // but must never survive into a later real session via localStorage.
    loadedSource.value = { docId: "d-fake", filename: "Fixture.pdf" };
    clearPersistedActiveRecord();
    expect(globalThis.localStorage?.getItem("cachet.activeRecord")).toBeNull();
    expect(loadedSource.value).toEqual({ docId: "d-fake", filename: "Fixture.pdf" });
  });

  it("clearing the source removes the persisted record too", () => {
    loadedSource.value = { docId: "d1", filename: "Executed MSA.pdf" };
    loadedSource.value = null;
    expect(globalThis.localStorage?.getItem("cachet.activeRecord")).toBeNull();
  });
});
