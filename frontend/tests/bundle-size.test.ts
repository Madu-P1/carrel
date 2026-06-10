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
 *   - dist/assets/logo.png (909 KB) — image asset, not parsed JS.
 *
 * NOTE on the entry budget: Ship 7ac8931 briefly route-split Reader off
 * the entry chunk via `lazy()` + `Suspense`. That worked in `bun run
 * dev` but produced a blank Reader pane under the bundled file://
 * macOS shell — preact/compat's Suspense + lazy combination didn't
 * re-render the tree after the chunk resolved. Reverted to a static
 * import; the entry budget below is sized to fit the static-import
 * payload again (~68 KB gz). Future code splits should be triggered by
 * user action (e.g., a click handler that does `await import(...)`)
 * rather than render-time Suspense, until preact/compat's lazy
 * behavior is verified under file://.
 */

const distDir = resolve(__dirname, "..", "dist", "assets");
const indexJsPath = resolve(distDir, "index.js");
const indexCssPath = resolve(distDir, "index.css");

/** Entry JS budget — gzipped. Tripped if the entry chunk grows past
 *  this. Move only with an explicit explanation in the commit message.
 *
 *  History:
 *    65 KB → 72 KB: ReaderView un-split (preact/compat Suspense bug)
 *    72 KB → 78 KB: Plan feature added (calendar feeds + WeekTimeGrid +
 *                    AddFeedDialog + SuggestionCard + usePlan + utils
 *                    + 4 Pydantic-shaped API types) ~73.6 KB live.
 *    78 KB → 84 KB: Search MVP + 3D Concepts + WeakConceptsRail. The
 *                    three.js + 3d-force-graph libs are lazy-imported
 *                    (separate chunks: ~189 KB gz three, ~218 KB gz
 *                    3d-force-graph) so the entry chunk only carries
 *                    the dynamic-import wiring and the new view module
 *                    IDs (~7 KB gz delta). Entry now lands at ~81.5 KB
 *                    gz live.
 *    84 KB → 85 KB: Public-beta Jobs Tray, first-run tour, evidence
 *                    inspector, and Anchor Column wiring. Core loop
 *                    visibility is entry-shell behavior, not route-only.
 *    85 KB → 87 KB: resolver-backed citation preview cards plus the
 *                    replayable animated first-run tour. Both are
 *                    trust/onboarding shell affordances and need to be
 *                    present before route-level lazy boundaries.
 *    87 KB → 89 KB: tutorial mockup upgraded with state-specific visual
 *                    narration and SVG citation-to-anchor guidance.
 *    89 KB → 92 KB: shell-level Reader focus command, route motion,
 *                    persistent resizable panels, and public-beta chrome
 *                    all execute before route-level lazy boundaries.
 *    92 KB → 93 KB: local-only usage event helper plus Reader menu/find
 *                    restoration wiring. Metrics are shell-adjacent and
 *                    intentionally available across first-run, Library,
 *                    Reader, Ask, and Study flows.
 *    93 KB → 97 KB: audit Phase 1 hardening added typed API timeouts,
 *                    stable Ask route/focus contracts, onboarding state
 *                    controller, and compact shell status wiring. These
 *                    are app-shell reliability paths, not lazy feature
 *                    detail.
 *    97 KB → 100 KB: Ask-pipeline UI + Study card overhaul shipped:
 *                    PR 4.1's AskCard / AskCardList / useAskCards;
 *                    PR 4.2's useNodeDeepLink + reader.fetchNode;
 *                    S-1's SrsSubjectScopePill + study scope state;
 *                    S-2's FlipCard / RatingRow / StudyFocusOverlay.
 *                    Live size at the bump: ~99.6 KB gz. Headroom
 *                    (~400 bytes) is deliberately tight to keep the
 *                    next addition honest about its weight.
 *   100 KB → 105 KB: Phase A Notes redesign (Stillwater + Liquid Glass).
 *                    New components: NoteTile (collapsed + inline-edit
 *                    expanded with autosave), UnsortedInbox (file-to-folder
 *                    inline), NotesIcons (Stillwater SVG set), the rebuilt
 *                    SubjectRail/NotesPane and the NotesPage glass tokens.
 *                    Adds the appShell.notesRailReplacement signal that
 *                    swaps the AppShell rail for the page's own rail on
 *                    /notes. Live size at the bump: ~103.5 KB gz.
 *   105 KB → 108 KB: Notes Phase A polish + single-rail architecture.
 *                    Rail content now swaps inside the AppShell sidebar
 *                    (one Carrel brand mark across the app) — adds
 *                    notes/state.ts module-level signals so SubjectRail
 *                    and NotesPage share selection. Polish: ⌘K search
 *                    focus, Esc to collapse a tile, tile expand
 *                    animation, autosave race fix, scroll-into-view on
 *                    expand, zero-count badge hiding, move-select
 *                    cleanup, empty-state copy. Live: ~106.5 KB gz.
 * 2026-05-18 (+4 KB): Notes Phase A squash-merge onto main brought
 *                    over additional Notes editor surface area + the
 *                    new ErrorBoundary / LoadingBoundary / Markdown
 *                    primitives + companion-cube updates. Live: ~108
 *                    KB gz.
 * 2026-05-29 (budget 112 -> 120 KB): Cachet verify-as-hero slice 1.
 *                    The verdict-taxonomy disposition logic, the
 *                    one-click SourceInspector, and the certification
 *                    model + print exhibit, statically imported via the
 *                    /verify route. Live: ~114.7 KB gz. Route-splitting
 *                    /verify via click-time import is the lean-entry
 *                    option, deferred per the file:// Suspense
 *                    constraint (see CLAUDE.md). */
