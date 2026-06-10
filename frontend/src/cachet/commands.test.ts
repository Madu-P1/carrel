import { describe, expect, it } from "vitest";

import { buildCommands, filterCommands, type Command } from "./commands";

describe("buildCommands", () => {
  const close = () => {};

  it("offers the verify verbs on the lectern and the verify route", () => {
    for (const path of ["/", "/verify"]) {
      const ids = buildCommands(path, close).map((c) => c.id);
      expect(ids).toContain("verify-draft");
      expect(ids).toContain("seal");
      expect(ids).toContain("export");
    }
  });

  it("the seal verb advertises no shortcut it does not implement", () => {
    // The old hint claimed ⌘S; no handler anywhere binds it. A filing-grade
    // tool must not decorate a command with a shortcut that does nothing.
    const seal = buildCommands("/", close).find((c) => c.id === "seal");
    expect(seal?.hint).toBeUndefined();
  });

  it("the seal and export verbs say they open the certification (ellipsis convention)", () => {
    const byId = new Map(buildCommands("/", close).map((c) => [c.id, c]));
    expect(byId.get("seal")?.title).toBe("Seal and save…");
    expect(byId.get("export")?.title).toBe("Export certification…");
  });

  it("hides the verify verbs where they cannot act", () => {
    const ids = buildCommands("/shelf", close).map((c) => c.id);
    expect(ids).not.toContain("verify-draft");
    expect(ids).not.toContain("seal");
    // navigation verbs are always available
    expect(ids).toContain("go-settings");
    expect(ids).toContain("go-shelf");
  });
});

describe("filterCommands", () => {
  const cmds: Command[] = [
    { id: "a", title: "Verify the draft", keywords: "check run", run() {} },
    { id: "b", title: "Open the Shelf", keywords: "saved record", run() {} }
  ];

  it("returns everything on an empty query", () => {
    expect(filterCommands(cmds, "").length).toBe(2);
  });

  it("matches by title token, case-insensitive", () => {
    expect(filterCommands(cmds, "VERIFY").map((c) => c.id)).toEqual(["a"]);
  });

  it("matches by keyword", () => {
    expect(filterCommands(cmds, "record").map((c) => c.id)).toEqual(["b"]);
  });

  it("requires every token to match (AND, not OR)", () => {
    expect(filterCommands(cmds, "open shelf").map((c) => c.id)).toEqual(["b"]);
    expect(filterCommands(cmds, "open draft").length).toBe(0);
  });
});
