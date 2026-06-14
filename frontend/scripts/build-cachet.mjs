import { build } from "vite";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/*
 * build-cachet.mjs — the Carrel-style local build for the STANDALONE Cachet app.
 *
 * Mirrors build-macos.mjs (which emits Carrel's app.new.html) but for Cachet: a
 * SEPARATE single-entry Vite build of cachet.html, so Carrel's build is never
 * perturbed (no shared multi-entry chunking), inlined into one self-contained
 * file:// HTML for the macOS WKWebView shell. The Cachet bundle is Carrel-free
 * by construction: cachet.html reaches only CachetApp + the verify/shelf
 * surfaces + the design system, so Vite tree-shakes every Carrel feature out.
 *
 * Output: macos-app/Resources/cachet.new.html + cachet-assets.new/, parallel to
 * Carrel's app.new.html + assets.new/. The Cachet .app is the generic Swift
 * shell pointed at cachet.new.html; that wiring is the Xcode/GUI packaging step.
 *
 * DEBT: the inliner below is adapted from build-macos.mjs (~90% shared). Extract
 * into scripts/lib/ once both are stable; kept separate for now so this build
 * never risks Carrel's verify-chain build.
 */

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, ".."); // frontend/
const dist = join(root, "dist-cachet");
const resources = resolve(root, "..", "macos-app", "Resources");
const srcHtml = resolve(root, "cachet.html"); // the Vite entry (source)
const htmlPath = join(dist, "cachet.html"); // the built output to inline
const outHtmlPath = join(resources, "cachet.new.html");
const outAssetsPath = join(resources, "cachet-assets.new");
const ASSETS_DIR = "cachet-assets.new";

// 1) Separate single-entry build of cachet.html into dist-cachet/.
await build({
  root,
  build: {
    outDir: "dist-cachet",
    emptyOutDir: true,
    rollupOptions: { input: srcHtml },
  },
});

// 2) Inline the build into one self-contained file:// HTML (mirrors build-macos).
const html = readFileSync(htmlPath, "utf8");
const scriptMatch = html.match(/<script type="module" crossorigin src="(.+?)"><\/script>/);
const stylesheetMatch = html.match(/<link rel="stylesheet" crossorigin href="(.+?)">/);
if (!scriptMatch || !stylesheetMatch) {
  throw new Error("Could not locate built asset references in dist-cachet/cachet.html");
}

