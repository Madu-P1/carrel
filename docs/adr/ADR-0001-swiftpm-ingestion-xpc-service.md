# ADR-0001: SwiftPM Ingestion As XPC Service

- Status: Accepted for Phase 1 planning
- Date: 2026-04-20

## Context

The current macOS ingestion helper is a standalone SwiftPM binary launched per request. That keeps the implementation simple, but it adds repeated process startup cost, makes cancellation awkward, and leaves progress reporting shallow. Phase 1 needs a durable boundary for native file access, PDFKit/Vision OCR, and desktop-grade ingestion telemetry without rewriting the rest of the app.

## Decision

Phase 1 will move native ingestion work behind a SwiftPM-based XPC service boundary.

The service contract will cover:

- ingestion request/response types
- progress reporting
- cancellation
- parser mode metadata
- file-access handoff rules

## Why Not Something Else

- Keep subprocess binary forever: rejected because process spin-up and weak cancellation become a product tax.
- Full helper-app rewrite first: rejected because it is too large for the Phase 1 scope.
- Move ingestion fully into Python: rejected because the repo already benefits from Apple-native PDFKit and Vision integration.

## Scope

Included in this ADR:

- XPC boundary definition
- progress and cancellation plumbing
- native ingestion service ownership
- file-access contract between shell and backend

Non-goals:

- App Store sandbox entitlements
- helper signing policy
- notarization and distribution policy

Those packaging concerns are tracked separately.
