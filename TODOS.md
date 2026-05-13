# Carrel — Deferred Work Backlog

Plans that came out of completed reviews but were intentionally not in scope of the milestone they were surfaced in. Each item lives at the path noted; this file is the index.

## Active backlog (from `docs/plans/flashcards-focus-2026-05-09.md` autoplan, approved 2026-05-10)

| Plan | Trigger | Why deferred | Source |
|---|---|---|---|
| `paid-tier-infrastructure.md` | PR 0 split surfaced in eng review | Carrel has no users/accounts/licenses table, no auth middleware, no Stripe. The full "BYOK + paid gate" story is multi-week work that should be its own milestone, not an appendix to flashcards. Includes macOS Keychain integration for Anthropic key storage. | autoplan Phase 3 |
| `flashcard-quality-investigation.md` | User feedback ("card quality is bad") | Auto-gen is paused via PR 0a until card quality is investigated. Needs prompt-engineering pass + eval suite expansion before auto-gen can return behind a feature flag. | autoplan Phase 1 (CEO) |
| `voice-refresh-app-wide.md` | User directive ("more welcoming") | Flashcard surface gets voice work in this milestone (deferred to week 3 pending telemetry). Library, Reader, Ask, Plan, Dashboard, Session need their own focused voice pass. | autoplan Phase 2 (Design) |
| `bulk-card-generation-flow.md` | CEO subagent's "generation-first" reframe | If post-PR-7 telemetry shows median active user has <20 cards, the real funnel issue is generation, not review. This plan covers "drop a textbook chapter → 50 cards proposed in 30s, all source-linked → accept-all in one click." | autoplan Phase 1 (CEO) |
| ~~`flashcards-citation-on-back.md`~~ | ~~Original PR 4~~ | **SHIPPED 2026-05-12** as PR 4 of flashcards-focus. | autoplan Phase 3 |
| ~~`flashcards-cloze-and-reverse.md`~~ | ~~Original PR 5~~ | **SHIPPED 2026-05-13** as PR 5.1 (cloze, ADR 0002) and PR 5.2 (reverse-pair, ADR 0003) of flashcards-focus. | autoplan Phase 3 |

## Notes
- Each plan name in `docs/plans/<plan>.md` when written.
- Pre-commit kill conditions and success metrics live in the originating plan, not here.
- Re-prioritize this list after every milestone closeout, not continuously.
