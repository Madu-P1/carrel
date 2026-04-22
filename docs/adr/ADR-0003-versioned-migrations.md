# ADR-0003: Versioned Migrations

- Status: Accepted for Phase 1 planning
- Date: 2026-04-20

## Context

The app currently relies on startup-time schema patching plus a shared schema file. That works for early exploration, but it is brittle across user databases and makes reproducibility harder as the schema grows.

## Decision

Phase 1 will adopt versioned SQL migrations backed by a `schema_migrations` table and a small Python migration runner.

## Why Not Alembic

The repo does not use SQLAlchemy ORM as its primary database layer. A small pure-SQL runner fits the existing SQLite architecture better, keeps migrations transparent, and is easier to ship inside the desktop app without introducing a second database abstraction stack.

## Scope

Included:

- `migrations/NNNN_*.sql`
- `schema_migrations` table
- deterministic migration runner

Excluded:

- ORM adoption
- cross-database portability work
- server-grade migration orchestration
