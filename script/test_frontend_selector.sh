#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SELECTOR_SOURCE="$ROOT_DIR/macos-app/Sources/EinsteinDesktopApp/FrontendSelector.swift"
HARNESS_FILE="$(mktemp "${TMPDIR:-/tmp}/frontend-selector-harness.XXXXXX.swift")"

cleanup() {
  rm -f "$HARNESS_FILE"
}

trap cleanup EXIT

cat >"$HARNESS_FILE" <<'SWIFT'
import Foundation

func require(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fputs("frontend-selector check failed: \(message)\n", stderr)
        exit(1)
    }
}

unsetenv("EINSTEIN_FRONTEND")
require(FrontendSelector.resolved() == .new, "expected default frontend to be .new")

setenv("EINSTEIN_FRONTEND", "legacy", 1)
require(FrontendSelector.resolved() == .legacy, "expected explicit legacy mode to win")

setenv("EINSTEIN_FRONTEND", "NEW", 1)
require(FrontendSelector.resolved() == .new, "expected case-insensitive env parsing")

print("frontend-selector ok")
SWIFT

swift "$SELECTOR_SOURCE" "$HARNESS_FILE" >/dev/null