const jsPath = join(dist, scriptMatch[1].replace(/^\.\//, ""));
const cssPath = join(dist, stylesheetMatch[1].replace(/^\.\//, ""));
const jsSource = readFileSync(jsPath, "utf8").replace(
  /\n?\/\/# sourceMappingURL=[^\r\n]+[\r\n]*$/u,
  "\n",
);
const cssRaw = readFileSync(cssPath, "utf8");

const cssAssetExts = [
  "woff2", "woff", "ttf", "otf", "eot",
  "png", "jpg", "jpeg", "gif", "webp", "svg", "avif",
  "mp3", "mp4", "webm", "wav", "ogg",
];
const assetExtPattern = cssAssetExts.join("|");
const css = cssRaw.replace(
  new RegExp(`url\\((['"]?)(\\.\\/)?([^'"\\)\\s]+\\.(?:${assetExtPattern}))\\1\\)`, "gi"),
  (match, quote, _dot, path) => {
    if (path.startsWith(`${ASSETS_DIR}/`) || path.startsWith("/") || /^[a-z]+:/i.test(path)) {
      return match;
    }
    return `url(${quote}./${ASSETS_DIR}/${path}${quote})`;
  },
);
const safeInline = (source) => source.replace(/<\/script/gi, "<\\/script");

// Rewrite relative dynamic imports + import.meta.url against the asset base, so
// any future code-split chunk resolves under file://. Cachet has none today, so
// this is a no-op guard, but it keeps the contract identical to Carrel's.
const dynamicImportRewrite = /import\("\.\/([A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*\.js)"\)/g;
const rewrittenJsSource = [
  `window.__carrelAssetBase = window.__carrelAssetBase ?? new URL("./${ASSETS_DIR}/", window.location.href).href;`,
  jsSource
    .replace(dynamicImportRewrite, 'import(window.__carrelAssetBase + "$1")')
    .replaceAll("import.meta.url", "window.__carrelAssetBase"),
].join("\n");

const integrityCheckRegex = /import\("\.\/([\w.\-]+\.js)"\)/g;
const surviving = [...rewrittenJsSource.matchAll(integrityCheckRegex)];
if (surviving.length > 0) {
  const examples = surviving.slice(0, 3).map((m) => m[0]).join(", ");
  throw new Error(
    `Cachet bundle integrity check failed: ${surviving.length} relative dynamic ` +
      `import(s) survived the rewrite (e.g., ${examples}).`,
  );
}

const bundledHtml = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Cachet</title>
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

// Integrity checks (mirror build-macos; no pdf.worker — Cachet has no reader).
if ((bundledHtml.match(/<!doctype html>/gi) ?? []).length !== 1) {
  throw new Error("Cachet bundle: expected exactly one <!doctype html> marker");
}
const scriptBlocks = [...bundledHtml.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\b[^>]*>/gi)];
if (scriptBlocks.findIndex((m) => /<\/script/i.test(m[1])) !== -1) {
  throw new Error("Cachet bundle: a <script> body contains a </script substring; escape via safeInline().");
}
const opens = (bundledHtml.match(/<script\b/gi) ?? []).length;
const closes = (bundledHtml.match(/<\/script\b[^>]*>/gi) ?? []).length;
if (opens !== closes) {
  throw new Error(`Cachet bundle: ${opens} <script> opens vs ${closes} closes`);
}
if (bundledHtml.includes("sourceMappingURL=")) {
  throw new Error("Cachet bundle: source map reference found");
}
const externalSrcs = [...bundledHtml.matchAll(/<script\b[^>]*\bsrc="([^"]+)"/gi)].map((m) => m[1]);
const badSrcs = externalSrcs.filter((src) => !src.startsWith(`./${ASSETS_DIR}/`));
if (badSrcs.length > 0) {
  throw new Error(`Cachet bundle: unresolvable script src(s) under file://: ${badSrcs.join(", ")}`);
}
const cssUrlMatches = [
  ...bundledHtml.matchAll(new RegExp(`url\\(['"]?\\.\\/${ASSETS_DIR}\\/([^'")\\s]+)['"]?\\)`, "gi")),
];
const missingAssets = [];
for (const match of cssUrlMatches) {
  if (!existsSync(join(dist, "assets", match[1]))) missingAssets.push(match[1]);
}
if (missingAssets.length > 0) {
  throw new Error(
    `Cachet bundle: CSS references missing asset(s): ${[...new Set(missingAssets)].join(", ")}`,
  );
}
// Local-first: no third-party CDN host may survive into the bundle.
const externalHostPattern = /(href|src)="https?:\/\/(?!127\.0\.0\.1|localhost)/i;
if (externalHostPattern.test(bundledHtml)) {
  const matches = [
    ...bundledHtml.matchAll(/(href|src)="(https?:\/\/(?!127\.0\.0\.1|localhost)[^"]+)"/gi),
  ].map((m) => m[2]);
  throw new Error(`Cachet bundle: external-host reference(s) detected: ${matches.join(", ")}`);
}

mkdirSync(resources, { recursive: true });
rmSync(outHtmlPath, { force: true });
rmSync(outAssetsPath, { recursive: true, force: true });
writeFileSync(outHtmlPath, bundledHtml);
if (existsSync(join(dist, "assets"))) {
  cpSync(join(dist, "assets"), outAssetsPath, { recursive: true });
}
console.log(`Cachet bundle written: ${outHtmlPath} (+ ${ASSETS_DIR}/)`);
