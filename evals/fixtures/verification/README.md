# Verification fixtures

Known-bad and known-good documents for the V2 verification engine
(`services/verify.py`, `/api/verify`). Each fixture carries a ground-truth
table at the top stating the per-citation verdict the verifier is expected to
produce.

These are NOT part of the biology ingestion seed in `../manifest.json`. They
are exercised by verification tests / `/api/verify` smoke runs, not by the
groundedness eval harness.

| Fixture | Profile | Notes |
|---|---|---|
| `mata_avianca_style_memo.md` | AI-drafted brief with 4 fabricated + 3 real cites | Sourced from the Mata v. Avianca sanction order (S.D.N.Y. 1:22-cv-01461, June 22, 2023). Tests CourtListener case-existence and holding-match gates together. |
