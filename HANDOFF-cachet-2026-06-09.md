# Cachet handoff, 2026-06-09

Read this first if you are a new session opening this repo to work on Cachet.
It tells you exactly where things stand, how to run the app, and what to
build next. No em dashes, no slop (project rule). Do not push and do not
open PRs unless the user explicitly says so.

## TL;DR

- All screenshot fixes and the overnight verify-honesty work are **committed
  on `main`** (HEAD `892084724`). `main` is 12 commits ahead of `origin/main`
  and **not pushed**, by design.
- The build is green: 217 Python verify/legal tests pass, frontend
  typecheck + lint clean, and the vault frontend builds from scratch in
  ~1.5s with the vault shell in the bundle.
- The engine was proven honest live against a real source: a fabricated
  quote reads "could not verify", an unbundled cite reads "outside the
  offline corpus checked", and a verbatim quote reads verified. No false
  "present in your sources".
- Everything runs offline, no egress. `tests.test_zero_egress` is 7/7 green
  under a hard socket ban.

## The one rule that keeps getting broken: use the VAULT UI

There are two Cachet frontends in this repo's history. Only one is real.

- **Correct (the product):** the **vault UI**. Entry is `CachetApp.tsx` as the
  vault shell. Surfaces are `LecternView` (the verify landing with the Cachet
  logo), `VaultView` (the Vault tab), and `VerifyResults.tsx`. Tabs sit on the
  right. The empty state reads "OPEN THE VAULT TO LOAD IT". The bundle string
  marker is `Lectern`.
- **Wrong (do not touch, do not ship):** an old standalone "Verify / Shelf"
  skeleton that also rendered from `CachetApp.tsx` on the pre-merge `main`
  skeleton. The user has said, in the strongest terms, that this interface
  will never be used. Every bug they reported came from the vault UI.

If you are ever unsure which UI you are looking at, grep the running bundle
or the source for the string `OPEN THE VAULT` / `Lectern`. If it is not there,
you are in the wrong UI. See `CACHET-VERIFY-UI-PORT-NOTES.md` for the history
of this exact mistake (it happened more than once).

## How to run it

From the repo root (the vault UI is now on `main`, and also lives in the
worktree at `.claude/worktrees/zealous-taussig-60b96a/`):

```bash
./run-cachet.sh            # builds the vault frontend (vite --mode cachet) then serves
./run-cachet.sh --serve    # skip the build, just serve the current dist
```

Then open **http://127.0.0.1:8000**. Ctrl-C to stop.

What `run-cachet.sh` does, and why it matters:
- It always builds with `vite build --mode cachet`. That mode loads
  `.env.cachet`, which sets `VITE_CACHET_ONLY=true`, which makes `main.tsx`
  render `CachetApp` (the vault shell). Building any other way gives you the
  study app or the wrong shell.
- It then runs `script/serve-cachet.py`, which serves the built `frontend/dist`
  over loopback `:8000` from one FastAPI process, injects the local-API token
  into the served HTML so `POST /api/verify` works in a plain browser, and
  **hard-pins** `CACHET_DETERMINISTIC_VERIFY=1` (no LLM, no egress).

The raw build command, if you ever need it by hand:
`cd frontend && corepack pnpm exec vite build --mode cachet && cd ..`

## Required one-time setup: the offline embedder cache

The in-house contract wedge uses a local embedder, `BAAI/bge-small-en-v1.5`
via fastembed. At verify time the code forces `HF_HUB_OFFLINE=1` and **fails
loud** if the weights are not already cached. This is the privacy attestation:
nothing downloads at verify time. You must provision the weights once, with
the network on, to BOTH caches (the custom dir the server uses, and the
fastembed default the tests use):

```bash
# custom dir used by serve-cachet.py
CARREL_FASTEMBED_CACHE_DIR=~/.cache/carrel-fastembed HF_HUB_OFFLINE=0 \
  .venv/bin/python -c "from fastembed import TextEmbedding; \
    TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='$HOME/.cache/carrel-fastembed')"

# fastembed default cache used by the test suite
HF_HUB_OFFLINE=0 .venv/bin/python -c "from fastembed import TextEmbedding; \
    TextEmbedding('BAAI/bge-small-en-v1.5')"
```

Both are already provisioned on this machine. A fresh machine needs this or
the contract path reports "the offline embedding model is not cached" and a
contract claim that should read "unsupported" degrades to "unknown".

## What was fixed this session

