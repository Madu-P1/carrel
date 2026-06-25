---
description: Run and triage macOS SwiftPM or Xcode tests using the extracted Build macOS Apps plugin.
allowed-tools: Read, Edit, Write, Bash, Agent, Skill, TodoWrite, Grep, Glob
---

# /test-macos-app

Use the extracted Build macOS Apps command and skill:

- `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/commands/test-macos-app.md`
- `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/skills/test-triage/SKILL.md`

Arguments from the operator:

`$ARGUMENTS`

## Workflow

1. Detect the harness: `xcodebuild test` or `swift test`.
2. Prefer the smallest meaningful scope. Use target, product, scheme, or filter
   arguments if supplied.
3. Classify failures as build failure, assertion failure, crash/signal,
   async/timing flake, environment/fixture issue, missing entitlement, or host
   app setup issue.
4. Rerun focused tests only when new information will be gained.
5. Report the command used, smallest failing scope, top failure category,
   likely cause, and next fix or rerun step.

For Carrel's native shell, the narrow default is:

`swift test --package-path /Users/madu/Desktop/Codex/macos-app`

