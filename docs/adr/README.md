# ADR Status Lock

These are the provisional Phase 1 architecture decisions already approved in principle, so implementation planning can proceed without reopening them on every PR.

- [ADR-0001](</Users/madu/Desktop/Codex/docs/adr/ADR-0001-swiftpm-ingestion-xpc-service.md>) SwiftPM ingestion as XPC service: **Yes**
  - Scope: XPC boundary, progress, cancellation, and file-access contract.
  - Non-goal: App Store sandbox entitlements, helper signing, and notarization policy are tracked separately.
- [ADR-0002](</Users/madu/Desktop/Codex/docs/adr/ADR-0002-typescript-preact-frontend.md>) TypeScript + Preact frontend: **Yes**
  - Lock: once Phase 1 ships, the macOS bundle and any dev-browser surface are derived from the same Vite build.
  - Interim state: `index.html` remains a read-only legacy browser surface until parity is reached, then it is retired.
- [ADR-0003](</Users/madu/Desktop/Codex/docs/adr/ADR-0003-versioned-migrations.md>) Versioned migrations: **Yes**
  - Rationale: the repo uses raw SQLite and pure SQL migrations today, not SQLAlchemy ORM, so a small hand-rolled runner is the lowest-friction app-shippable choice.
- [ADR-0004](</Users/madu/Desktop/Codex/docs/adr/ADR-0004-hybrid-retrieval-fts5-sqlite-vec.md>) Hybrid retrieval with FTS5 + sqlite-vec: **Yes**
  - Lock: FTS5 lands first, sqlite-vec follows once packaging/loading is validated on the desktop targets.

Follow-up already queued for Phase 1 start:

- Add a `macos-latest` CI matrix when Swift/XPC and sqlite-vec work begins.
