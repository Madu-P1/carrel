# Build macOS Apps Porting Notes

## What Was Extracted

This folder is a direct copy of the installed `Build macOS Apps` plugin cache:

- Source cache: `/Users/madu/.codex/plugins/cache/openai-curated/build-macos-apps/c6ea566d`
- Extracted copy: `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps`

The extracted plugin contains 42 files:

- `.codex-plugin/plugin.json`: plugin manifest and UI metadata.
- `README.md`: high-level overview.
- `agents/openai.yaml`: plugin-level display metadata.
- `commands/*.md`: command-style workflow prompts.
- `skills/*/SKILL.md`: skill instructions Codex loads when a task matches.
- `skills/*/references/*.md`: detailed reference snippets for selected skills.
- `assets/*`: icon/logo assets.

## How It Works

This plugin is skills-first. It does not ship its own MCP server or local tool
binary. The runtime behavior comes from Codex reading the relevant skill
instructions, then using normal workspace tools: shell commands, file edits,
Xcode/SwiftPM commands, `lldb`, `codesign`, `spctl`, `plutil`, and `log stream`.

The activation path is:

1. The plugin manifest points Codex at `./skills/`.
2. Each skill has YAML frontmatter with a `name` and `description`.
3. When a user request matches a skill description, Codex opens that skill's
   `SKILL.md`.
4. If the skill points to `references/`, Codex reads only the relevant reference
   file.
5. Codex then applies the workflow in the current project.

## Skill Map

- `build-run-debug`: discover Xcode/SwiftPM project shape, create
  `script/build_and_run.sh`, wire `.codex/environments/environment.toml`, build,
  run, verify, debug, or stream logs.
- `swiftpm-macos`: use `Package.swift`, `swift build`, `swift run`, and
  `swift test` for package-first macOS projects.
- `swiftui-patterns`: design native macOS SwiftUI scenes, windows, commands,
  toolbars, settings, split views, menu bar extras, and state ownership.
- `view-refactor`: split large SwiftUI files into explicit app/view/model/store/
  service/support structure and tighten state boundaries.
- `appkit-interop`: use narrow AppKit bridges when SwiftUI cannot express a
  desktop behavior cleanly.
- `window-management`: tune macOS window chrome, title/toolbar behavior,
  materials, placement, restoration, and launch behavior.
- `liquid-glass`: adopt modern macOS SwiftUI Liquid Glass patterns and remove
  conflicting custom chrome.
- `telemetry`: add and verify lightweight `OSLog.Logger` instrumentation.
- `test-triage`: run focused macOS tests and classify failures.
- `signing-entitlements`: inspect code signing, entitlements, sandboxing,
  hardened runtime, and Gatekeeper issues.
- `packaging-notarization`: validate distribution artifacts and notarization
  readiness.

## Commands

The `commands/` files are reusable workflow entrypoints:

- `/build-and-run-macos-app`: setup and use the project-local build/run script.
- `/fix-codesign-error`: inspect signing and entitlement failures.
- `/test-macos-app`: run and classify the smallest meaningful test scope.

They are not executable shell scripts. They are command prompt definitions for
Codex-style workflows.

## What Codex Actually Does With It

For macOS app work, I typically:

1. Inspect project shape: `.xcworkspace`, `.xcodeproj`, `Package.swift`, schemes,
   executable products, app names, and existing scripts.
2. Prefer a project-local `script/build_and_run.sh` as the repeatable entrypoint.
3. Keep SwiftPM GUI apps launching as `.app` bundles via `/usr/bin/open -n`,
   rather than raw executable launches.
4. Use SwiftUI-native scene/window APIs first.
5. Use AppKit only for a narrow bridge: `NSViewRepresentable`,
   `NSViewControllerRepresentable`, responder chain, panels, or direct window
   behavior.
6. Verify with build/run/test/log commands appropriate to the current project.
7. Summarize failures as compiler, linker, signing, test assertion, runtime
   launch, or environment/setup issues.

## Porting Checklist

To port this into another Codex plugin-style environment:

1. Preserve `.codex-plugin/plugin.json`.
2. Keep `skills/` at the path referenced by the manifest.
3. Keep each `SKILL.md` frontmatter block intact.
4. Preserve referenced files under `references/` because several skills point to
   them by relative path.
5. Copy `commands/` only if the target environment supports command prompt
   definitions.
6. Copy `agents/openai.yaml` and `assets/` only if the target environment uses
   plugin UI metadata.
7. Do not expect an MCP server. The plugin depends on the host agent's normal
   ability to read files, edit files, and run shell commands.

## Claude Integration In This Repo

This repo wires the extracted bundle into Claude through:

- `/Users/madu/Desktop/Codex/CLAUDE.md`
- `/Users/madu/Desktop/Codex/.claude/commands/macos-app.md`
- `/Users/madu/Desktop/Codex/.claude/commands/build-and-run-macos-app.md`
- `/Users/madu/Desktop/Codex/.claude/commands/test-macos-app.md`
- `/Users/madu/Desktop/Codex/.claude/commands/fix-codesign-error.md`

Claude should invoke `/macos-app` for general native macOS work and the focused
commands for build/run, test triage, and signing failures. The commands instruct
Claude to load `PORTING_NOTES.md`, the relevant `SKILL.md`, and any referenced
files before editing or running commands.

## Important Dependency Assumptions

The workflows assume a macOS host with some combination of:

- Xcode command line tools
- `xcodebuild`
- SwiftPM / `swift`
- `lldb`
- `/usr/bin/open`
- `codesign`
- `spctl`
- `plutil`
- `log stream`

For non-macOS hosts, most build/run/debug/signing workflows become reference
guidance rather than directly executable automation.
