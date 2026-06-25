---
description: Inspect macOS signing, entitlement, sandbox, hardened runtime, or Gatekeeper failures using the extracted Build macOS Apps plugin.
allowed-tools: Read, Edit, Write, Bash, Agent, Skill, TodoWrite, Grep, Glob
---

# /fix-codesign-error

Use the extracted Build macOS Apps command and skills:

- `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/commands/fix-codesign-error.md`
- `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/skills/signing-entitlements/SKILL.md`
- `/Users/madu/Desktop/Codex/docs/extracted/build-macos-apps/skills/packaging-notarization/SKILL.md`

Arguments from the operator:

`$ARGUMENTS`

## Workflow

1. Locate the `.app` bundle or binary.
2. Inspect the main binary, `Info.plist`, entitlements, and signature.
3. Use concrete commands where possible:
   - `codesign -dvvv --entitlements :- <path>`
   - `spctl -a -vv <path>`
   - `plutil -p <plist-or-entitlements>`
   - `security find-identity -p codesigning -v`
4. Classify the issue: unsigned/ad hoc, wrong identity, entitlement mismatch,
   sandbox mismatch, hardened runtime issue, nested signing issue, or
   distribution/notarization prerequisite.
5. Provide the minimum repair or validation sequence.

Never invent entitlements. Read them from source or the artifact.

