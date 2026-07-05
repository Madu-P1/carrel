# ADR-0014: kernel packaged as an installable distribution (2026-07-05)

Status: DONE (the enabling brick). Follows the same-day engine extraction
(`c90d11af8`, ADR-0014 step 3: engine internals moved into
`cachet_verify/engine/`, old paths became `sys.modules` alias shims).

## What shipped

`packages/cachet-verify/` — a proper installable distribution for the kernel:
- `pyproject.toml` declares `cachet-verify` 0.1.0, deps **exactly**
  `python-dateutil>=2.8` and `eyecite~=2.7` (the kernel's entire third-party
  runtime closure — everything else is stdlib), a `cachet-verify` console
  script → `cachet_verify.__main__:main`, and the conformance corpus as
  package data.
- The source is the repo's **real `cachet_verify/` tree, reached through a
  symlink** (`packages/cachet-verify/cachet_verify -> ../../cachet_verify`).
  There is NO copy. This is the ADR's whole point: a second copy is what
  drifts, and a drifted verifier mints a false verdict.

## Why this was the right next step (and why it is non-destructive)

ADR-0014's load-bearing move is "extract the kernel so both surfaces import it
and the vendored fork is deleted." The Codex-internal extraction removed the
in-repo duplication; **packaging is the bridge to the cross-repo half** — the
companion and the website can now depend on this one distribution instead of
re-vendoring the engine. It touches no app runtime code, does not move the live
`cachet_verify/` tree the app imports from repo root, and does not modify the
`uv`-managed root `pyproject.toml` (a new `packages/*` pyproject is not a uv
workspace member, so `uv sync` is unaffected). Fully reversible: delete the dir.

## The proof (this is the real deliverable, not the metadata)

The extraction *claimed* the kernel stands alone. This proves it:

1. `python -m build --wheel` → `cachet_verify-0.1.0-py3-none-any.whl`, whose
   contents include `cachet_verify/engine/*` and
   `cachet_verify/conformance_corpus/nonlegal-v1.jsonl`.
2. Installed into a **fresh venv** (`.isovenv`); pip pulled only
   `cachet-verify`, `eyecite`, `python-dateutil` (+ their transitive deps).
3. In that venv, `services` / `routes` / `ai` are **not importable**
   (`find_spec` → `[]`), and `cachet_verify` resolves from site-packages, not
   the repo.
4. The six kernel suites — kernel, conformance, zero-egress, certificate,
   residue, seam — run **105/105 OK against the installed wheel** from a cwd
   with no repo source on the path. This includes:
   - `KernelSelfContainmentTests`, whose subprocess probe (`python -c "import
     cachet_verify..."`) now runs against the *installed* package and confirms
     it pulls zero app modules;
   - the conformance floors loading the corpus from inside the wheel;
   - the zero-egress socket-ban suite.
5. Back in the repo, the app still imports the kernel from root unchanged
   (`test_cachet_verify_conformance` 10/10). Packaging is inert to the app.

## The `ai.afm_client` / `services.retrieval` non-issue, confirmed

The only two app-module references left in the kernel are both safe for a
standalone install: `engine/subject_labeler.py`'s `from ai.afm_client import ...`
is lazy (inside a function) and `try/except`-guarded to a `RegexFloorLabeler`
fallback, reached only when `CARREL_SUBJECT_LABELER=afm`; `engine/validators.py`'s
`services.retrieval.typed_hybrid` import is `TYPE_CHECKING`-only. The isolated
install ran the full deterministic path with neither present.

## Operator decisions (2026-07-05)

- **Git history:** branch protection forbids force-pushing `main`, so the
  extraction (`c90d11af8`) and packaging (`a8afc3c7c`) commits **stay on main**
  (both green); all remaining ADR-0014 work goes through PRs. The redundant
  `cachet-kernel-extraction` branch was deleted.
- **Companion dependency posture:** the companion depends on the **full**
  `cachet-verify`, accepting its offline pure-Python deps (`eyecite`,
  `dateutil`), rather than a stdlib-only `cachet-verify-core`. Confirmed on
  corrected facts: the companion's verify bridge was previously **100% stdlib**
  (the eyecite/dateutil references in it are comments, not imports). Zero-egress
  is preserved — the kernel makes no network call.

## Cross-repo progress

