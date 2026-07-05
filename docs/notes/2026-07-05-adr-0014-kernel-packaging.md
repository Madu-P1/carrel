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
   - **Slices 3+ (residue, then parametric/quote) are NOT clean swaps.** The
     companion's `parametric.py` is a single merged 470-line module where
     quantity/count extraction is interleaved with money/magnitude/percent/date
     in one `extract_anchors`, producing the companion's own `Anchor` type;
     the kernel keeps `residue` separate (`ResidueAnchor`, its own span-skip and
     year-shaped-integer handling). Routing just the residue half risks a subtle
     verdict divergence not covered by the conformance corpus, so it needs a
     careful refactor with differential testing (or a kernel-side stdlib
     parametric entry the companion can adopt wholesale) — a focused follow-up,
     not a quick swap. Left for its own session/PR.
2. **Website mirror re-point — still open.**
   `~/Desktop/cachetverify` carries TWO pre-extraction copies of the kernel
   (`packages/cachet-kernel` and `site/api/_kernel`), both in the old
   `src/{services,ai}` layout, and the site's `api/verify.py` runs one live on
   Vercel. Re-syncing/re-pointing them to depend on `cachet-verify` is the next
   scoped PR; it touches the deployed verify endpoint, so it gets its own
   careful change. Its `pyproject` also under-declares deps (omits `eyecite`),
   which this package fixes.
