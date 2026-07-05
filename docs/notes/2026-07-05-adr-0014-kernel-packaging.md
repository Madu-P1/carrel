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

## What remains of ADR-0014 (cross-repo, DESTRUCTIVE — needs go-ahead)

Not done here, deliberately, because each deletes or overwrites code in another
repo:

1. **Companion adopts the packaged kernel and its vendored fork is deleted.**
   `~/Desktop/cachet-companion/cachet_companion/verify/*` (~5,000 lines) is a
   **superset** of `cachet_verify` (it carries citation/validity/cloud seams
   the kernel does not). This is a real migration, not a delete: the
   companion-only surfaces must be re-homed as adapters over the kernel before
   the fork can go. The drift guard is holding in the meantime (conformance
   corpus + `nearcopy.py` byte-identical across repos, checked 2026-07-05).
2. **Website mirror re-point.** `~/Desktop/cachetverify/packages/cachet-kernel`
   is a path-preserving *copy* of the pre-extraction closure (still has the old
   `src/services`, `src/ai` layout). It should become a dependency on this
   `cachet-verify` distribution, or at minimum be re-synced to the new
   `cachet_verify/engine/` layout. Its `pyproject` also under-declares deps
   (omits `eyecite`), which this package fixes.

Both are the next ADR-0014 increments; both are destructive/cross-repo and are
left for an explicit go-ahead.
