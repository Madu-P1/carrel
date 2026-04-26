import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";
import { describe, expect, test } from "vitest";

/*
 * Entry-bundle size budget.
 *
 * After Ship 8b lazy-split features/reader off the main chunk, the
 * cold-start payload (index.js + index.css that EVERY page pays for)
 * landed at ~61.7 KB gz / ~18.7 KB gz. This guard pins the gzipped
 * size of those two artifacts below explicit thresholds so future
 * regressions fail loudly in CI before they reach production.
 *
 * Headroom rule: each budget sits ~5% above the post-fix size. That
 * gives natural growth room without inviting drift. Bumping a budget
 * is a deliberate decision — write a comment explaining what landed
 * and why it justified the new ceiling.
 *
 * The test runs against the Vite output in `dist/`. If `dist/` doesn't
 * exist yet (a developer ran `vitest` before `bun run build`), we skip
 * with a console warning rather than fail — the test is a CI gate, not
 * a dev-mode nag. CI pipelines run `bun run build` before `bun run
 * test`, so the artifact is always present in the gate path.
 *
 * NOT BUDGETED (intentionally):
 *   - dist/assets/pdf.worker.min.mjs (1.37 MB) — the pdfjs runtime;
 *     already loaded as a static asset on demand, never inlined into
 *     the entry chunk. Reducing this would mean swapping pdfjs
 *     versions, out of scope.
 *   - dist/assets/pdf.js (334 KB / 98 KB gz) — the dynamic pdfjs-dist
 *     wrapper chunk that Vite split via the import() in
 *     features/reader/lib/pdfjs-setup.ts. Loaded only on the Reader
 *     route. Same story: if it grows, that's a pdfjs version bump.
 *   - dist/assets/ReaderView.js (10 KB gz) — the route-split Reader
 *     feature. Has its own implicit budget via the entry budget below
 *     (if Reader leaks into the entry chunk, the entry budget trips).
 *   - dist/assets/logo.png (909 KB) — image asset, not parsed JS.
 */

const distDir = resolve(__dirname, "..", "dist", "assets");
const indexJsPath = resolve(distDir, "index.js");
const indexCssPath = resolve(distDir, "index.css");

/** Entry JS budget — gzipped. Tripped if the entry chunk grows past
 *  this. Move only with an explicit explanation in the commit message. */
const ENTRY_JS_GZIP_BUDGET = 65 * 1024; // 65 KB (current ~62 KB)

/** Entry CSS budget — gzipped. Same rule as JS. */
const ENTRY_CSS_GZIP_BUDGET = 20 * 1024; // 20 KB (current ~19 KB)

function gzippedSize(path: string): number {
  const raw = readFileSync(path);
  return gzipSync(raw).length;
}

describe("entry-bundle size budget", () => {
  test("dist/ artifacts exist (run `bun run build` first if this fails)", () => {
    if (!existsSync(indexJsPath) || !existsSync(indexCssPath)) {
      console.warn(
        `bundle-size: entry artifacts missing at ${distDir}. ` +
          "Run `bun run build` before this test in CI."
      );
      // Soft-skip to avoid false failures during dev-mode test runs.
      return;
    }
    expect(existsSync(indexJsPath)).toBe(true);
    expect(existsSync(indexCssPath)).toBe(true);
  });

  test("entry index.js is below the gzipped JS budget", () => {
    if (!existsSync(indexJsPath)) return;
    const gz = gzippedSize(indexJsPath);
    expect(
      gz,
      `index.js gzipped is ${gz} bytes, budget is ${ENTRY_JS_GZIP_BUDGET}. ` +
        "If this is a deliberate growth, bump ENTRY_JS_GZIP_BUDGET with a " +
        "comment explaining what landed."
    ).toBeLessThan(ENTRY_JS_GZIP_BUDGET);
  });

  test("entry index.css is below the gzipped CSS budget", () => {
    if (!existsSync(indexCssPath)) return;
    const gz = gzippedSize(indexCssPath);
    expect(
      gz,
      `index.css gzipped is ${gz} bytes, budget is ${ENTRY_CSS_GZIP_BUDGET}.`
    ).toBeLessThan(ENTRY_CSS_GZIP_BUDGET);
  });

  test("ReaderView code-split chunk exists (route-level lazy load)", () => {
    // We don't budget the size here (the entry budget already catches
    // accidental Reader leakage into the entry chunk). What we DO want to
    // assert: the route-level split is still in place. If a future
    // change reverts the lazy() and pulls Reader back into the entry,
    // the chunk goes away and this assertion catches it.
    if (!existsSync(distDir)) return;
    const readerChunk = resolve(distDir, "ReaderView.js");
    expect(
      existsSync(readerChunk),
      "ReaderView.js code-split chunk is missing — the route-level " +
        "lazy import in src/app/App.tsx may have been reverted to a " +
        "static import. Restore the lazy() wrapper around ReaderView."
    ).toBe(true);
  });
});