1. **Companion — slice 1 landed as a draft PR** (`cachet-companion#1`, branch
   `adopt-kernel-nearcopy`). The companion deletes its byte-identical
   `verify/nearcopy.py` and imports `verify_near_copy_flip` from the packaged
   kernel; the old byte-identity sync test becomes an import-source assertion;
   `requirements.txt` (the companion's first dependency) editable-installs the
   kernel from the sibling Codex checkout. `script/verify.sh` RESULT: PASS (all
   10 stages: 567 python / 329 node / held-out de-id gate / 7 egress
   invariants). Scout scope + remaining slices below.
   - The kernel's full `verify_claim`/`attest_draft` API is **not**
     dependency-light (it pulls eyecite+dateutil via `engine.anchors`); only
     `contract`, `residue`, `nearcopy` import with zero heavy deps. So the
     migration goes stdlib-clean-first: **slice 1 nearcopy + slice 2 combine
     (both done, in PR #1)** → residue → then the parametric/quote paths (which
     route through the eyecite-bearing engine modules — the decision slice, now
     unblocked by the accept-eyecite posture). Companion-only seams (citation,
     caselaw, holding, validity, cloud, clause) are NOT duplication and stay.
   - **Slice 2 (combine)** was a clean duck-typed drop-in: the kernel's
     `contract.combine` reads only `.state`, so it rolls up the companion's
     richer `CheckResult` unchanged, and the re-export keeps
     `from cachet_companion.verify import combine` working. Semantics identical.
     Also cleared two pre-existing `F841` lint errors that were failing the
     companion's forge `ruff check` invariant (unrelated to the migration).
   - **Slice 3 (residue) landed in PR #1, via the differential-refactor route.**
     `parametric.extract_anchors` now delegates quantity/count extraction to
     `cachet_verify.residue.extract_residue_anchors` (which even takes a matching
     `claimed_spans` arg); ~90 lines of duplicated residue machinery deleted
     (`_UNIT_TABLE`, `_UNIT_WORDS`, `_QUANTITY`, `_GROUPED_COUNT`, `_PLAIN_COUNT`,
     `_year_shaped`). Proven safe by a **3001-case differential** over
     `extract_anchors` + `verify_parametric` — byte-identical before/after the
     swap and after the dead-code deletion. Money/date/percent/duration
     extraction and `_compare_sentence` stay local.
   - **The residue swap surfaced a real kernel bug (the ADR paying off).**
     `cachet_verify.residue._QUANTITY` had an unbounded `\d+` digit run — a
     **ReDoS (CWE-1333)** reachable through the daemon's `/verify` claim text —
     that the anchors engine and the companion's fork had already fixed but the
     kernel's residue detector had drifted without. Hardened kernel-side (bound
     to `\d{1,18}`/`(?:,\d{3}){1,8}`) with a residue ReDoS regression test, on
     branch `kernel-residue-redos-fix` → **carrel PR #199**. No verdict change
     (the 3001-case differential stays identical). The companion residue slice
     depends on #199 landing: **merge #199 before `cachet-companion#1`.** This is
     exactly the two-copies-drift the extraction exists to end — a fix on one
     side that never reached the other, caught the moment they were unified.
   - **Slices 1-3 + the kernel ReDoS fix are MERGED** (2026-07-05): carrel#199
     (`fe1a55f3a` on main) and cachet-companion#1 (nearcopy+combine+residue, 4
     commits rebased onto companion main). Both mains synced and green together
     (companion 45 core tests OK against the merged kernel).
   - **Slice 4 (parametric money/date) is NOT a delegation — investigated and
     stopped, with evidence.** The companion's `extract_anchors` and
     `_compare_sentence` are **co-designed**: the companion carries currency
     INSIDE its magnitude canonical (`("EUR", val)`) so a currency swap fails the
     canonical compare (a deliberate fix, mythos: magnitude-currency-blind-
     false-green). The kernel's `engine.anchors` magnitude canonical is
     units-only; the kernel reaches the SAME safe verdict (a currency swap →
     `could_not_check`, verified by direct test 2026-07-06) but via its OWN
     comparison path, not its anchors. So feeding the kernel's parametric anchors
     into the companion's `_compare_sentence` would **reintroduce the currency-
     blind false-green** — a naive extraction-delegation is unsafe. Deduping the
     money/date half therefore requires the companion to adopt the kernel's WHOLE
     parametric VERIFY path (extraction + comparison), not just extraction — a
     major refactor that replaces `verify_parametric`, needing a stdlib-clean
     parametric verify entry in the kernel. **Not worth forcing now**; the
     remaining parametric fork is guarded against drift by the shared
     conformance + honesty-parity corpora.
   - **`quote.py`** (the other big companion fork, of `engine.quote_check` +
     `engine.validators`) may be a cleaner delegation than parametric (quote
     checking is more self-contained, and eyecite is now accepted) — worth its
     own scoped investigation before the parametric refactor.

## Where ADR-0014 stands (2026-07-06)

The cleanly-dedupable duplication is gone and merged: kernel extracted +
packaged (main), and the companion's nearcopy + combine + residue forks deleted
and routed through the kernel. The unification lens already earned its keep by
surfacing a real kernel ReDoS (carrel#199). What remains — the companion's
parametric money/date extraction and `quote.py` — are behavior-equivalent
hardened forks that are NOT simple swaps (co-designed extraction+comparison,
load-bearing divergences), guarded against drift by the shared corpora. Fully
finishing "delete the vendored fork" is a dedicated future project (companion
adopts the kernel's whole parametric verify path, differential-tested), not a
quick slice. The website mirror re-point remains a separate scoped PR.
2. **Website mirror re-point — still open.**
   `~/Desktop/cachetverify` carries TWO pre-extraction copies of the kernel
   (`packages/cachet-kernel` and `site/api/_kernel`), both in the old
   `src/{services,ai}` layout, and the site's `api/verify.py` runs one live on
   Vercel. Re-syncing/re-pointing them to depend on `cachet-verify` is the next
   scoped PR; it touches the deployed verify endpoint, so it gets its own
   careful change. Its `pyproject` also under-declares deps (omits `eyecite`),
   which this package fixes.
