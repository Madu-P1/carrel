import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test } from "vitest";

// The Cachet handoff type trio (2026-07-02, ~/Downloads/design_handoff_cachet):
// Newsreader on reading surfaces, Hanken Grotesk in the chrome, JetBrains Mono
// for hashes/counts/tiers. The roles are rebound in cachet.module.css; the
// @font-face declarations live in tokens.css; the woff2 are self-hosted for
// offline. A rebind without a matching @font-face silently falls back and the
// chosen face never renders, so these tests tie rebind + declaration + files on
// disk together so they cannot drift apart.

const cachetCss = readFileSync(resolve(__dirname, "cachet.module.css"), "utf8");
const tokensCss = readFileSync(
  resolve(__dirname, "..", "design-system", "tokens.css"),
  "utf8"
);
const fontsDir = resolve(__dirname, "..", "assets", "fonts");

describe("the Cachet handoff fonts are actually wired", () => {
  test("cachet.module.css rebinds the three roles to the handoff faces", () => {
    const serif = cachetCss.match(/--font-serif:\s*([^;]+);/)?.[1] ?? "";
    const serifBody = cachetCss.match(/--font-serif-body:\s*([^;]+);/)?.[1] ?? "";
    const sans = cachetCss.match(/--font-sans:\s*([^;]+);/)?.[1] ?? "";
    const mono = cachetCss.match(/--font-mono:\s*([^;]+);/)?.[1] ?? "";
    expect(serif).toContain("Newsreader");
    expect(serifBody).toContain("Newsreader");
    expect(sans).toContain('"Hanken Grotesk"');
    expect(mono).toContain('"JetBrains Mono"');
  });

  test("tokens.css declares @font-face for every family the shell rebinds to", () => {
    // Without these the browser cannot resolve the family names and the chrome
    // silently renders in the system fallback.
    expect(tokensCss).toMatch(/@font-face\s*\{[^}]*"Newsreader"/);
    expect(tokensCss).toMatch(/@font-face\s*\{[^}]*"Hanken Grotesk"/);
    expect(tokensCss).toMatch(/@font-face\s*\{[^}]*"JetBrains Mono"/);
  });

  test("the declared woff2 files exist on disk and are referenced", () => {
    const files = [
      "newsreader-latin-400.woff2",
      "newsreader-latin-500.woff2",
      "newsreader-latin-600.woff2",
      "newsreader-latin-italic-400.woff2",
      "hanken-grotesk-latin-400.woff2",
      "hanken-grotesk-latin-500.woff2",
      "hanken-grotesk-latin-600.woff2",
      "hanken-grotesk-latin-700.woff2",
      "jetbrains-mono-latin-400.woff2",
      "jetbrains-mono-latin-500.woff2"
    ];
    for (const f of files) {
      expect(existsSync(resolve(fontsDir, f)), `${f} on disk`).toBe(true);
      // A declaration pointing at a missing file fails silently at runtime too.
      expect(tokensCss, `${f} referenced`).toContain(f);
    }
  });
});
