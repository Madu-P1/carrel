import { describe, expect, it } from "vitest";

import { buildCommands, filterCommands, type Command } from "./commands";

describe("buildCommands", () => {
  const close = () => {};

  it("never offers a verb with no listener (the dead verify verbs stay out)", () => {
    // verify-draft/seal/export dispatched a CustomEvent nothing handled, so the
    // palette offered actions that silently did nothing. They stay out until a
    // listener exists on the verify surface.
    for (const path of ["/", "/verify", "/shelf"]) {
      const ids = buildCommands(path, close).map((c) => c.id);
      expect(ids).not.toContain("verify-draft");
      expect(ids).not.toContain("seal");
      expect(ids).not.toContain("export");
    }
  });

  it("always offers the navigation verbs", () => {
    const ids = buildCommands("/shelf", close).map((c) => c.id);
    expect(ids).toContain("go-settings");
    expect(ids).toContain("go-shelf");
    expect(ids).toContain("go-vault");
    expect(ids).toContain("new");
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
