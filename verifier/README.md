# The standalone Cachet certificate verifier

`index.html` is the free, public seal-checker: one self-contained file, zero
dependencies, zero network. Open it from disk (`file://`) or host it anywhere;
paste or drop a Cachet certificate and the seal is verified in the browser via
Web Crypto. Nothing is sent anywhere, no account, no Cachet install needed.

Why it exists (billions plan §3.2, 2026-07-04): the certificate is the
demandable artifact, and **checking one must cost the demander nothing** — the
signer pays, the demander never does. Every recipient who checks a seal learns
the format exists. This file is the distribution channel.

## The contract it verifies (frozen, additive-only — ADR-0015)

- A certificate is one JSON object: `schema_version`, `kernel_version`,
  `issued_at`, `draft_sha256`, `source_sha256s`, `state`
  (`verified | altered | could_not_check`), `claims[]`, `fingerprint`.
- The fingerprint is SHA-256 over the canonical body (every field except
  `fingerprint`), serialized keys-sorted with `,`/`:` separators, UTF-8 —
  byte-identical to the kernel's
  `json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
- Refusals carry the same weight as confirmations. An intact seal proves the
  record is exactly as issued; it does not make any claim true.

## Drift lock

`frontend/src/features/attest/verifierStandalone.test.ts` extracts this page's
inlined algorithm and proves it against the same kernel-issued fixtures that
pin the app's own verifier, plus a no-network/no-telemetry source check. If
this file drifts from the kernel contract, CI fails.
