# ADR 0002 — Cloze deletion cards: `kind` column on `srs_cards`

Status: ACCEPTED (synthesizer verdict, Carrel autonomous build, 2026-05-13)
Scope: PR 5.1 of `docs/plans/flashcards-focus-2026-05-09.md`
Migration: `migrations/0017_srs_cards_kind.sql`

## Context

PR 5 of the flashcards-focus campaign adds two new card types to the SRS surface:
cloze deletion and reverse cards. Both require a schema discriminator on
`srs_cards`. The plan groups them under one section but states "each
independently shippable." The Carrel autonomous routine's audit trigger fires
on any new migration, so this decision was litigated via the proponent/adversary
synthesizer pattern before any code lands.

## Decision

Ship cloze cards as PR 5.1, split from reverse cards (PR 5.2). The schema
change is a single column on `srs_cards`:

```sql
ALTER TABLE srs_cards
ADD COLUMN kind TEXT NOT NULL DEFAULT 'qa' CHECK(kind IN ('qa', 'cloze'));
```

Two mandatory scope additions, surfaced by the adversary leg and folded in by
the synthesizer:

1. **FTS / search projection must strip cloze markers.** `services/study.py::list_cards`
   currently runs `LOWER(s.front) LIKE ?` against raw card text. A cloze front
   like `"The mitochondrion is the {{c1::powerhouse}} of the cell"` would
   otherwise pollute search results (literal `"c1"` matches the marker token,
   and `"powerhouse"` matches despite being hidden on the front face).
   Implementation: strip `{{cN::...}}` markers from the search projection before
   the LIKE comparison.

2. **Concept-name rewriting must skip cloze marker spans.**
   `services/study.py::_normalize_card_text` does `value.replace(raw_name, cleaned)`
   over front/back. A concept literally named `"c1"` (financial coupon labels,
   chemistry compound identifiers, etc.) would corrupt cloze markers via this
   replace. Implementation: detect `{{cN::...}}` spans and exclude them from
   the rewrite.

## Alternatives considered

### A. Polymorphic JSON column (`card_payload JSONB`) — REJECTED

Defeats the CHECK + index discipline used elsewhere in the schema. Forces every
read site to JSON-probe. No precedent in this codebase.

### B. Separate `srs_cloze_cards` table — REJECTED

All FSRS state (stability, difficulty, reps, lapses, due_date), the
`idx_srs_cards_due_state` index, joins to `concepts`/`documents`, the
`fetch_due_cards` query, and the `list_cards` query are shared between qa and
cloze. A separate table forces UNION ALL on every scheduler query and
duplicates FSRS columns. Cost outweighs the encapsulation benefit at MVP scale.

### C. Parent `srs_card_notes` table with N-occlusion siblings — REJECTED for PR 5.1

The adversary's strongest argument: mature cloze implementations (Anki) model
N occlusion regions per note that schedule independently. A row-per-card
model with a single `kind` field cannot scale to multi-occlusion without a
schema rewrite later.

Counter, and reason for rejection at MVP: Carrel is pre-launch with zero
users. The plan explicitly scopes single-occlusion cloze
(`{{c1::term}}`, no multi-segment, no multi-region). Building the parent
table now is over-engineering against zero demand. The data lives in one
app's local SQLite, so a future migration to introduce the parent table is
reversible. **Trigger to revisit:** when a user requests multi-occlusion, or
before PR 5.2 ships if reverse-card semantics force a table-rebuild migration
anyway (then bundle the parent-table refactor into that rebuild to amortize
cost).

### D. Repurpose existing `card_type` column instead of new `kind` — REJECTED for PR 5.1

`srs_cards.card_type` exists at `migrations/0001_initial.sql:84` as a free-text
column with values like `"custom"`, `"anchor"`, `"ai-draft"` — descriptive
provenance, not a behavioral discriminator. Tightening it with a CHECK would
either (a) require a destructive migration risking existing rows or
(b) overload one column with provenance and rendering, two orthogonal concerns.

A separate `kind` column keeps both axes typed. **The `card_type` rename /
reconciliation is acknowledged as a separate cleanup PR**, not a blocker for
PR 5.1.

### E. Bundle PR 5.1 + PR 5.2 (cloze + reverse) into one PR — REJECTED

The adversary argued bundling amortizes the CHECK-constraint rebuild
(SQLite cannot ALTER ... DROP CONSTRAINT; widening the enum from
`('qa','cloze')` to `('qa','cloze','reverse')` requires a full table rebuild).

Counter, and reason for rejection: the rebuild is hours of work in a local
SQLite, not days. Bundling means a bug in reverse-card pair semantics blocks
cloze from shipping. The asymmetry favors the split: 5.1 lands green; 5.2
follows behind a table-rebuild migration that can amortize the parent-table
refactor (Alternative C) if that becomes warranted. CLAUDE.md explicitly
states: "Test-gated, additive PRs. Every PR ships small, independently
shippable. Multi-day features land as 3-5 sub-PRs."

## Consequences

### Positive

- Single-column migration, metadata-only on SQLite (no row rewrite, no
  schema_migrations contention against active users).
- All scheduler queries continue to work unchanged.
- `kind` discriminator is typed + indexed-friendly, mirrors the validated
  precedent from `migrations/0014_calendar_local_feed_kind.sql`.
- The 0014 migration itself is the working template (defaulted, CHECK-narrow,
  no backfill).

### Negative / accepted debts

- `card_type` and `kind` are two type-shaped columns on the same table.
  Acknowledged debt; cleanup PR slated separately.
- PR 5.2 (reverse cards) will need an enum widening migration that rebuilds
  the table. Acceptable cost — bundle it with any parent-table refactor that
  multi-cloze demand surfaces.
