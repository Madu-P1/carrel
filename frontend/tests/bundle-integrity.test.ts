import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

// This suite guards against the class of build bug where inlined JS contains
// a literal </script substring, causing WKWebView's HTML parser to close the
// <script> tag early and render the rest of the bundle as body text.
//
// Concrete incident: PR-E5-lite era. `app.new.html` contained `src="./assets/index.js"></script>`
// inside an inline module script, which closed the tag at byte 7643 and rendered
// ~1.5 MB of minified JS as plain text in the app window.
//
// Verified by: re-running `pnpm build:macos` and asserting the built artifact
// passes per-block integrity before landing anywhere near WKWebView.

const bundlePath = resolve(__dirname, "..", "..", "macos-app", "Resources", "app.new.html");

describe("bundled app.new.html integrity", () => {
  test("built bundle exists and is non-trivial", () => {
    expect(existsSync(bundlePath)).toBe(true);
    const stat = statSync(bundlePath);
    // Sanity: should be well over 100 KB (includes inlined JS + CSS + pdf worker base64).
    expect(stat.size).toBeGreaterThan(100_000);
  });

  test("every <script> body is free of </script substrings", () => {
    const html = readFileSync(bundlePath, "utf8");
    const blocks = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi)];
    const offenders = blocks
      .map((match, index) => ({ index, inner: match[1] }))
      .filter((block) => /<\/script/i.test(block.inner));

    if (offenders.length > 0) {
      const reports = offenders
        .map((o) => {
          const at = o.inner.search(/<\/script/i);
          const preview = o.inner.slice(Math.max(0, at - 60), Math.min(o.inner.length, at + 60));
          return `  block #${o.index} at offset ${at}: ...${preview}...`;
        })
        .join("\n");
      throw new Error(
        `Bundled HTML has script block(s) containing </script:\n${reports}\n\n` +
        "The HTML parser will close the <script> tag early and render the rest as body text. " +
        "Escape inlined JS via safeInline() in frontend/scripts/build-macos.mjs."
      );
    }
    expect(offenders.length).toBe(0);
  });

  test("<script> open and </script> close counts match", () => {
    const html = readFileSync(bundlePath, "utf8");
    const opens = (html.match(/<script\b/gi) ?? []).length;
    const closes = (html.match(/<\/script>/gi) ?? []).length;
    expect(opens).toBe(closes);
  });

  test("no stale ./assets/index.js reference", () => {
    const html = readFileSync(bundlePath, "utf8");
    // The Vite output directory is dist/assets/. We copy to macos-app/Resources/assets.new/.
    // Any reference to ./assets/index.js in the bundled HTML would 404 under file://.
    expect(html.includes('src="./assets/index.js"')).toBe(false);
  });

  test("every <script src=...> points at ./assets.new/", () => {
    const html = readFileSync(bundlePath, "utf8");
    const srcs = [...html.matchAll(/<script\b[^>]*\bsrc="([^"]+)"/gi)].map((m) => m[1]);
    const bad = srcs.filter((src) => !src.startsWith("./assets.new/"));
    if (bad.length > 0) {
      throw new Error(`Unresolvable external script src(s) under file://: ${bad.join(", ")}`);
    }
    expect(bad.length).toBe(0);
  });

  test("exactly one <!doctype html> marker", () => {
    const html = readFileSync(bundlePath, "utf8");
    const hits = (html.match(/<!doctype html>/gi) ?? []).length;
    expect(hits).toBe(1);
  });

  test("root mount div is present in body", () => {
    const html = readFileSync(bundlePath, "utf8");
    expect(html).toMatch(/<div\s+id="root"\s*><\/div>/);
  });

  test("no references to third-party CDN hosts (local-first guard)", () => {
    // Bunny Fonts, Google Fonts, jsdelivr, unpkg, etc. all break the offline
    // promise and pay DNS+TLS on every cold launch. Fonts and scripts must
    // be self-hosted under src/assets/ and bundled into assets.new/.
    const html = readFileSync(bundlePath, "utf8");
    const externalRefs = [...html.matchAll(/(href|src)="(https?:\/\/(?!127\.0\.0\.1|localhost)[^"]+)"/gi)].map(
      (m) => m[2],
    );
    if (externalRefs.length > 0) {
      throw new Error(
        `Bundle references third-party hosts (breaks local-first): ${externalRefs.join(", ")}\n` +
        "Self-host the asset under frontend/src/assets/ and import it from the relevant stylesheet.",
      );
    }
    expect(externalRefs).toEqual([]);
  });

  test("every CSS url(./assets.new/...) points at a real file on disk", () => {
    const html = readFileSync(bundlePath, "utf8");
    const assetsDir = resolve(__dirname, "..", "..", "macos-app", "Resources", "assets.new");
    const refs = [...html.matchAll(/url\(['"]?\.\/assets\.new\/([^'")\s]+)['"]?\)/gi)].map((m) => m[1]);
    const missing = refs.filter((name) => !existsSync(resolve(assetsDir, name)));
    if (missing.length > 0) {
      throw new Error(
        `CSS url(./assets.new/...) references missing file(s): ${[...new Set(missing)].join(", ")}`,
      );
    }
    expect(missing).toEqual([]);
  });

  test("Instrument Serif @font-face is bundled (not CDN-loaded)", () => {
    const html = readFileSync(bundlePath, "utf8");
    // Must contain a @font-face for Instrument Serif pointing at a local file.
    expect(html).toMatch(/@font-face\s*\{[^}]*font-family:\s*["']Instrument Serif["'][\s\S]*?url\(['"]?\.\/assets\.new\//i);
    // Must NOT reference fonts.bunny.net, fonts.googleapis.com, fonts.gstatic.com.
    expect(html).not.toMatch(/fonts\.bunny\.net/i);
    expect(html).not.toMatch(/fonts\.googleapis\.com/i);
    expect(html).not.toMatch(/fonts\.gstatic\.com/i);
  });
});
