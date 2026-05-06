# Carrel — Android Strategy

> Status: decision document. Implementation kicks off after first-paid-user milestone. Author: solo founder + autonomous overnight session, 2026-05-07.

## Decision

**Ship Android via Capacitor.** Wrap the existing Vite + Preact + TypeScript bundle in a Capacitor Android shell (Kotlin host). Reuse 100% of the frontend codebase. Reuse 100% of the FastAPI backend, deployed to a hosted endpoint. The mobile app is a thin shell + the same web bundle + native plugins for the few capabilities that actually need them.

## Why Capacitor (vs. the alternatives)

Three viable paths were evaluated.

### Path A — Capacitor (chosen)

**What it is:** Ionic's Capacitor wraps the existing web bundle in a native Android (Kotlin) and iOS (Swift) shell. The webview hosts the Preact app exactly as it runs on macOS. Native plugins are added for camera, file picker, calendar, push notifications, biometrics.

**Pros:**
- Zero frontend rewrite. Every existing route, hook, design-system primitive, animation, and test ports for free.
- The dual-Preact-instance fix already landed for `file://`-style asset loading; Capacitor uses a similar scheme.
- One engineer can ship Android in 4-6 weeks and iOS in another 2-3.
- Updates to the web bundle ship without an app-store review for non-native changes (live reload).
- Plugin ecosystem covers everything we need: `@capacitor/camera`, `@capacitor/filesystem`, `@capacitor/push-notifications`, `@capgo/native-audio`, etc.
- Production proof: Notion, Khan Academy use webview-wrapped mobile apps successfully.

**Cons:**
- WebView performance is slightly worse than native, especially on low-end Android devices. Mitigation: Carrel's bundle is 47KB gz; we are not the bottleneck.
- Animations that depend on WKWebView-specific Safari behavior may need testing on Android WebView (Chrome). The citation-flight FLIP animation in particular needs verification.
- Android File Provider integration for "share to Carrel" intents requires a small plugin.
- App-store review for the shell still required (one-time per platform).

### Path B — Tauri Mobile

**What it is:** Tauri's mobile alpha. Rust host, webview UI. Same code-reuse story as Capacitor but with a Rust runtime instead of native Kotlin/Swift.