- Single-occlusion cloze ships first; multi-occlusion is a follow-up that
  requires a parent-notes refactor.
- The `kind` CHECK is brittle to widen. Mitigation: include a comment in the
  migration documenting the planned `'reverse'` value so future widening is
  predictable.

## Implementation notes (scope of PR 5.1)

1. **Migration `0017_srs_cards_kind.sql`** wrapped in `BEGIN TRANSACTION; ... COMMIT;`.
   Adds the column; updates `tests/test_db_migrations.py` to assert existing
   rows read `kind='qa'`.

2. **Backend** (`api_models.py`, `services/study.py`):
   - Extend `CardCreateRequest` with `kind: Literal["qa","cloze"] = "qa"` and
     `cloze_text: Optional[str]`.
   - `services/study.py::create_card` validates `kind="cloze"` requires at
     least one `{{c1::...}}` marker.
   - SELECT lists in `fetch_due_cards` and `list_cards` include `kind`.
   - **Scope addition (FTS strip):** `list_cards` search projection strips
     `{{cN::...}}` markers before `LOWER LIKE`.
   - **Scope addition (rewrite exclusion):** `_normalize_card_text` skips
     cloze marker spans.

3. **Frontend**:
   - `renderClozeBody(card, face)` helper used at the two card-render sites.
   - Front face: cloze span is hidden (visual placeholder, e.g. `_____`).
   - Back face: cloze span rendered in accent color; existing PR 4
     `SourceCitation` footer preserved.
   - `CardCreateDialog.tsx` and `CardAiDraftDialog.tsx` gain a RadioGroup
     above the front textarea: `qa` (default) | `cloze`.

4. **Tests**:
   - Backend: kind validation (cloze requires marker; qa unchanged); search
     projection strips markers; concept-name rewrite preserves markers when
     a concept is literally named `"c1"`.
   - Frontend: cloze rendering on front (hidden) and back (revealed); creation
     dialog kind toggle round-trips through the API.
   - Migration: existing rows default to `kind='qa'`.

## Deferred follow-ups (not part of PR 5.1)

- `card_type` rename / consolidation with `kind`.
- `srs_card_notes` parent table for multi-occlusion cloze.
- FSRS interleave-ban for sibling cloze cards (only matters once siblings
  exist).
- ADR for offset-span syntax vs `{{cN::...}}` inline markers — only matters
  if multi-occlusion ships.

## Transcripts

### Proponent

> The schema shape is already validated. Migration
> `0014_calendar_local_feed_kind.sql:19-20` is the exact template
> (`ALTER TABLE calendar_feeds ADD COLUMN kind TEXT NOT NULL DEFAULT 'url'
> CHECK (kind IN ('url', 'local'))`). Shipped, no backfill needed.
>
> A column (not polymorphic JSON, not a separate table) keeps cloze on the
> existing hot path with zero query rewrites. Splitting cloze from reverse
> honors CLAUDE.md's "test-gated, additive PRs" convention. The migration is
> safe by construction (metadata-only on SQLite, no FTS5 trigger on
> srs_cards). FlashcardFace already accepts `body: ComponentChildren`, so
> cloze rendering is a body-prop change, not a component rewrite.
>
> Strongest concession: `card_type` already exists on srs_cards. Rationale to
> keep both: `card_type` is descriptive provenance, `kind` would be
> behavior — different axes.

### Adversary

> The schema shape is semantically wrong. Cloze in mature implementations is
> N-occlusion-per-note generating N sibling cards. A single-row model loses
> per-region scheduling or smuggles multi-card semantics into kind strings.
>
> `card_type` column already exists — adding `kind` alongside creates dual
> discriminators with no reconciliation.
>
> CHECK constraint is a foot-gun. SQLite cannot DROP/MODIFY CHECK. PR 5.2
> requires a table rebuild. Bundling 5.1+5.2 amortizes.
>
> FTS5/search story unaddressed. `LOWER(s.front) LIKE ?` against
> `"the {{c1::powerhouse}} of the cell"` pollutes search for both `"c1"` and
> `"powerhouse"`.
>
> Citation moat narrows. PR 4 just shipped citation on back face; cloze back
> is the same text as front with occlusion revealed — no separate answer
> surface to attach SourceCitation to.
>
> FSRS interleave problem: sibling cloze cards from one note should be
> interleave-banned. Punted.
>
> `{{c1::term}}` syntax conflicts with `_normalize_card_text` naive rewrite —
> a concept named "c1" corrupts cloze markers.
>
> Recommendation: defer PR 5.1, or bundle as one PR 5 with
> `srs_card_notes` parent table + offset-span syntax.
>
> Severity: MAJOR.

### Synthesizer verdict

> WINNER: PROPONENT — Ship PR 5.1 cloze with mandatory FTS-strip and
> name-rewrite-exclusion scope additions.
>
> Granted from Adversary, non-decisive: dual discriminators (defer cleanup),
> single-occlusion FSRS interleave (not a problem at single-occlusion),
> citation moat (cloze can carry SourceCitation footer).
>
> Granted from Adversary, mandatory in PR 5.1: FTS marker-strip;
> `_normalize_card_text` marker-span exclusion.
>
> Rejected from Adversary, decisive: parent table now is overbuild for zero
> users; CHECK rebuild is hours, not days; bundling risks a 5.2 bug
> blocking 5.1.
>
> Confidence: HIGH. The proponent's precedent (0014) is concrete and recent;
> the adversary's strategic claims (PR 6, moat) are stale or rhetorical; the
> two concrete bugs (FTS noise + name rewrite collision) are cheaply fixed
> in-scope.