// Bumped 120 -> 124 KB for Cachet PR5b: the Workspace/Margin layout adds three
// components (WorkspaceMargin, ExaminationDrawer, the segmentation + rail-layout
// helpers) on the verify surface.
// Bumped 124 -> 125 KB for the deterministic verify engine UI (certification
// exhibit with inline SHA-256, the local/cloud attestation, abbreviation-aware
// disposition logic): ~124.5 KB gz live. Route-splitting /verify at click time
// stays the lean-entry option, deferred per the file:// Suspense constraint
// (see CLAUDE.md).
// Bumped 125 -> 126 KB for the Cachet Vault manager UI (grid + detail two-mode
// layout, the solid VaultMark folder, and the grid-aware drag-to-move with its
// destination-naming confirm): ~125.1 KB gz live. CachetApp is statically imported
// from main.tsx, so the vault UI ships in the Carrel entry too; dynamic-importing
// the Cachet shell out of the entry is the lean follow-up, deferred per the same
// file:// Suspense constraint.
// Bumped 126 -> 127 KB for verdict survival (audit O1): useVerify state moved
// from useState to a signal-backed VerifyStore so the lectern's verdict —
// settled or still streaming — survives the shell's unmount-on-nav, plus the
// markSealed engine seam that keeps the quiet Save hidden after a seal across
// remounts. ~126.1 KB gz live; the prior 2026-06-10 fixes had already bought
// back their own weight via DEV-gating, so this is the first real growth.
const ENTRY_JS_GZIP_BUDGET = 127 * 1024;

/** Entry CSS budget — gzipped. Same rule as JS.
 *
 *  History:
 *    20 KB → 23 KB: ReaderView un-split
 *    23 KB → 25 KB: Plan feature CSS modules (~22.6 KB live)
 *    25 KB → 26 KB: Public-beta Jobs Tray, evidence, and Anchor Drawer
 *                    module styles.
 *    26 KB → 28 KB: custom first-run tour motion stage and rich citation
 *                    preview card styling.
 *    28 KB → 29 KB: centered first-run app frame, SVG arrow animation,
 *                    and denser responsive polish for the tutorial.
 *    29 KB → 32 KB: visible Liquid Glass treatment moved into shared
 *                    shell/primitives so the effect shows inside the
 *                    WKWebView app surface, not only behind it.
 *    32 KB → 34 KB: current app-shell CSS settled above the old ceiling
 *                    after the Reader panel/focus and first-run surfaces;
 *                    no new route-only styling is hidden in this budget.
 *    34 KB → 36 KB: Phase A Notes Stillwater + Liquid Glass styles —
 *                    NotesPage palette tokens (light + dark), translucent
 *                    rail / inbox / tile surfaces with backdrop-filter blur,
 *                    serif tile headers + cite-pill chrome. Plus the
 *                    AppShell `.bodyNotesRail` rule that collapses the
 *                    grid when the page owns the left rail.
 *    36 KB → 38 KB: Phase A polish + global Stillwater token sheet
 *                    (notes-tokens.css) so the rail content reads the
 *                    same --np-* vars whether rendered in NotesPage or in
 *                    the AppShell sidebar's swap slot. Tile expand
 *                    animation + scroll-into-view styles, move-select
 *                    chevron pseudo, empty-state action chrome.
 *    38 KB → 40 KB: Full-page Note Editor (Word-doc-style writing
 *                    surface) — NoteEditor.module.css ships toolbar
 *                    chrome, sticky topbar, the 720px "sheet" Liquid
 *                    Glass panel, contenteditable body type rules
 *                    (h1/h2/h3/p/ul/ol/blockquote/pre/em/strong), 404
 *                    state. Adds the /notes/:id route.
 *    40 KB → 42 KB: Cachet verify-as-hero slice 1. Scoped .verifyScope
 *                    paper/ink/oxblood token layer, the side-by-side
 *                    SourceInspector, and the print-isolated
 *                    certification exhibit. Live: ~40.5 KB gz. */
// Bumped 42 -> 44 KB for Cachet PR5b: the Workspace/Margin/Examination styles
// (document body, margin rail + notes, unplaced tray, slide-in drawer).
// Bumped 44 -> 45 KB for the drawer-geometry fixes (2026-06-10): the
// Examination drawer became viewport-fixed (it was pinned to a page ancestor,
// producing dead bands and scroll-clipped columns at wide windows), the
// verdict surface shifts beside the open drawer at >=1081px instead of
// underneath it, and the shell clips horizontal overflow. ~45.0 KB gz live
// (the prior ceiling had 49 bytes of headroom; this is real geometry, not drift).
const ENTRY_CSS_GZIP_BUDGET = 45 * 1024;

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

});
