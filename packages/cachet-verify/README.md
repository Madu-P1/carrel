# cachet-verify

The deterministic Cachet attestation kernel, packaged for embedding.

```python
from cachet_verify.adapter import verify_claim   # verified | altered | could_not_check
```

Three states, no confidence float. `altered` dominates, `could_not_check` is the
floor, `verified` requires unanimous positive evidence, and silence never passes
(ADR-0015). The verdict path runs no model and makes no network call; the
`AttestationDaemon` binds loopback only, so zero-egress is a provable process
property. Every result is offline-reproducible and sealed by a canonical
SHA-256 fingerprint (`cachet_verify.certificate`).

## This is not a copy

The source in this package is the repo's real `cachet_verify/` tree, reached
through a symlink — there is one source of truth, not a vendored fork. This is
ADR-0014's point: a second copy is what drifts, and a drifted verifier mints a
false verdict, which is brand-fatal. Surfaces (the app, the companion browser
extension, the website) depend on THIS package rather than re-vendoring the
engine.

## The pure / semantic split

`cachet_verify.engine.subject_labeler` can call an on-device semantic labeler,
but its `ai.afm_client` import is lazy and `try/except`-guarded to a regex
floor, so the pure deterministic paths import and run with zero AI dependency.
The runtime third-party closure is exactly `python-dateutil` and `eyecite`.

## Build and self-test in isolation

```
python -m build --wheel                 # from this directory
pip install dist/cachet_verify-*.whl    # into a fresh venv
python -m cachet_verify --help          # the CLI gate (exit codes 0/1/2)
```

The conformance corpus (`cachet_verify/conformance_corpus/nonlegal-v1.jsonl`)
is the executable honesty spec every port must pass; it ships inside the wheel.
