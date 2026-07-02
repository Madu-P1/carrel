# Embedding the Cachet attestation kernel

One kernel, one contract, three ways in. Every surface — a Word add-in, an IDE
panel, a CI job, the Cachet app itself — is a thin client of the same
three-state verdict:

    verify(claim, sources) -> verified | altered | could_not_check

The honesty guarantees you inherit (and may never weaken):

- **Never a false green.** An altered claim cannot read `verified`. Enforced by
  the conformance suite; a distribution that fails one floor case is not a
  Cachet kernel.
- **Never a silent guess.** Anything the deterministic engine cannot trace to a
  source refuses (`could_not_check`) with the reason stated.
- **Provenance on everything.** Every check names its evidence root.
- **Zero egress.** The kernel opens no sockets (socket-ban proven in CI). The
  daemon binds 127.0.0.1 only, by construction.

## 1. The loopback daemon (recommended for apps)

```python
from cachet_verify.daemon import AttestationDaemon
daemon = AttestationDaemon(token="<random-token>", port=8787)
daemon.start()
```

```bash
curl -s http://127.0.0.1:8787/health
# {"ok": true, "schema_version": 1}

curl -s -X POST http://127.0.0.1:8787/verify \
  -H "X-Cachet-Token: <random-token>" -H "Content-Type: application/json" \
  -d '{"claim": "The fund totals $360 million.",
       "sources": ["The fund totals $180 million."]}'
# {"schema_version": 1, "state": "altered",
#  "checks": [{"state": "altered", "provenance": "deterministic",
#              "detail": "The summary states $360 million; the loaded source
#                         states $180 million.", "subject": "..."}]}

curl -s -X POST http://127.0.0.1:8787/attest \
  -H "X-Cachet-Token: <random-token>" -H "Content-Type: application/json" \
  -d '{"draft": "<whole document>", "sources": ["<source text>"]}'
# -> the sealed certificate (see §4)
```

Sources may be raw strings or `{"text": "...", "truncated": true|false,
"complete": true|false}` records. A quote missing from a truncated source
refuses instead of flagging — pass honesty about your sources in, get honesty
about the claims out.

Errors carry stable codes (`error.code`): `unauthorized`, `bad_request`,
`payload_too_large`, `not_found`, `method_not_allowed`. Branch on codes, never
message text. The wire contract is additive-only: fields appear, none are
removed or repurposed.

## 2. The CLI (recommended for CI gates)

```bash
python -m cachet_verify --draft-file summary.md \
    --source-file contract.txt --certificate cert.json --exhibit
```

Exit codes ARE the gate: `0` verified, `1` altered, `2` could_not_check,
`3` usage error, `4` internal error. Verdict codes are emitted only by a
completed engine run — a crash or unwritable path can never masquerade as a
verdict. The honest CI recipe: fail the pipeline on `1`, route `2` to a human.

## 3. The Python API (in-process, same repo family)

```python
from cachet_verify.adapter import verify_claim, attest_draft
attestation = verify_claim("The fee is $5 million.", [source_text])
draft = attest_draft(whole_draft, [source_a, source_b])
```

## 4. The certificate (the demandable artifact)

`POST /attest`, the CLI's `--certificate`, and `/api/attest` on the app server
all return the same sealed record: canonical-JSON body, SHA-256 fingerprint,
draft and source hashes, per-claim verdicts with receipts. Verify offline:

```python
from cachet_verify.certificate import verify_certificate, revalidate_certificate
verify_certificate(cert)                        # seal intact?
revalidate_certificate(cert, draft, sources)    # inputs identical + verdicts reproduce?
```

Any tampering — one flipped verdict, one edited detail — breaks the seal.

## 5. Prove your distribution is a Cachet kernel

```bash
python -m cachet_verify --conformance            # bundled corpus
python -m cachet_verify --conformance my.jsonl   # your own cases
```

Exit 0 iff every honesty floor holds. Catch rate is reported, not gated:
implementations may differ in coverage, never in honesty.
