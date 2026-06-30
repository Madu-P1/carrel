---
description: Set up or use the project-local macOS build/run/debug workflow from the extracted Build macOS Apps plugin.
allowed-tools: Read, Edit, Write, Bash, Agent, Skill, TodoWrite, Grep, Glob
---

# /build-and-run-macos-app

Use the extracted Build macOS Apps command and skill:

- `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/commands/build-and-run-macos-app.md`
- `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/skills/build-run-debug/SKILL.md`
- `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/skills/build-run-debug/references/run-button-bootstrap.md`

Arguments from the operator:

`$ARGUMENTS`

## Workflow

1. Discover whether the repo uses `.xcworkspace`, `.xcodeproj`, or
   `Package.swift`.
2. Identify the scheme/product and the process/app name.
3. If no project-local run script exists, create or update
   `script/build_and_run.sh` using the canonical bootstrap reference.
4. If `.codex/environments/environment.toml` is needed, wire its `Run` action to
   `./script/build_and_run.sh`.
5. Run the script in the requested mode: `run`, `debug`, `logs`, `telemetry`, or
   `verify`.
6. Classify failures as compiler, linker, signing, build settings, missing
   toolchain, script bug, or runtime launch.

For Carrel, prefer the existing `/Users/madu/Desktop/Codex/script/build_and_run.sh`
unless the operator explicitly asks to replace it.

