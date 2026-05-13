# ADR 0003 — Reverse cards: drop CHECK, add `card_pairs` join table, dedicated `/pair` endpoint

Status: ACCEPTED (synthesizer verdict, Carrel autonomous build, 2026-05-13)
Scope: PR 5.2 of `docs/plans/flashcards-focus-2026-05-09.md`
Migration: `migrations/0018_*.sql` (drop kind CHECK + add card_pairs)
Builds on: [ADR 0002](./0002-pr-5-1-cloze-cards-schema.md)

## Context

The flashcards-focus campaign has one remaining sub-PR: reverse cards. The
plan PR 5 item #2 calls for "for any AI-drafted Q/A card with a single-term
answer, auto-generate the reverse direction" with a `paired_card_id` link.
ADR 0002 anticipated this moment and conditionally allowed bundling a
parent-table refactor "if reverse-card semantics force a table-rebuild
migration anyway."

The Carrel autonomous routine ran a full proponent/adversary/synthesizer
round before any code lands. The adversary leg surfaced two load-bearing
concerns the original plan did not address:

1. **SQLite `PRAGMA foreign_keys` toggling is a no-op within a transaction.**
   The proponent's CHECK-widening table-rebuild needs `PRAGMA foreign_keys=OFF`
   for safety. Carrel's migration runner uses `conn.executescript()` per
   migration (each migration file is its own implicit transaction boundary;
   see `db.py::apply_migrations`). The PRAGMA can be set in the migration
   file BEFORE its `BEGIN TRANSACTION`, but the bookkeeping is fragile and
   easy to break in any follow-up rebuild migration.

2. **Every new card kind would force another table rebuild.** The kind CHECK
   added in PR 5.1 (`kind IN ('qa','cloze')`) is closed; widening it to
   include `'reverse'` requires a full table rebuild because SQLite cannot
   ALTER ... DROP/MODIFY CHECK. Anki has ~10 card kinds. If Carrel follows a
   similar trajectory (image occlusion, audio, type-in, etc.), the CHECK
   signs us up for ~10 rebuilds — one per card-kind addition.

The synthesizer ruled ADVERSARY_WINS on the schema mechanics and the pair-
link integrity questions, granting the proponent only the auto-reverse UX
intent (which the synthesizer reversed anyway for composability with the
junction-table choice).

## Decision

Three coupled choices, all decided in favor of the adversary's alternative:

### 1. Drop the `kind` CHECK; validate in application code

