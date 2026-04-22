# ADR-0004: Hybrid Retrieval With FTS5 + sqlite-vec

- Status: Accepted for Phase 1 planning
- Date: 2026-04-20

## Context

Document-grounded study features need stronger retrieval than simple chunk scans. The repo already uses SQLite locally, so retrieval should build on that local-first foundation instead of introducing a separate service too early.

## Decision

Phase 1 retrieval work will follow a staged hybrid plan:

1. land FTS5-backed lexical retrieval first
2. add sqlite-vec once extension packaging and loading are validated on desktop targets
3. layer reranking and metadata-aware selection on top of those primitives

## Why This Path

- SQLite remains the right default for a local-first desktop product.
- FTS5 is built-in, practical, and low-risk.
- sqlite-vec keeps vector search close to the existing data model instead of introducing a separate vector database prematurely.

## Non-Goals

- large-scale distributed retrieval
- remote search infrastructure
- mandatory vector-only retrieval
