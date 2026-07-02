# ADR-0016: Cachet ships as a cross-platform desktop app — Tauri shell, Python engine sidecar

- Status: Accepted (operator directive, 2026-07-02)
- Date: 2026-07-02
- References: [ADR-0015](ADR-0015-attestation-layer-north-star.md) (attestation-layer north star,
  daemon as the single embedding target), [ADR-0014](ADR-0014-cachet-verification-kernel-with-surfaces.md)
  (kernel-with-surfaces), [ADR-0011] (Cachet extraction, strangler-in-place), the 2026-06-26
  Harvey-council verdict (the macOS-only shell named the FATAL gap for the Wedge-2 Windows buyer).

## Context

The operator directs that Cachet be distributed as a real desktop application on BOTH Windows and
macOS — an app, not a web app. Today Cachet's product surface lives inside the Carrel repo as a
Preact bundle hosted by a macOS-only Swift/WKWebView shell, talking to the FastAPI backend over
loopback with an injected token. The Harvey council independently identified macOS-only
distribution as fatal for the no-cloud in-house wedge: the regulated GC buyer runs Windows.

The question decided here: what shell and packaging carry Cachet to both OSes, and does the move
affect the product's constitution (zero-egress provable at runtime, deterministic kernel as the
only verdict authority, three-state contract, loopback-only wire with token auth, honest-refusal
invariants)?

## Decision

**Shell: Tauri 2.** One codebase, system webviews — WKWebView on macOS (the same engine the
current shell already targets, so every hard-won WKWebView lesson carries over) and WebView2 on
Windows (evergreen Chromium). The shell's job is deliberately small: create the window, spawn and
supervise the engine sidecar, inject the per-session token before any JS runs (the same discipline
as today's WKUserScript injection), and lock the webview down (CSP `connect-src` loopback only, no
shell-open, no fs access from the page).

**Engine: the existing Python backend as a bundled sidecar.** The frontend's wire contract
(`/api/verify`, `/api/verify/stream` SSE, `/api/attest`, `/api/briefs`, `/api/documents`,
`/api/vaults`, token header, loopback base URL) is frozen by the redesign ground-truth doc and by
ADR-0015's additive-only rule. The sidecar is a PyInstaller-frozen slice of the FastAPI app
serving exactly that contract on an ephemeral loopback port, with the kernel inside it. Per
ADR-0015 build order, the loopback daemon remains the single embedding TARGET; the FastAPI slice
is the daemon's superset today and shrinks toward it as the strangler-fig proceeds
(ADR-0011/0014). SQLite moves to the per-OS app-data directory.

**Frontend: one Preact bundle, unchanged wire contract.** The redesigned frontend is
shell-agnostic by construction: it speaks the frozen loopback contract and nothing else, so the
SAME bundle serves the current macOS WKWebView shell during transition and the Tauri app at
distribution. Nothing in the redesign needs to know Tauri exists.

## Alternatives rejected

- **Electron.** The strongest counter: maturity, tooling breadth, no Rust exposure. Rejected
  because both decisive axes here favor Tauri: (1) the trust narrative — Cachet's pitch is
  auditable, on-device, zero-egress; shipping a minimal shell over the OS webview with a small
  Rust core is a materially better story than bundling Chromium+Node (a full network-capable
  runtime) into a product whose moat is "no data leaves this device"; (2) footprint — ~15 MB vs
  ~250 MB matters on a locked-down GC laptop. The shell code Cachet needs is a few hundred lines;
  Electron's ecosystem breadth buys nothing here.
- **Dual native (keep Swift shell, add WinUI/.NET).** Two shells, two chrome implementations,
  double the surface for every future change — against the prime directive, and it delays the
  Windows ship the council called fatal. The Swift shell remains for Carrel; Cachet's
  distribution moves to Tauri on both OSes.
- **Web app / PWA.** Excluded by operator directive, and structurally wrong: the no-cloud promise
  requires the engine on the user's machine.

## Does this affect the constitution?

**No — it executes it.** ADR-0015 build order #3 made the loopback daemon the single embedding
target precisely so surfaces could multiply without touching the trust spine. The desktop app is
the first non-macOS proof of that design.

Preserved unchanged: zero-egress as a runtime-provable process property (socket-ban stays in CI;
the packet-capture proof gains a Windows leg); the deterministic kernel as sole verdict authority;
the three-state contract and every §8 honesty invariant (they live in the kernel and the UI logic
modules, not in any shell); loopback-only + per-session token auth (injection mechanism ports
1:1); the additive-only wire contract.

Consequences (additive, now load-bearing):
1. **Kernel/back-end bundling debt is pulled forward.** The engine slice must freeze cleanly
   (PyInstaller) for mac-arm64/x64 and win-x64; the `services.legal` weld inside
   `cachet_verify/adapter.py` (the standalone-install item) is now on the critical path.
2. **Signing becomes real work on two platforms**: Apple notarization (Phase 4 debt) plus Windows
   Authenticode. Unsigned builds are fine for validation demos; distribution needs certs.
3. **CI gains a Windows job** for the engine tests + the egress proof.
4. The system-topology docs change one row: "macOS shell" becomes "desktop shell (Tauri, Win+Mac)";
   the Swift shell stays as Carrel's host.
5. The frontend redesign (in flight) targets the frozen wire contract only — it is the Tauri app's
   UI with zero rework.

## Revisit triggers

- Tauri's webview fragmentation produces a real rendering defect the bundle cannot work around
  (fallback: Electron, accepting the size/trust cost).
- The buyer requires an OS the system webview story does not cover.
- The engine slice proves unfreezeable at acceptable size (fallback: embedded CPython runtime).