Migration `0018_srs_cards_kind_drop_check.sql` removes the CHECK constraint
from `srs_cards.kind`. Since SQLite cannot `ALTER ... DROP CONSTRAINT`, the
migration uses the canonical 12-step rebuild pattern ONCE, with explicit
`PRAGMA foreign_keys=OFF` placed BEFORE the BEGIN/COMMIT in the migration
file (taking advantage of `conn.executescript()`'s implicit pre-commit).

The validation moves entirely to `services/study.py::create_card`, which
already had a defense-in-depth allowlist:

```python
if kind not in ("qa", "cloze"):
    raise ValueError(f"kind must be 'qa' or 'cloze', got {kind!r}")
```

PR 5.2 widens this allowlist to include `"reverse"`. Future card kinds
add a value to this Python list — no more SQL migrations to widen an enum.

The Pydantic `Literal["qa","cloze","reverse"]` on `CardCreateRequest` remains
the route-layer guard. The validation surface goes: Pydantic → service-layer
allowlist. Both are typed; neither is in the database.

### 2. `card_pairs` join table — NOT `paired_card_id` self-FK

Migration `0018` (same file or a follow-up `0019`) adds:

```sql
CREATE TABLE card_pairs (
    card_a_id TEXT NOT NULL,
    card_b_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (card_a_id, card_b_id),
    CHECK (card_a_id < card_b_id),
    FOREIGN KEY (card_a_id) REFERENCES srs_cards(id) ON DELETE CASCADE,
    FOREIGN KEY (card_b_id) REFERENCES srs_cards(id) ON DELETE CASCADE
);
CREATE INDEX idx_card_pairs_b ON card_pairs(card_b_id);
```

The `CHECK (card_a_id < card_b_id)` constraint guarantees:
- No duplicate pairs (PRIMARY KEY plus ordering means (A,B) and (B,A) reduce to one row).
- No self-pairs (a row of (A,A) violates the strict ordering).
- No asymmetric pair (the pair is one row, not two).
- No chains (a card can be paired with one other card via one row).

`ON DELETE CASCADE` from both sides means deleting either card of the pair
removes the pair row (the surviving card stays alive; its pair relationship
is just gone). This is correct — a half-orphaned reverse card has no useful
semantic.

### 3. Dedicated `POST /api/srs/cards/pair` endpoint

Add a new route handler that accepts `{front, back, concept_id?, card_type?}`,
creates the qa card AND the reverse card (with front/back swapped) AND the
`card_pairs` row in one transaction, and returns `{primary_id, reverse_id}`.

Leave `POST /api/srs/cards` (singular) untouched. This preserves the existing
contract that `types.gen.ts` already encodes for every caller, avoids the
"polymorphic response based on flag" wart the adversary flagged, and
composes cleanly with the junction-table choice (one endpoint per row count).

Frontend `CardCreateDialog` adds a "Reverse pair" radio option alongside Q&A
and Cloze. Selecting it routes the submit to `study.createCardPair()` instead
of `study.createCard()`. The dialog title and Submit button text adapt.

## Alternatives rejected

### A. Proponent's plan: widen the CHECK via table-rebuild + self-FK + auto_reverse flag

Rejected for three reasons:
1. PRAGMA mechanics are workable but fragile. Each future card-kind addition
   forces another rebuild. The CHECK earns its cost only once and pays it
   ~10 times over the product's life.
2. `paired_card_id` self-FK admits four invalid states the schema cannot
   reject (asymmetric, chain, self-loop, three+ cards chaining).
3. `auto_reverse` boolean polymorphs the existing endpoint's response shape
   (sometimes one card, sometimes two), breaking the typed contract.

### B. Skip the CHECK-dropping rebuild; document the stale CHECK as debt

Considered. The CHECK would remain `IN ('qa','cloze')` indefinitely, with
the Python validator accepting `'reverse'`. The DB-layer constraint becomes
stale (reverse cards would technically violate the column constraint).

Rejected because: SQLite does enforce CHECK constraints; INSERTing a row
with `kind='reverse'` would fail at the DB. The stale CHECK isn't just
"documented debt", it's a functional blocker. We have to drop it.

### C. Bundle the `srs_card_notes` parent-table refactor

ADR 0002's conditional ("if reverse-card semantics force a rebuild anyway,
bundle the parent-table refactor") triggers in this PR. The synthesizer
considered and rejected this bundling because:

- The strategic case for `srs_card_notes` rests on multi-occlusion cloze
  demand, which still doesn't exist.
- The migration in PR 5.2 already rebuilds `srs_cards` once for the CHECK
  drop. Bundling `srs_card_notes` would also refactor every read site
  (`fetch_due_cards`, `list_cards`, `create_card`) to JOIN through the
  parent — significant blast radius.
- The marginal cost of a future `srs_card_notes` migration is hours, not
  days. Pay it when the actual feature constraint (multi-occlusion cloze
  or image occlusion) is visible.

### D. The proponent's `auto_reverse` UX

The proponent argued `auto_reverse=True` on the existing endpoint matches
authoring intent. The synthesizer granted the intent argument but kept the
adversary's dedicated `/pair` endpoint because (a) endpoint shape is the
most reversible of the three choices, (b) the dedicated endpoint composes
with the junction-table choice (one endpoint per row count), (c) it does
not break the typed singular contract.

The "authoring intent" remains expressible: the frontend dialog toggles
between qa, cloze, and reverse-pair. Routing to a different endpoint
based on the toggle is a one-line client-side branch, not a UX regression.

## Consequences

### Positive

- Future card kinds add to a Python allowlist, never to a SQL migration.
- `card_pairs` schema admits zero invalid states.
- API contract stays singular-and-plural without polymorphism.
- Existing PR 5.1 reads (`fetch_due_cards`, `list_cards`) remain unchanged.
- `card_pairs` is additive; no FK rewires to anchors, reviewlog, or
  planning.

### Negative / accepted debts

- **PR 5.1's CHECK constraint gets dropped one PR after it shipped.** This
  is the operator-visible reversal. The rationale is documented above:
  CHECKs on expanding enums are brittle; the type safety lived in the
  Pydantic + service layers anyway. Net loss is small.
- **One table-rebuild migration in 0018.** Future kind-additions skip this;
  this is the one-time pay-off for moving validation to app code.
- **`card_pairs` is a 1:1-only pair structure today.** If a future feature
  needs N-way card groupings (e.g., a flashcard "deck" of related cards),
  this table is the wrong shape and we'd add a new structure. Acceptable —
  no current demand for N-way.

## Implementation notes (scope of PR 5.2)

1. **Migration `0018_*.sql`** — drop `kind` CHECK via 12-step rebuild
   pattern. Add `card_pairs` table + index. Use this template:

   ```sql
   -- 0018_srs_cards_kind_drop_check_and_card_pairs.sql
   PRAGMA foreign_keys = OFF;
   BEGIN TRANSACTION;

   CREATE TABLE srs_cards_new (
       -- exact column set from migrations/0001_initial.sql:81-99 + kind from 0017
       -- NO CHECK on kind; validation lives in services/study.py
       ...
   );
   INSERT INTO srs_cards_new SELECT
       id, concept_id, card_type, front, back, state, stability, difficulty,
       elapsed_days, scheduled_days, reps, lapses, due_date, last_review, kind
   FROM srs_cards;
   DROP TABLE srs_cards;
   ALTER TABLE srs_cards_new RENAME TO srs_cards;

   CREATE INDEX idx_srs_cards_due_state ON srs_cards (due_date, state);

   CREATE TABLE card_pairs (
       card_a_id TEXT NOT NULL,
       card_b_id TEXT NOT NULL,
       created_at TEXT NOT NULL DEFAULT (datetime('now')),
       PRIMARY KEY (card_a_id, card_b_id),
       CHECK (card_a_id < card_b_id),
       FOREIGN KEY (card_a_id) REFERENCES srs_cards(id) ON DELETE CASCADE,
       FOREIGN KEY (card_b_id) REFERENCES srs_cards(id) ON DELETE CASCADE
   );
   CREATE INDEX idx_card_pairs_b ON card_pairs(card_b_id);

   COMMIT;
   PRAGMA foreign_keys = ON;
   ```

   Note: the PRAGMA lines sit OUTSIDE the BEGIN/COMMIT block, taking
   advantage of `conn.executescript()`'s implicit pre-commit. Verified
   against `db.py::apply_migrations` (line ~370): each migration is its own
   executescript call.

2. **Backend** (`services/study.py`, `routes/study.py`, `api_models.py`):
   - Widen `kind` allowlist in `create_card` to include `"reverse"`.
   - Add `create_card_pair(conn, *, front, back, concept_id, card_type)`
     helper that opens a savepoint, inserts the qa row, inserts the
     reverse row with front/back swapped and `kind="reverse"`, inserts
     the `card_pairs` row with the lower id as `card_a_id`, commits.
   - Add Pydantic model `CardPairCreateRequest` (front, back, optional
     concept_id + card_type).
   - Add response model `CardPairCreateResponse` returning
     `{primary_id: str, reverse_id: str}`.
   - Add route `POST /api/srs/cards/pair` that calls `create_card_pair`.

3. **Frontend** (`endpoints.ts`, `CardCreateDialog.tsx`, tests):
   - Add `study.createCardPair({front, back})` returning `{primary_id, reverse_id}`.
   - Extend `CardCreateDialog` kind picker from 2 to 3 options
     (Q&A, Cloze, Reverse pair). Reverse-pair mode routes submit to
     `createCardPair`; the back textarea label becomes "Reverse answer".
   - Regenerate types.gen.ts.

4. **Tests**:
   - Backend migration: existing rows preserved across the rebuild;
     FK references survive; `idx_srs_cards_due_state` survives;
     `card_pairs` rejects (A,A), accepts (A,B), rejects (B,A) where A<B.
   - Backend service: `create_card_pair` produces two rows + one pair row
     in one transaction; rollback works.
   - Backend route: POST /api/srs/cards/pair returns both ids; the pair
     is readable via list_cards (both rows appear).
   - Frontend: dialog kind picker has three options; selecting Reverse
     pair routes to `study.createCardPair`; the response shape is
     handled.

## Deferred follow-ups

- `card_type` rename / consolidation with `kind` (still deferred from ADR 0002).
- `srs_card_notes` parent table — defer again unless multi-occlusion
  cloze or image-occlusion demand surfaces.
- "Single-term answer" auto-detection for AI-drafted reverse pairs — the
  plan's original scope. Defer until the manual-create path is shipped and
  used; the heuristic is a separate UX question.
- FSRS scheduling implications of paired cards. The two cards schedule
  independently (each is its own srs_cards row with its own FSRS state).
  Acceptable — you may know the term but not the inverse. Document.

## Transcripts

### Proponent (summary)

> Focused table-rebuild widening the CHECK to ('qa','cloze','reverse').
> Add paired_card_id self-FK. auto_reverse flag on POST /api/srs/cards.
> Defer srs_card_notes parent-table refactor again. Reverse cards render
> through the same StudyView path as qa.

### Adversary (summary)

> Table-rebuild is fragile and signs us up for ~10 future rebuilds.
> Drop the CHECK; validate in Python. paired_card_id self-FK admits four
> invalid states. Use a card_pairs(card_a, card_b) junction table with
> CHECK (card_a < card_b) + ON DELETE CASCADE. auto_reverse polymorphs the
> API; use a dedicated POST /api/srs/cards/pair endpoint instead.
> Severity: MAJOR.

### Synthesizer verdict

> ADVERSARY_WINS. The PRAGMA-in-transaction claim is technically workable
> but fragile; future kind-additions multiply the risk. The four invalid
> states the self-FK admits are concrete and a junction table eliminates
> them. The dedicated /pair endpoint composes with the junction-table
> choice and preserves the typed singular contract. The auto_reverse UX
> intent is preserved by routing the dialog toggle to a different endpoint.
> Confidence: HIGH.
