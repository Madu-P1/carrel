# ADR-0002: TypeScript + Preact Frontend

- Status: Accepted for Phase 1 planning
- Date: 2026-04-20

## Context

The macOS bundle currently ships a very large single-file frontend, while the repo also contains a separate browser surface. That split slows iteration, obscures ownership, and makes parity difficult to reason about.

## Decision

Phase 1 will introduce a TypeScript + Vite + Preact frontend that becomes the future single source of truth for UI code.

Once Phase 1 reaches parity:

- the macOS bundled frontend
- any browser/dev surface

will be derived from the same Vite build outputs.

## Interim Rule

`index.html` remains a read-only legacy browser surface until the new frontend reaches parity. It is not being expanded as a second long-term product surface.

## Why This Stack

- TypeScript gives explicit contracts for a growing client surface.
- Preact keeps the bundle light for WKWebView.
- Vite provides fast local iteration and static output suitable for the macOS bundle.

## Rejected Alternatives

- Keep the single-file frontend: rejected because it is already a drag on reliability and velocity.
- Next.js/SSR stack: rejected because the app does not benefit materially from SSR inside WKWebView.
- Full React framework with heavier runtime: rejected because the product needs smaller, simpler desktop packaging.
