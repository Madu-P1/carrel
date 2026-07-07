import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

const root = resolve(__dirname, "..", "src");
const files = [
  "design-system/tokens.css",
  "design-system/animations.css",
  "design-system/primitives/Button/Button.module.css",
  "design-system/primitives/Input/Input.module.css",
  "design-system/primitives/Pane/Pane.module.css",
  "design-system/primitives/Dialog/Dialog.module.css",
  "design-system/primitives/Tooltip/Tooltip.module.css",
  "design-system/primitives/Badge/Badge.module.css",
  "design-system/primitives/ScrollArea/ScrollArea.module.css",
  "design-system/primitives/Card/Card.module.css",
  "design-system/primitives/Text/Text.module.css",
  "app/shell/AppShell.module.css"
].map((file) => resolve(root, file));

function read(path: string): string {
  return readFileSync(path, "utf8");
}

describe("motion CSS guardrails", () => {
  test("migrated files do not use legacy motion tokens", () => {
    const offenders = files
      .map((file) => ({ file, source: read(file) }))
      .filter(({ source, file }) => {
        if (file.endsWith("tokens.css")) {
          return false;
        }
        return /--motion-(fast|base|slow)|--ease-in-out/.test(source);
      });

    expect(offenders).toEqual([]);
  });

  test("transition shorthands do not animate layout-triggering properties", () => {
    const offenders = files
      .map((file) => ({ file, source: read(file) }))
      .flatMap(({ file, source }) => {
        const matches = [...source.matchAll(/transition\s*:\s*([\s\S]*?);/g)];
        return matches
          .filter((match) => /\b(width|height|top|left|margin|padding)\b/.test(match[1]))
          .map((match) => ({ file, transition: match[1].trim() }));
      });

    expect(offenders).toEqual([]);
  });

  test("display variants are the only ones wired to the serif font", () => {
    const textCss = read(resolve(root, "design-system/primitives/Text/Text.module.css"));
    expect(textCss).toContain(".variant-h1");
    expect(textCss).toContain(".variant-display");
    expect(textCss).toContain("font-family: var(--font-serif-display);");
  });

  test("tokens and keyframes include reduced-motion fallbacks", () => {
    const tokens = read(resolve(root, "design-system/tokens.css"));
    const animations = read(resolve(root, "design-system/animations.css"));

    expect(tokens).toContain("@media (prefers-reduced-motion: reduce)");
    expect(tokens).toContain("--dur-base: 60ms;");
    expect(animations).toContain(".anim-fadeUp");
    expect(animations).toContain(".anim-slideInRight");
    expect(animations).toContain(".anim-slideInLeft");
    expect(animations).toContain(".anim-scalePress");
    expect(animations).toContain(".anim-pulseOnce");
    expect(animations).toContain(".anim-shimmer");
    expect(animations).toContain(".anim-focusRing");
    expect(animations).toContain(".anim-caretBlink");
  });

  test("route transition wrapper preserves full-height reader layouts", () => {
    const shell = read(resolve(root, "app/shell/AppShell.module.css"));
    const match = shell.match(/\.pageTransition\s*\{([\s\S]*?)\}/);

    expect(match?.[1]).toContain("height: 100%;");
    expect(match?.[1]).toContain("min-height: 0;");
  });
});
