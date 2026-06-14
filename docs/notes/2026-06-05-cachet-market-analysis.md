# Cachet market analysis (2026-06-05, 37-agent) — reconstructed

Reconstructed 2026-06-14 from claude-mem observation #18682 after the original
278-line draft was lost (untracked file in a worktree removed during git cleanup;
see the postmortem below). This is the substance, not the verbatim prose. The
expanded successor of this analysis is `docs/notes/2026-06-05-cachet-competitive-analysis.md`
(54-agent), which is the authoritative version; this file exists to preserve the
37-agent bottom line and to resolve the cross-reference to it in
`docs/notes/2026-06-05-cachet-local-architecture.md`.

## Bottom line

The litigator citation-check wedge is **commoditized**:
- Free inside Claude via the CourtListener MCP (May 2026).
- LawDroid at ~$25/mo; Clearbrief at ~$300/mo.
- BriefCatch RealityCheck ships the same deterministic + LLM design Cachet uses.

So **lead with the in-house, no-cloud wedge**, not litigator pre-flight.

## Defensible pillars
1. **Holding-match rigor** (not just does-the-cite-exist, but does the opinion support the claim).
2. **True on-device / no-cloud** verification.

Caveat carried in the draft: **"local has a cloud asterisk today"** — the Verify
path is Claude-gated (calls api.anthropic.com), so the no-cloud claim is a roadmap
position until the deterministic/local path is the default. (This later became the
runtime-zero-egress framing.)

## Competitive set named
Harvey (then ~$11B valuation), Thomson Reuters CoCounsel / Westlaw, LexisNexis,
Clearbrief, BriefCatch, Paxton AI, LawDroid.

## Phase 0 gate
Do not build further until **≥3 written paid-pilot commitments** from regulated
in-house buyers.

---

## Companion: architecture research brief (103 lines, also lost, work product on main)

The companion `2026-06-05-cachet-architecture-research-brief.md` was a kickoff
prompt for a research session on Cachet's local-verification architecture. Its
work product **landed as `docs/notes/2026-06-05-cachet-local-architecture.md`**
(on main), so only the procedural kickoff prompt was lost. It posed 8 architecture
questions — local inference stack (Apple Foundation Models vs MLX vs Ollama); the
deterministic vs LLM boundary; offline case-existence; local NLI / entailment; a
provable-offline demo; the audit artifact; model packaging; provider provenance —
and two demo decisions: audience = validation lawyers + investors; surface = both
the litigator citation catch and the in-house contract-claim verification, sequenced.

---

## Postmortem (why this had to be reconstructed)

During the 2026-06-14 git-sprawl cleanup, a "knock out the decision branches" step
committed each worktree's unique work to its branch and pushed it to origin before
removing the worktree. For this worktree the two docs were **untracked**, so
`git add` of named paths that were already correct still left **nothing staged**;
the loop did not guard on that and removed the worktree anyway, deleting the only
on-disk copy. Untracked files are not git objects, so `git fsck` could not recover
them. The fix (now built into the auto-prune script): **never remove a worktree
unless its real changes were verifiably committed AND pushed**; treat an empty
commit as a hard stop, not a skip. See [[cachet-git-sprawl-cleanup]].
