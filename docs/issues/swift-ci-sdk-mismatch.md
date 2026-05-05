# Swift CI SDK mismatch

## What

Two pre-existing Swift compile errors only fire against GitHub
Actions' `macos-latest` runner, not against local Xcode (newer SDK):

1. **`ContentView.swift:105` — `'glassEffect'` not found**
   `.glassEffect(...)` is a macOS 26 (Tahoe) SwiftUI API. The runner
   currently ships an older SDK that doesn't expose it.

2. **`LocalCalendarBridge.swift:100` — `sending 'self.store' risks causing data races`**
   Swift 6 strict concurrency error. The `EKEventStore` capture in
   `requestFullAccessToEvents { ... }` doesn't satisfy `Sendable`
   under the runner's stricter Swift 6 toolchain.

## Why this happened

`Package.swift` pins `swift-tools-version: 6.0` and
`platforms: [.macOS(.v14)]`, which is honest about the *target*
floor but not about the *SDK floor* used to type-check newer APIs.
Both call sites work locally because Xcode 26's SDK has
`glassEffect` + relaxed `EKEventStore` concurrency.

## Workaround (current)

`.github/workflows/ci.yml::swift-tests` carries `continue-on-error: true`
so a failure surfaces but doesn't block the PR. Tests themselves
still run when the build succeeds; once the SDK floor is reconciled,
remove the flag.

## Fix (real)

Two paths, pick one:

### Option A — gate the macOS-26 features behind `#available` checks

Wrap each `.glassEffect(...)` call in:
```swift
if #available(macOS 26, *) {
    view.glassEffect(...)
} else {
    view  // older fallback
}
```

For the EventKit concurrency error, audit `LocalCalendarBridge.swift`
for capture-of-self in escaping closures and use `[weak self]` /
unstructured Tasks consistently — it's a real Swift 6 issue, not a
false positive.

### Option B — pin the runner image

```yaml
runs-on: macos-15  # or macos-26 once available
```

Cheaper to ship but masks the underlying type-checking debt.

## How to verify the fix

```bash
cd macos-app
xcrun --show-sdk-version  # confirm SDK
swift build               # locally
swift test --parallel
```

Then on the runner:
```yaml
- run: xcrun --show-sdk-version
- run: swift build
```

When both produce the same SDK version (or the code conditionalizes
on availability), remove `continue-on-error: true` from the
swift-tests job and re-test.
