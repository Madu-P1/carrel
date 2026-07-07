import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const dist = join(root, "dist");
// The native macOS shell was extracted out of this repo on 2026-07-07.
// The bundle now lands in the repo-root dist/ directory rather than the
// old native-shell Resources path.
const resources = resolve(root, "..", "dist");
const htmlPath = join(dist, "index.html");
const outHtmlPath = join(resources, "app.new.html");
const outAssetsPath = join(resources, "assets.new");

const html = readFileSync(htmlPath, "utf8");
const scriptMatch = html.match(/<script type="module" crossorigin src="(.+?)"><\/script>/);
const stylesheetMatch = html.match(/<link rel="stylesheet" crossorigin href="(.+?)">/);

if (!scriptMatch || !stylesheetMatch) {
  throw new Error("Could not locate built asset references in dist/index.html");
}

const jsPath = join(dist, scriptMatch[1].replace(/^\.\//, ""));
const cssPath = join(dist, stylesheetMatch[1].replace(/^\.\//, ""));
const jsSource = readFileSync(jsPath, "utf8").replace(
  /\n?\/\/# sourceMappingURL=[^\r\n]+[\r\n]*$/u,
  "\n",
);
const cssRaw = readFileSync(cssPath, "utf8");

// Vite emits CSS url()s relative to dist/assets/. When the CSS is inlined into
// the bundled app.new.html, relative URLs now resolve against the bundle
// output dir, but the bundled assets are copied into assets.new/ beside it.
// Rewrite bare-relative url() paths so they land in assets.new/ under file://.
// We only touch url(./filename.ext) and url(filename.ext) forms; absolute URLs,
// data: URIs, and already-assets.new/-prefixed paths are left alone.
const cssAssetExts = [
  "woff2", "woff", "ttf", "otf", "eot",
  "png", "jpg", "jpeg", "gif", "webp", "svg", "avif",
  "mp3", "mp4", "webm", "wav", "ogg"
];
const assetExtPattern = cssAssetExts.join("|");
const css = cssRaw.replace(
  new RegExp(`url\\((['"]?)(\\.\\/)?([^'"\\)\\s]+\\.(?:${assetExtPattern}))\\1\\)`, "gi"),
  (match, quote, _dot, path) => {
    if (path.startsWith("assets.new/") || path.startsWith("/") || /^[a-z]+:/i.test(path)) {
      return match;
    }
    return `url(${quote}./assets.new/${path}${quote})`;
  },
);
const safeInline = (source) => source.replace(/<\/script/gi, "<\\/script");

/*
 * Rewrite every `import("./X.js")` so the dynamic chunk loader resolves
 * paths against the Resources/assets.new/ directory rather than against
 * the inlined HTML's own URL.
 *
 * Why this is necessary: the bundle inlines the entry JS into a
 * <script> inside app.new.html. Inside that inlined script, a relative
 * dynamic import like `import("./pdf.js")` is resolved against the
 * HTML's URL (e.g., file://.../Resources/app.new.html), so it looks for
 * .../Resources/pdf.js — but the actual chunk lives at
 * .../Resources/assets.new/pdf.js.
 *
 * The previous version of this script only rewrote pdf.js. After Ship
 * 8b's route-level lazy split landed `import("./ReaderView.js")`, the
 * Reader page silently failed to load under file:// because the chunk
 * URL resolved to a non-existent path. Generalize the rewrite to catch
 * ANY relative chunk import so future code splits don't trip the same
 * bug.
 *
 * Pattern: `import("./<filename>.js")` where filename is alphanumeric
 * + dash/underscore. Any chunk Vite emits that the entry pulls in via
 * a code-split point matches this shape. Absolute URLs, http(s)://,
 * and import.meta.url-based paths are left alone.
 */
// Runtime asset-base global. Renamed from __einsteinAssetBase to
// __carrelAssetBase in the 2026-04-29 Carrel rename. The contract lives
// entirely inside `frontend/` (this script writes it; pdfjs-setup.ts +
// the inlined entry JS read it), so the rename is safe without a
// backward-compat shim.
//
// The chunk-name body allows alphanumeric, dash, underscore, AND dot
// (the dot was added 2026-04-29 to match `three.module.js` — Vite
// preserves the original `.module` suffix when the source file is named
// `three.module.mjs`). Without it the regex stopped at "three" and
// failed to match `import("./three.module.js")`, so the rewrite skipped
// it AND the integrity check skipped it (same regex), and the bundled
// app shipped a relative dynamic import that 404'd at runtime under
// file:// with "Importing a module script failed." The dot lives only
// inside the body, never at the start or end, so a chunk literally
// named `..js` can't slip through.
const dynamicImportRewrite =
  /import\("\.\/([A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*\.js)"\)/g;
const rewrittenJsSource = [
  'window.__carrelAssetBase = window.__carrelAssetBase ?? new URL("./assets.new/", window.location.href).href;',
  jsSource
    .replace(dynamicImportRewrite, 'import(window.__carrelAssetBase + "$1")')
    .replaceAll("import.meta.url", "window.__carrelAssetBase")
].join("\n");

// Build-time integrity check: after the rewrite, no relative dynamic
// imports of the form `import("./*.js")` should survive. The check
// regex is intentionally MORE permissive than the rewrite regex
// (`[\w.\-]+\.js` matches anything alphanumeric + dots + dashes +
// underscores) so a chunk shape the rewrite hasn't been taught about
// fails the build LOUDLY here instead of silently reaching runtime.
// History: a previous regression shipped because the rewrite missed
// `three.module.js` and the check used the SAME regex, so the survivor
// passed the check too.
const integrityCheckRegex = /import\("\.\/([\w.\-]+\.js)"\)/g;
const survivingRelativeImports = [
  ...rewrittenJsSource.matchAll(integrityCheckRegex),
];
if (survivingRelativeImports.length > 0) {
  const examples = survivingRelativeImports
    .slice(0, 3)
    .map((m) => m[0])
    .join(", ");
  throw new Error(
    `Bundled HTML integrity check failed: ${survivingRelativeImports.length} ` +
      `relative dynamic import(s) survived the rewrite (e.g., ${examples}). ` +
      "Update the dynamicImportRewrite pattern in build-macos.mjs to match."
  );
}

const bundledHtml = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Cachet Engine</title>
    <link rel="preconnect" href="http://127.0.0.1:8000" />
    <style>
${css}
    </style>
    <script type="module">
${safeInline(rewrittenJsSource)}
    </script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
`;

// Integrity checks. Every failure mode that would ship a broken bundle should
// fail the build here, not at runtime inside WKWebView.

if ((bundledHtml.match(/<!doctype html>/gi) ?? []).length !== 1) {
  throw new Error("Bundled HTML integrity check failed: expected exactly one <!doctype html> marker");
}

// Per-block scan: no <script>...</script> body may contain a </script substring.
// This is the only check that actually prevents the HTML parser from closing
// an inline script early when inlined JS happens to include the literal markup.
// Catches the root-cause class of bug regardless of how many script tags exist.
const scriptBlocks = [...bundledHtml.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\b[^>]*>/gi)];
const offendingBlockIndex = scriptBlocks.findIndex((match) => /<\/script/i.test(match[1]));
if (offendingBlockIndex !== -1) {
  throw new Error(
    `Bundled HTML integrity check failed: script block #${offendingBlockIndex} contains a </script substring. ` +
    "The HTML parser will close the <script> tag early and render the rest as body text. " +
    "Escape via safeInline() before inlining any JS."
  );
}

// Structural sanity: opens and closes match.
const openCount = (bundledHtml.match(/<script\b/gi) ?? []).length;
const closeCount = (bundledHtml.match(/<\/script>/gi) ?? []).length;
if (openCount !== closeCount) {
  throw new Error(
    `Bundled HTML integrity check failed: ${openCount} <script> opens vs ${closeCount} closes`
  );
}

if (bundledHtml.includes("sourceMappingURL=")) {
  throw new Error("Bundled HTML integrity check failed: source map reference found in app.new.html");
}

// No asset path should reference the pre-bundle Vite output directory, because
// ./assets/ is not copied into the bundle output dir — only ./assets.new/ is.
if (bundledHtml.includes('src="./assets/index.js"')) {
  throw new Error('Bundled HTML integrity check failed: stale "./assets/index.js" reference found');
}

// Every <script src=...> must point at ./assets.new/... or be absent (we inline main bundle).
const externalSrcs = [...bundledHtml.matchAll(/<script\b[^>]*\bsrc="([^"]+)"/gi)].map((m) => m[1]);
const badSrcs = externalSrcs.filter((src) => !src.startsWith("./assets.new/"));
if (badSrcs.length > 0) {
  throw new Error(
    `Bundled HTML integrity check failed: unresolvable script src(s) under file://: ${badSrcs.join(", ")}`
  );
}

// CSS url() paths that point at assets.new/ must actually exist on disk after
// the copy step. Catches typos or rename drift in the font/asset set.
// We check before assets.new/ is (re)written, against dist/assets/ which is
// the canonical source that will be copied.
const cssUrlMatches = [...bundledHtml.matchAll(/url\(['"]?\.\/assets\.new\/([^'")\s]+)['"]?\)/gi)];
const missingAssets = [];
for (const match of cssUrlMatches) {
  const assetName = match[1];
  if (!existsSync(join(dist, "assets", assetName))) {
    missingAssets.push(assetName);
  }
}
if (missingAssets.length > 0) {
  throw new Error(
    `Bundled HTML integrity check failed: CSS references missing asset(s): ${[...new Set(missingAssets)].join(", ")}. ` +
    "Ensure the files exist in frontend/src/assets/ and are imported by a bundled stylesheet."
  );
}

// The PDF.js worker stays as a normal file under assets.new/ so app launch does
// not eagerly decode a large base64 blob. Reader code resolves this URL lazily.
if (!existsSync(join(dist, "assets", "pdf.worker.min.mjs"))) {
  throw new Error(
    "Bundled HTML integrity check failed: pdf.worker.min.mjs is missing from dist/assets. " +
    "The Reader expects the worker to be copied to Resources/assets.new/."
  );
}

// Local-first guard: the bundle must not reference any third-party CDN host.
// A render-blocking external stylesheet or font URL breaks offline behavior
// and pays DNS+TLS on every cold launch — both are architectural mistakes
// for this product. Fonts are self-hosted under src/assets/fonts/.
const externalHostPattern = /(href|src)="https?:\/\/(?!127\.0\.0\.1|localhost)/i;
if (externalHostPattern.test(bundledHtml)) {
  const matches = [...bundledHtml.matchAll(/(href|src)="(https?:\/\/(?!127\.0\.0\.1|localhost)[^"]+)"/gi)].map((m) => m[2]);
  throw new Error(
    `Bundled HTML integrity check failed: external-host reference(s) detected: ${matches.join(", ")}. ` +
    "Local-first: all assets must be bundled. Self-host fonts and scripts instead of using a CDN."
  );
}

mkdirSync(resources, { recursive: true });
rmSync(outHtmlPath, { force: true });
rmSync(outAssetsPath, { recursive: true, force: true });
writeFileSync(outHtmlPath, bundledHtml);

if (existsSync(join(dist, "assets"))) {
  cpSync(join(dist, "assets"), outAssetsPath, { recursive: true });
}