**Pros:**
- Tiny binary (~5MB vs Capacitor's 25-40MB).
- Rust toolchain is cleaner than the native mobile build chain.
- One stack from desktop (already considered for v2 of the macOS shell) through mobile.

**Cons:**
- Alpha. Documented churn. Plugin ecosystem is empty compared to Capacitor.
- Solo founder + alpha tooling = avoidable risk.
- No production deployments at scale to learn from.

**Verdict:** revisit in 12 months.

### Path C — Separate React Native app

**What it is:** Build a separate React Native app from scratch. Share only the FastAPI backend.

**Pros:**
- Truly native UI components. Best perceived performance on Android.
- React Native has the largest mobile-dev hiring pool.
- Animations can be 60fps on lower-end devices via Reanimated.

**Cons:**
- Forks the codebase. Every feature now has to be built twice. Design system has to be re-implemented.
- The hire is a senior React Native engineer, not a generalist. Salary ~$180K-220K in the US, vs ~$140K for a Capacitor-savvy generalist.
- Time to first Android build: 4-6 months vs 4-6 weeks for Capacitor.
- The argument for native UI is weakest in Carrel's category — students compare us to Notion and Quizlet, both of which use web-shell mobile apps.

**Verdict:** the right answer if the round were $5M and the team were 8 people. Wrong answer for a $750K seed.

## The constraints Capacitor will hit (and the fixes)

Going through the existing macOS-specific code to identify what won't survive a port without intervention:

### 1. `file://` asset resolution — partially fixed already

The `frontend/scripts/build-macos.mjs` script today rewrites dynamic imports to use `window.__carrelAssetBase` for the `assets.new/` directory. Capacitor uses an `https://localhost` scheme for served assets, not `file://`. The asset-base abstraction we already have works directly: just compute it from `window.location.href` instead of `import.meta.url`.

**Action:** add a `build-android.mjs` parallel to `build-macos.mjs` that emits the same bundle into the Capacitor `android/app/src/main/assets/public/` directory. Reuse the dynamic-import rewrite verbatim.

**Effort:** half a day.

### 2. WKWebView-specific behaviors

Audit findings (from `frontend/src/`):

- **`OutlineRail.tsx`** uses `-webkit-` prefixed CSS for `backdrop-filter`. Android Chrome WebView supports unprefixed `backdrop-filter` since Chrome 76. **Fix:** add the unprefixed version alongside.
- **`Dialog.tsx`** uses `-webkit-tap-highlight-color`. Same fix.
- **PDF rendering** uses `pdf.js` which works fine in any WebView; no change.
- **Citation-flight animation** uses WAAPI + FLIP. Android WebView supports this. **Verify on a real device.**
- **No `_native_` Swift bridges** to call from the frontend. The macOS Swift shell does its own thing (window chrome, app menu, file picker) but the web bundle does not call into it. This is good — nothing to port.

**Action:** prefix-audit pass through `frontend/src/design-system/` to add unprefixed properties. Probably one batch edit, ~30 min.

### 3. Native file picker

Capacitor has `@capacitor/filesystem` and a `Camera` plugin for camera capture. For "import any file from local storage," we use the Android Storage Access Framework via `@capawesome/capacitor-file-picker`.

**Frontend touchpoint:** `frontend/src/features/library/components/ImportDropzone.tsx` currently uses HTML `<input type="file">`. On Android-Capacitor, this triggers a system intent to the file picker, which works. No change needed for v1. A nicer integration with Capacitor's plugin API can land in v2.

**Effort:** zero for v1.

### 4. Calendar coach integration

The Plan view today proposes study blocks against the user's calendar. On macOS this uses the FastAPI backend's calendar import (ICS subscription). On Android, the same ICS import works. For deeper integration with Google Calendar, the user can grant OAuth on the web and the same calendar appears in the mobile app.

**Effort:** zero for v1.

### 5. Push notifications

The Plan view has a "tonight's session" notification need. macOS today uses none. Android via Capacitor uses Firebase Cloud Messaging.

**Action:** add `@capacitor/push-notifications` + a simple FCM project setup. Backend already has the user-identity scaffolding (`db.py`).

**Effort:** one day.

### 6. Backend hosting

The macOS app runs `127.0.0.1:8000` locally. Android cannot do this — the Python backend has to be hosted.

**Action:** add a `backend/Dockerfile` (already exists for the IAF project; pattern is the same) and a Fly.io or Railway deploy. Use the same FastAPI app.

**Effort:** one day. The backend is already designed to run remotely.

**Implication for the local-first claim:** on Android, the data plane is not local-first by default. We have two options:
- **Option A:** drop the local-first marketing claim on Android (honest, but loses a differentiator).
- **Option B:** ship the on-device LLM tier on macOS only as the "Pro Air-Gapped" tier; Android is cloud-tier with same encryption-in-transit + per-user data isolation as any modern SaaS.

We default to **Option B** and message it clearly: macOS is the privacy-maximalist surface; Android brings the same study system to the device most students actually carry.

## Implementation plan

Sequenced for one engineer (the new senior eng hire post-funding) over 6 weeks:

| Week | Deliverable |
|---|---|
| 1 | Capacitor scaffold; backend on Fly.io; `build-android.mjs` working end-to-end; first APK that loads the Library on a Pixel emulator. |
| 2 | All 9 routes verified on Android. Prefix-audit pass on the design system. |
| 3 | Citation-flight animation verified on real low-end Android (Pixel 6a, Samsung A-series). |
| 4 | Native file picker integration (the `<input>` path works; this is the polish pass). Push notifications wired to FCM. |
| 5 | Beta release via Google Play Internal Testing. 20 student testers from the design-partner cohort. |
| 6 | Public beta on Play Store. Same Carrel pricing tier as macOS. |

## What NOT to do

- **Do not spawn a parallel native Android project.** The codebase fork kills velocity for the next two years.
- **Do not delay the macOS shell improvements** to match Android. The macOS app is the prosumer-quality surface. Android trails on polish, leads on distribution.
- **Do not put the local-first LLM in the Android app.** Llama 3.1 8B requires 8-12GB RAM at sane quantization. Most Android phones cannot run it. Cloud-tier on Android is the honest answer.
- **Do not chase iPad or iOS until Android proves out the wrap pattern.** iOS will follow Capacitor in week 7 with maybe one week of additional work.

## Risk

The single biggest risk is that the citation-flight FLIP animation jitters on mid-tier Android. If it does, Carrel's signature moment becomes a stutter, not a wow. Mitigation: a fallback non-FLIP animation that simply highlights the target chunk and scrolls to it without the morph. Less elegant, still functional. The fallback is a 100-line PR if needed.

## Next concrete steps (the moment funding lands)

1. Hire the senior eng with Capacitor experience listed as a plus.
2. Spin up Fly.io with the backend Dockerfile.
3. Capacitor `init` against the existing frontend repo as a new app target.
4. First APK in week 1.

This document was written autonomously based on the existing codebase audit. Verify the Capacitor plugin recommendations against current versions before committing dependencies.
