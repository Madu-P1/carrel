# Audio transcription — implementation plan

> Discovered during the universal-ingest verification pass (2026-05-07): audio uploads cannot be transcribed by the current CLI ingestion bridge. This document captures why, and the smallest path to ship real audio support.

## What was tried (and why it doesn't work)

Initial approach: extend `macos-app/Sources/EinsteinIngestionBridge/main.swift` with `SFSpeechRecognizer` calls, request authorization at first invocation, run on-device recognition, return the transcript through the same JSON envelope used for image OCR.

Result: the bridge process is killed with SIGABRT (exit 134) on every audio invocation. Root cause: SFSpeechRecognizer requires:

1. An `Info.plist` with `NSSpeechRecognitionUsageDescription` declared. CLI executables do not have one, so the TCC subsystem aborts the process before any code runs.
2. A user-facing app-bundle context for the system permission prompt. CLI tools cannot surface the prompt; status stays `.notDetermined` indefinitely even with `requestAuthorization(_:)`.
3. On-device speech assets installed for the user's locale.

Constraint 1 alone is fatal for the standalone bridge. The Swift code added in 2026-05-07 was reverted; the `parse_audio` Python parser stays a stub for now and the upload allowlist excludes audio suffixes.

## The correct path

Move audio transcription into the main `EinsteinDesktopApp` (which already has an Info.plist) and expose it to the Python backend via a small in-process HTTP endpoint that the bridge hits when run.

### Step 1 — bundle declares the privacy key

Add to `macos-app/Sources/EinsteinDesktopApp/Info.plist` (or wherever the app's Info.plist lives — the project may need to add one if absent):

```xml
<key>NSSpeechRecognitionUsageDescription</key>
<string>Carrel transcribes lecture recordings and voice notes on-device so you can search, ask questions, and review them like any other source. Audio never leaves your laptop.</string>
```

### Step 2 — the app exposes a local transcription endpoint

The macOS app already runs the Python backend on `127.0.0.1:8000`. Add a Swift-side HTTP server (or an XPC service) on a separate port that exposes `POST /transcribe` accepting an audio file path and returning JSON identical to the existing bridge envelope.

Alternative: the app posts the path to the Python backend's `/api/internal/transcribe` endpoint, which is a thin shim that calls into a Swift helper via something like `pyobjc` or a launched-but-trusted Apple-bundle subprocess.

### Step 3 — request authorization at first launch

In the app's `applicationDidFinishLaunching`, call `SFSpeechRecognizer.requestAuthorization`. Persist the result. The system prompt fires once, the user grants, all future transcription runs work.

### Step 4 — the parser calls the in-app endpoint

Replace the current `NativeBridge.run(path)` call in `parse_audio` with an HTTP POST to the app's transcription endpoint. Same JSON envelope; minimal changes downstream.

### Step 5 — on-device asset check

Before transcription, check `recognizer.supportsOnDeviceRecognition`. If false, surface a clear error directing the user to System Settings > General > Language & Region (where on-device speech assets are downloaded automatically when a language is configured).

## Estimated effort

About 1–2 days of focused Swift + Python work. Tests are straightforward (mock the bridge endpoint; validate the parser path with a known-text WAV).

## Why this isn't being done in the current autonomous run

The autonomous loop's risk constraints exclude broad architectural changes. Adding an in-app HTTP server, an Info.plist, and a TCC-prompt flow touches enough surfaces that a sleeping founder cannot triage if something goes sideways. Better to land it in a dedicated focused session.

## What ships in the meantime

The Library upload UI accepts the same 50+ document, image, and code formats. Audio + video are excluded from the allowlist with a clear message. Students who need to transcribe lectures right now can use the Mac's built-in Voice Memos app's transcript feature, then upload the resulting text file.
