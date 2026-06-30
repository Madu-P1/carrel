---
description: Use the extracted Build macOS Apps skill bundle for native macOS Swift, SwiftUI, AppKit, build, test, signing, and telemetry work.
allowed-tools: Read, Edit, Write, Bash, Agent, Skill, TodoWrite, Grep, Glob
---

# /macos-app

Use the extracted Build macOS Apps capability bundle for this request:

`/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps`

Arguments from the operator:

`$ARGUMENTS`

## Mandatory Skill Loading

Before acting, read:

1. `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/PORTING_NOTES.md`
2. The relevant `SKILL.md` files under `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/skills/`
3. Any referenced `references/*.md` files named by those skills

Do not treat this as generic Swift advice. Treat the extracted skill files as
the workflow source of truth.

## Skill Selection Map

Pick the smallest useful set, usually 1-3:

- Build, launch, runtime failures, or Run button setup:
  `skills/build-run-debug/SKILL.md`
- SwiftPM package-first project:
  `skills/swiftpm-macos/SKILL.md`
- SwiftUI scene, window, toolbar, settings, split view, or menu bar UI:
  `skills/swiftui-patterns/SKILL.md`
- Large SwiftUI view cleanup:
  `skills/view-refactor/SKILL.md`
- AppKit bridge, responder chain, panels, pasteboard, drag/drop, or direct window access:
  `skills/appkit-interop/SKILL.md`
- Window chrome, titlebar, toolbar visibility, placement, restoration, or borderless behavior:
  `skills/window-management/SKILL.md`
- macOS Liquid Glass adoption or custom chrome removal:
  `skills/liquid-glass/SKILL.md`
- Unified logging / `OSLog.Logger` instrumentation:
  `skills/telemetry/SKILL.md`
- Test failures:
  `skills/test-triage/SKILL.md`
- Code signing, entitlements, sandbox, hardened runtime, or Gatekeeper:
  `skills/signing-entitlements/SKILL.md`
- Archive, package, export, or notarization readiness:
  `skills/packaging-notarization/SKILL.md`

## Operating Rules

1. Read local project context before editing. For Carrel, start with
   `/Users/madu/Desktop/Codex/CLAUDE.md`, then inspect the relevant files under
   `macos-app/`.
2. Prefer shell-first workflows: `./script/build_and_run.sh`, `xcodebuild`,
   `swift build`, `swift test`, `lldb`, `codesign`, `spctl`, `plutil`, and
   `log stream`.
3. For SwiftPM GUI apps, launch a staged `.app` bundle with `/usr/bin/open -n`;
   do not launch AppKit/SwiftUI GUI binaries as raw executables unless the
   skill explicitly says the product is a CLI.
4. Keep SwiftUI native first. Use AppKit only for the smallest explicit bridge.
5. Preserve project-local privacy and never print secrets, tokens, private
   document content, or user data in logs or final output.
6. Verify with the smallest command that proves the change, then escalate only
   when needed.

## Output Contract

End with:

- Skill files used
- Files changed
- Commands run, with pass/fail status
- Any remaining risk or manual verification need

