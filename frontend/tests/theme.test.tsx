import { readFileSync } from "node:fs";

import { render, screen } from "@testing-library/preact";
import { afterEach, expect, test } from "vitest";

import { App } from "../src/app/App";
import "../src/main.css";

/*
 * Theme token lint.
 *
 * Originally asserted literal hex values (`#f5f5f7`, `#1d1d1f`). After the
 * Einstein UI brief landed (docs/einstein-ui-prompt.md) we moved to OKLCH +
 * semantic names:
 *   --text-primary  (new, canonical)
 *   --color-text-primary  (legacy alias, points at --text-primary)
 *
 * These tests now verify the shape we promise to the rest of the design
 * system:
 *   1. Both themes define `--text-primary` as a concrete OKLCH value.
 *   2. Dark and light differ on the luminance axis in the expected direction
 *      (dark surface → light text, light surface → dark text).
 *   3. The legacy alias still resolves through to the new semantic token so
 *      existing components pick up the amber-accent palette for free.
 */

const themesCss = readFileSync(
  "./src/design-system/themes.css",
  "utf8"
);

function findThemeValue(selector: string, property: string): string {
  const selectorIndex = themesCss.indexOf(`${selector} {`);
  if (selectorIndex === -1) {
    return "";
  }

  const blockStart = themesCss.indexOf("{", selectorIndex);
  const blockEnd = themesCss.indexOf("}", blockStart);
  const block = themesCss.slice(blockStart + 1, blockEnd);
  const match = block.match(new RegExp(`${property}:\\s*([^;]+);`));
  return match ? match[1]!.trim() : "";
}

function parseOklchLightness(value: string): number | null {
  const match = value.match(/oklch\(\s*([0-9.]+)/);
  if (!match) return null;
  const lightness = Number.parseFloat(match[1]!);
  return Number.isFinite(lightness) ? lightness : null;
}

afterEach(() => {
  document.documentElement.className = "";
});

test("dark theme exposes a light text-primary token in OKLCH", async () => {
  document.documentElement.classList.add("theme-dark");
  // Navigate to /library before render so the "No sources yet" readiness
  // marker still fires; the default route is now the Dashboard, which
  // doesn't show that text.
  window.history.pushState({}, "", "/library");
  render(<App />);
  await screen.findByText(/No sources yet\./i);

  const value = findThemeValue("html.theme-dark", "--text-primary");
  const lightness = parseOklchLightness(value);

  expect(value).toMatch(/^oklch\(/);
  // On a dark surface, primary text lightness must be near-white (~0.9+).
  expect(lightness).not.toBeNull();
  expect(lightness!).toBeGreaterThan(0.9);

  // Legacy alias must route through to the new semantic token so any older
  // component still wired to --color-text-primary picks up amber-era changes.
  expect(findThemeValue("html.theme-dark", "--color-text-primary")).toBe(
    "var(--text-primary)"
  );
});

test("light theme exposes a dark text-primary token in OKLCH", async () => {
  document.documentElement.classList.add("theme-light");
  // Navigate to /library before render so the "No sources yet" readiness
  // marker still fires; the default route is now the Dashboard, which
  // doesn't show that text.
  window.history.pushState({}, "", "/library");
  render(<App />);
  await screen.findByText(/No sources yet\./i);

  const value = findThemeValue("html.theme-light", "--text-primary");
  const lightness = parseOklchLightness(value);

  expect(value).toMatch(/^oklch\(/);
  // On a light surface, primary text lightness must be near-black (<=0.35).
  expect(lightness).not.toBeNull();
  expect(lightness!).toBeLessThan(0.35);

  expect(findThemeValue("html.theme-light", "--color-text-primary")).toBe(
    "var(--text-primary)"
  );
});

test("both themes define a cool-teal accent token", () => {
  const dark = findThemeValue("html.theme-dark", "--accent");
  const light = findThemeValue("html.theme-light", "--accent");

  expect(dark).toMatch(/^oklch\(/);
  expect(light).toMatch(/^oklch\(/);

  // Cool hue: OKLCH hue for teal sits in the 180–220° range. Anything outside
  // is a regression toward blue-SaaS (>230) or warm-amber (<160).
  const darkHueMatch = dark.match(/oklch\([0-9.]+\s+[0-9.]+\s+([0-9.]+)/);
  const lightHueMatch = light.match(/oklch\([0-9.]+\s+[0-9.]+\s+([0-9.]+)/);
  expect(darkHueMatch).not.toBeNull();
  expect(lightHueMatch).not.toBeNull();

  const darkHue = Number.parseFloat(darkHueMatch![1]!);
  const lightHue = Number.parseFloat(lightHueMatch![1]!);
  expect(darkHue).toBeGreaterThanOrEqual(180);
  expect(darkHue).toBeLessThanOrEqual(220);
  expect(lightHue).toBeGreaterThanOrEqual(180);
  expect(lightHue).toBeLessThanOrEqual(220);
});

test("state-warn stays warm (amber) so alerts read distinct from the cool accent", () => {
  const warnDark = findThemeValue("html.theme-dark", "--state-warn");
  const warnLight = findThemeValue("html.theme-light", "--state-warn");

  const hueFor = (value: string) => {
    const match = value.match(/oklch\([0-9.]+\s+[0-9.]+\s+([0-9.]+)/);
    return match ? Number.parseFloat(match[1]!) : null;
  };

  expect(hueFor(warnDark)).toBeGreaterThanOrEqual(40);
  expect(hueFor(warnDark)).toBeLessThanOrEqual(90);
  expect(hueFor(warnLight)).toBeGreaterThanOrEqual(40);
  expect(hueFor(warnLight)).toBeLessThanOrEqual(90);
});
