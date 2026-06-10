import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test } from "vitest";

// The cold-register display face. The 2026-06-02 brand decision moved Cachet's
// display serif from Instrument Serif to Libre Caslon Display; the rebind lives
// in cachet.module.css (--font-serif on the shell root). A rebind without a
// matching @font-face silently falls back to Charter/Georgia — the chosen face
// never renders and Vite never bundles the woff2 files. These tests tie the
// three pieces (rebind, declaration, files on disk) together so they cannot
// drift apart again.

const cachetCss = readFileSync(resolve(__dirname, "cachet.module.css"), "utf8");
const tokensCss = readFileSync(
  resolve(__dirname, "..", "design-system", "tokens.css"),
  "utf8"
);

describe("the Cachet display face is actually wired", () => {
  test("cachet.module.css rebinds --font-serif to Libre Caslon Display first", () => {
    const rebind = cachetCss.match(/--font-serif:\s*([^;]+);/)?.[1] ?? "";
    expect(rebind).toContain('"Libre Caslon Display"');
  });

  test("tokens.css declares @font-face for every family the shell rebinds to", () => {
    // Without this declaration the browser cannot resolve the family name and
    // the cold register silently renders in the fallback serif.
    expect(tokensCss).toMatch(/@font-face\s*\{[^}]*"Libre Caslon Display"/);
  });

  test("the declared woff2 files exist on disk (latin + latin-ext)", () => {
    const fontsDir = resolve(__dirname, "..", "assets", "fonts");
    expect(existsSync(resolve(fontsDir, "libre-caslon-display-latin-400.woff2"))).toBe(true);
    expect(
      existsSync(resolve(fontsDir, "libre-caslon-display-latin-ext-400.woff2"))
    ).toBe(true);
    // And tokens.css actually references them (a declaration pointing at a
    // missing file fails silently at runtime too).
    expect(tokensCss).toContain("libre-caslon-display-latin-400.woff2");
    expect(tokensCss).toContain("libre-caslon-display-latin-ext-400.woff2");
  });
});