Engine (backend):
- **Three-state case existence (`#1`).** A cite that is simply outside the
  bundled offline corpus is now "could not check" ("outside the offline corpus
  checked. Confirm it against the full national database."), not a false
  "citation not found". A bounded-corpus 404 no longer masquerades as
  fabrication. See `services/verify.py` (`_verdict_from_case_verdicts`,
  `_deterministic_reason`) and `deterministic_envelope.py`
  (`_annotate_litigator_verdicts` sets `bounded_corpus`).
- **C1, C2, C3 false-positive paths closed.** C1: an LLM grounding error can
  no longer surface as a silent green. C2: a quoted phrase that arrived via a
  non-quote anchor is re-checked against the matched clause and downgraded to
  "could not check" if it does not actually appear. C3: a topic-overlap gate
  stops an off-topic clause from being treated as on point. See
  `deterministic_envelope.py` (`_contract_claim`, `_clause_on_topic`).
- **D1 quote-panel reconciliation.** Contract clause text is now carried into
  the verdict and the source pool, so the quote panel and the per-claim cards
  agree.

UI (vault surface):
- De-duplicated the unattributed-quotes tray (it was shown twice). Removed the
  duplicate block from `WorkspaceMargin.tsx` and `VerifyResults.tsx`.
- Tofu / non-printable glyph fix: new `displaySafe.ts` (offset-safe,
  ASCII-only codepoint ranges, replaces non-printables with U+FFFD), applied
  at text-render sites.
- Opaque certification overlay: `.certOverlay` is now solid (`rgb(14 14 16)`),
  not 72% alpha. Note: `.sourceScrim` legitimately stays translucent; that is
  a different overlay and is not a regression.
- Certification label relabeled (Harvey's call): "Complete record of all
  statements checked", with a note that it is the full record including the
  items flagged for review.

Per-claim disposition (`claimDisposition.ts`): `fabricated` now excludes a
bounded-corpus 404; added an `outsideCoverage` disposition mapping to
"could not check".

## Verify documents (for a live demo)

In `~/Downloads/Cachet-verify-documents/` (both .md/.txt and .docx):
- `loving_v_virginia_excerpt.md`: the SOURCE to load into the vault. Verbatim
  Loving v. Virginia holdings from Cornell LII.
- `brief_to_verify.txt` / `.docx`: a brief mixing two real quotes with two
  fabricated holdings.
- `demo-claims.md` / `.docx`: paste-one-sentence-at-a-time claims, half
  verbatim (should read verified), half fabricated (should read could not
  verify).

Demo flow: load the excerpt into the vault, then verify the brief or paste the
demo claims. Cachet confirms the real quotes and refuses the fabricated ones.
Paste ONE sentence at a time: the engine grounds per sentence, and a
multi-quote paragraph collapses into a single claim (documented limitation,
see below).

## What genuinely still needs building

The screenshot and overnight fixes are done. There is no half-built feature
dangling. The remaining work, in rough priority:

1. **Unit-of-grounding limitation (documented, not fixed).** Multiple quotes in
   one sentence without a citation collapse into one claim, because the
   sentence splitter deliberately does not break on a closing quote (it keeps a
   holding and its trailing citation together). Pinned by
   `tests/test_legal_sentences.py::test_quoted_holding_keeps_its_following_citation`
   and documented in
   `docs/notes/2026-06-09-cachet-unit-of-grounding-limitation.md`. A real fix
   is non-trivial; do not "fix" it by breaking the holding-plus-citation rule.
2. **Clean-prose coverage wording (gated on lawyer validation).** Anchor-free
   prose should get a coverage statement, never a "verified" badge, and
   "untreated" (no card) must stay distinct from "could not check". Wording
   must be validated with real lawyers before shipping. See
   `docs/notes/2026-06-08-untreated-vs-could-not-check.md` and the
   `cachet-clean-prose-coverage-decision` memory.
3. **Contract anchor coverage (~25 to 35%).** The deterministic extractor
   covers only part of contract clauses by anchor. Expanding anchor detectors
   (party, defined-term, section sign, amounts, dates) lifts the in-house
   wedge. Background in
   `docs/notes/2026-06-05-cachet-deterministic-extraction.md`.
4. **Extraction P3: strangle the study app (structural, ADR-0011).** Separate
   Cachet from Carrel in place, leaf-first. Inventory at
   `docs/notes/2026-06-06-p3-strangle-deletion-inventory.md`. This is the path
   to a standalone Cachet binary and the only place with one-way doors, so move
   carefully.

None of these are blockers for a demo. The app as merged is demo-ready.

## Validation, not just building

The product bar is "Harvey, our senior lawyer, could use Cachet right now and
be happy." Harvey is a priors-and-pressure-test persona, not a substitute for
real customers (he says so himself). Real validation runs through the warm
Lebanese channel and, for the in-house no-cloud contract wedge, the firm's
Gulf-exposed clients. Civil-law jurisdictions kill the litigator fake-cite
wedge (no binding precedent, no fake-cite pain), so test the contract wedge
there. See the `cachet-lebanon-validation-interviews` memory.

## Constraints (do not violate)

- **Do not push, do not open PRs** unless the user explicitly asks. Commit and
  merge locally only.
- **Zero egress must hold.** No new network calls on the verify path. Prove it
  with `tests.test_zero_egress` under the socket ban, not by reading code.
- **No em dashes, no AI-slop vocabulary** in any prose, commit, or doc.
- **Never print or log secrets.** The serve token is a fixed demo token; it
  authorizes only the local loopback call and never leaves the device.
- **The deterministic engine is the product.** No generation. The LLM path
  exists only as an explicit env opt-out (`CACHET_DETERMINISTIC_VERIFY=0`); the
  demo and the default never touch it.

## Repo state notes

- `main` HEAD `892084724` == branch `claude/zealous-taussig-60b96a`. Linear
  history, fast-forwarded, not pushed.
- The main checkout had an uncommitted `.claude/launch.json` (transient
  dev-server preview configs). It was stashed before the fast-forward and is
  recoverable at `stash@{0}` ("main preview launch configs"). The merged
  `launch.json` already has an equivalent `cachet` config, so you probably do
  not need the stash.
- Untracked files in the main checkout (`chatgpt-app/`,
  `man_solo_portrait_final.png`, `cachet-landing/.gitignore`, an older
  `CACHET-SHELL-HANDOFF.md`) are unrelated pre-existing WIP. They are not part
  of this session's work and were left untouched.
- Other reference docs in the worktree root: `CACHET-DEMO-RUNBOOK.md`,
  `CACHET-ENGINE-BUILD-HANDOFF.md`, `CACHET-VERIFY-UI-PORT-NOTES.md`,
  `HANDOVER-cachet-ui-2026-06-08.md`.
