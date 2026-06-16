# Cachet night report — 2026-06-15

Branch: `claude/crazy-brahmagupta-301932`. Everything below is committed there
(drafts; nothing pushed/merged/deployed).

## What shipped (verified: live BIM + tests)

1. **Demo segmentation + honesty fix** (`3374549af`) — slide/bullet drafts split
   per line; honest examination drawer; drawer-open layout fixed; exact-token
   highlight (`flagged_spans`). FE 819 + BE verify/legal/zero-egress green.
2. **Armada armed + gate hardened** (`4efac61c4`) — `.claude/forge.engine.tasks.md`
   is the full prioritized goal set; truth-surface files routed to human review;
   real-world-regression invariant added to the contract.
3. **D1 — EU magnitude abbreviations, no catch regression** (`92713c1df`) — the
   hero path. `mln/mn/bn/bln/mld` recognized; the altered-figure pre-pass no longer
   bails on an adjacent comma-decimal. Regression guard locks the mln-class failure.

## The demo, proven live (localhost:8000, real BIM source)

Pasting your tampered BIM slide now returns **3 statements**:
- `(60 billion …)` → **UNSUPPORTED**, underlines `60 billion` ("source states 20 billion")
- `Allocation key … 20% France …` → **UNSUPPORTED**, underlines `20%`
- `Result: 30 mln …` → **VERIFIED**

i.e. **2 of 3 need review · Supported 1** — both alterations caught and pinpointed,
acceptance visible beside the refusal. The examination drawer reads the real
finding; the layout holds when it opens.

## Staged for your review (NOT shipped — needs a human/council call)

- **D2** (conflicting-clauses over-refusal): a *clean* allocation line reads
  could-not-check because an unrelated "16% profitability" clause triggers the
  conflicting-clauses guard. Fixing it safely needs subject-topicality on the
  contradiction; the current refusal is the deliberate guard against false-greening
  an amended-contract conflict. Not demo-critical (D1 gives acceptance). Spec +
  analysis in `forge.engine.tasks.md`.
- The rest of the armada: P1 engine (E2-E4), P3 frontend (F1-F2) — `[REVIEW]`.

## Why no unattended swarm ran

Forge's unattended driver ships on an operator-owned, implementer-unreadable
held-out gate, and **fails closed when that gate is empty** (yours is). It refuses
to autonomously ship a legal-verifier's truth surfaces on the in-repo suite alone —
which is correct: tonight's mln regression passed unit logic and still broke a real
catch. The safe path is supervised truth-surface work (done above for D1) + a
staged review queue, not a fire-and-forget swarm. To enable real overnight runs
later, build a trustworthy `<cage>/held-out/` first (its own task).

## How to run / stop

- Demo server (already running my code against your real data):
  `EINSTEIN_DATA_DIR=/Users/madu/Desktop/Codex/data .venv/bin/python script/serve-cachet.py`
  → http://127.0.0.1:8000  (stop: `lsof -ti tcp:8000 | xargs kill`)
- Supervised Forge on the armada (truth-surface work, with you in the loop):
  `bash ~/.claude/skills/forge/forge-arm.sh` then `/forge` in that session.
- The demo baseline is `3374549af`; nothing autonomous can lose it.
