import { afterEach, describe, expect, it, vi } from "vitest";

import { documents as documentsApi } from "@/services/api/endpoints";

import {
  clearPersistedActiveRecord,
  loadedSource,
  refreshSources,
  sourceDocs,
  sourcesFixtureRequested
} from "./source";

vi.mock("@/services/api/endpoints", () => ({
  documents: { list: vi.fn() },
  vaults: { list: vi.fn(), create: vi.fn(), remove: vi.fn() }
}));
const mockList = vi.mocked(documentsApi.list);

// source.ts holds the module-global signals the whole shell trusts: which
// record the next verify is checked against, persisted across app launches.
// These tests lock the fixture gate and the persistence seam around it.

afterEach(() => {
  loadedSource.value = null;
  sourceDocs.value = null;
  globalThis.localStorage?.clear();
  vi.clearAllMocks();
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


describe("stale active-record validation", () => {
  it("drops a persisted record that no longer exists in the library", async () => {
    // The live failure this pins (2026-06-10): the localStorage pointer
    // outlived its database. The lectern chip asserted 'LOADED AS THE RECORD'
    // for a docId the engine could not resolve, so every check came back
    // could-not-check while the drawer said no source was loaded — the screen
    // contradicted itself about session state.
    loadedSource.value = { docId: "ghost-doc", filename: "Broadfield.pdf" };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockList.mockResolvedValue([
      { id: "real-1", filename: "MSA.pdf", subject_name: "General", page_count: 3, file_type: "pdf" }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any);
    await refreshSources();
    expect(loadedSource.value).toBeNull();
    expect(globalThis.localStorage?.getItem("cachet.activeRecord")).toBeNull();
  });

  it("keeps a persisted record that the library still contains", async () => {
    loadedSource.value = { docId: "real-1", filename: "MSA.pdf" };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockList.mockResolvedValue([
      { id: "real-1", filename: "MSA.pdf", subject_name: "General", page_count: 3, file_type: "pdf" }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any);
    await refreshSources();
    expect(loadedSource.value).toEqual({ docId: "real-1", filename: "MSA.pdf" });
  });

  it("keeps the record when the library fetch fails (no clearing on uncertainty)", async () => {
    loadedSource.value = { docId: "real-1", filename: "MSA.pdf" };
    mockList.mockRejectedValue(new Error("backend offline"));
    await refreshSources();
    expect(loadedSource.value).toEqual({ docId: "real-1", filename: "MSA.pdf" });
  });
});
