# Strategic decision brief: Carrel AFM integration — which path forward

*Self-contained briefing for an external AI model. Paste this entire document and ask: "Given everything below, which of the three options should I pick, and why? What am I missing?"*

---

## TL;DR (read this first)

I'm a solo founder building a pre-launch local-first AI study workspace called **Carrel** on macOS. I just landed an integration with Apple's Foundation Models framework (the on-device 3B language model that ships with macOS 26) as my free-tier provider. The bridge works end-to-end at the wire level, but the model is too small to reliably follow my product's nested structured-output schema, so the user-facing Ask flow currently returns visually empty answers when routed through AFM. I have three options on the table and I want a second opinion before I commit my next 3-4 hours.

**The three options:**

1. **Ship Pass 1 honestly with the gap documented** (30 min) — commit what works, PR opens describing the limitation, AFM activates the day a follow-up Phase 4.5 lands.
2. **Push through Phase 4.5 today** (3-4 hr) — write provider-specific schema handling in `services/tutor.py` so AFM produces user-visible answers in the app.
3. **Park AFM for tonight, pivot to customer development** — I have a 3-study-group test planned that I haven't run yet; it would yield stronger product signal than more infra work.

**My question:** Which of these gives me the best expected return on the next 3-4 hours, and what's the meta-question I'm avoiding by even framing it as a technical choice?

---

## Context: who I am and what Carrel is

**Carrel** is a macOS-native study/research workspace. You drop in PDFs, lecture slides, papers; you get cited Q&A (every claim flies back to the exact span in the source in 420 ms), spaced-repetition flashcards generated from your sources, and a deadline-aware coach that schedules study blocks against your real calendar. **Local-first by default** — your library never leaves your laptop unless you opt-in to Claude for harder questions.

**Status:** Pre-launch. Zero users. ~85% feature complete vs my own design doc. I've been building solo for ~6 months. Just renamed from "Einstein Tutor" to "Carrel" two weeks ago. Native Swift macOS shell wraps a WKWebView running a Preact frontend talking to a FastAPI backend.

**Validated wedge** (from 1 customer conversation + my own conviction): privacy + verbatim citations + deadline planning. Three pillars that map to two products:
- **Carrel Study** ($8 individual / $25 cohort) — students + study groups + lab teams. Lead with deadline planner.
- **Carrel Research** ($25/mo / $150-300 institutional seat) — researchers + analysts + lawyers + clinicians. Lead with citations + privacy.

Same codebase, two marketing surfaces.

**Strategic priors:**
- I've decided AFM is the right strategic answer for the free tier. The pitch "we use the LLM Apple ships with your Mac" is unique to my product because Carrel is macOS-only. Nothing else credibly matches it.
- I've spent the last week implementing AFM Pass 1 (Phases 1-3 of a 9-phase plan): a Swift sidecar that wraps the FoundationModels framework, a Python provider implementing my existing `AIProvider` Protocol, and a test suite (50 unit tests passing).
- The next 30 days have one strategic priority: recruit 3 study groups (med M1 cohort, PhD comp-exam group, lab journal-club team), give them Carrel free, watch how they use it, validate which value props actually drive retention. I have a recruitment script ready but haven't sent it.

---

## What just happened (the technical situation)

I built an `EinsteinAFMBridge` Swift CLI that wraps Apple's `LanguageModelSession` and serves it over stdin/stdout JSON to my Python backend. Implemented an `AFMClient` Python class matching my existing `AIProvider` Protocol. Wired it into provider selection.

**At the wire level it works:**
```
Bridge availability probe: ok=true, latency 22 ms, model afm-3b
Bridge real generation:    ok=true, latency 700-3200 ms (warm), text returned correctly
Python end-to-end:         ok=true via subprocess + JSON, full ClaudeCallResult round-trip
50 unit tests passing in 0.006s, ruff clean
```

**But when I flipped the app to use AFM and asked real questions through the actual tutor pipeline, the answers came back visually empty.** Backend logs show:

```
event=tutor_grounded_answer ok=true model=afm-3b hit_count=8
latency_ms=10110.76  citation_attempt_count=0  citation_drop_count=0
```

`ok=true` but `citation_attempt_count=0` means: the LLM call succeeded, my retrieval found 8 relevant chunks, but the model produced zero structured citations. Carrel's UI is built around citation chip flight (click a citation → it animates to the source span in the PDF) — with zero citations, there's nothing to flight, and the answer card renders blank or shows "couldn't synthesize."

**I reproduced the call directly** with my actual tutor system prompt + tool schema. Here's literally what AFM emitted:

```json
{
  "submit_grounded_answer": {
    "answer": "During metaphase, chromosomes align at the cell's equator (the metaphase plate). Spindle fibers attach to the kinetochores. In anaphase, sister chromatids are pulled to opposite poles of the cell.",
    "supported_spans": ["2", "2"],
    "unsupported_spans": []
  }
}
```

**The answer text is correct** (verbatim from chunk 2 of my test source). But the shape doesn't match what my tutor expects:

```json
{
  "summary": "...",                              // AFM produces "answer" instead
  "claims": [{                                   // AFM doesn't produce a claims array at all
    "text": "...",
    "citations": [{
      "chunk_index": 1,
      "quote": "<verbatim span>"
    }]
  }],
  "unsupported_spans": []
}
```

**Three specific deltas in AFM's output:**
1. Wraps the whole payload in the tool name key (`submit_grounded_answer: {...}`) — Claude's tool-use API strips this; AFM emits it as-is.
2. Uses `answer` where the schema requires `summary`.
3. Replaces the nested `claims[].citations[]` array with a flat `supported_spans` list of chunk indices. Loses the verbatim quote (which is what powers the citation chip flight).

**Why this happens:** AFM is a 3B-parameter model. It has no runtime guided-generation API (no `@Generable` for dynamic schemas, no `format` parameter like Ollama). It produces JSON best-effort. Complex nested schemas with field names like `claims[].citations[].chunk_index` are at the edge of what a 3B model reliably follows. Claude Sonnet (200B+) handles it trivially via its native tool-use API.

---

## Why this is a real architectural moment, not just a bug

My `AIProvider` Protocol abstracts over Claude, AFM, and Ollama at the **wire level** — they all accept the same `request_tool_call(tool=...)` and return a typed `ClaudeCallResult`. But **schema adherence is not uniform across providers**, and my `services/tutor.py` schema was implicitly designed against Claude's strict tool-use.

To make small-model providers work in the grounded-answer flow, I need one of:

**A. Provider-specific prompts in `services/tutor.py`** (~80 LOC). Branch on `provider.kind` to emit a flatter schema for AFM/Ollama. Cleanly separable but leaks provider awareness into business logic.

**B. Response normalization in `AFMClient.request_tool_call`** (~60 LOC). Post-process AFM's output to match the requested schema (unwrap tool-name key, alias `answer→summary`, synthesize `claims` from `supported_spans` + chunk text). Keeps the Protocol contract clean but requires `AFMClient` to know chunk text, which means changing the Protocol surface.

**C. Two-tier tool schema** (~120 LOC). Define a "simple" tool schema for local-tier providers and let `services/tutor.py` upgrade the response to the nested `Claim`/`Citation` structures server-side from chunk indices + the original chunks (which the tutor already has in scope).

I lean toward C. A and B both have abstraction smells.

This isn't just about AFM. It's about ANY small local model. The day I want to support Llama 3.2 on Ollama for users on macOS 14/15, the same gap re-opens. Designing for "small model schema friendliness" once now buys me Ollama + AFM + any future local-tier model with no code change.

---

## What I'm worried about (the honest meta-question)

I've been building Carrel for ~6 months. I've shipped a lot of features. I just spent **3 days** on AFM Pass 1, and it works at the wire level but doesn't yet light up the actual product.

**The question I keep avoiding:** Why am I deciding between three engineering options instead of running my 3-study-group customer test?

Defenders of "keep building AFM" argument:
- I can't ship the free tier without it. The "we use the LLM Apple ships with your Mac" pitch line is genuinely unique and is half the strategic moat. Without it I'm a paid Claude wrapper.
- Customer tests with a half-working product give bad signal. Better to wait until the free tier actually works.
- AFM working end-to-end is a 1-day push (Phase 4.5). Then I can pivot to customer test with a complete free tier.

Defenders of "go run the customer test" argument:
- I have zero validated demand for any of this. One customer conversation isn't a market.
- Engineering feels productive but yields no information about whether anyone will actually pay for this.
- The 3-study-group test costs me ~0 in engineering and would tell me, within 30 days, whether my "Carrel Study cohort" pricing hypothesis is real. That's far higher EV than another day of infra.
- My product works fine on Claude. I could test demand TODAY with Claude as the free-tier backend (taking a small per-call cost) instead of waiting for AFM.

I genuinely don't know which framing is right. They both feel true. I'm probably anchored on the engineering side because it's what I'm comfortable with.

---

## Constraints worth knowing about

- **Solo founder.** No team. Every hour I spend on infra is an hour I don't spend on customer dev, marketing, fundraising, or designing the next strategic step.
- **Pre-launch, zero users.** No installed base to break, no revenue to protect, no growth metric to defend. Maximum optionality.
- **Runway is finite.** I'm not VC-funded; I'm self-funded. The economics work for 9-12 more months at current burn.
- **Taste-driven craft is a moat.** Carrel has premium native macOS UX (5 signature motion moments, Linear/Raycast aesthetic, ADRs for every architectural decision). Cutting corners on quality compounds against me.
- **Hardware setup is fine.** macOS 26.4.1 M-series + Apple Intelligence enabled (took a language change to en_US which is itself a real-world UX gotcha worth fixing in install.sh).
- **My users won't have AFM enabled out of the box.** Real shipping requires either bundled install.sh detection (which I have planned for Phase 6) or user-side toggling. Either way it's friction.

---

## My specific decision and the help I want

Pick one:

**(1) Ship Pass 1 honestly** — commit what works to its own branch, PR opens describing the gap as a known limitation. Phase 4.5 stays on the backlog. Total time: 30 min. Outcome: AFM is on disk, integrated, tested, but not yet user-functional. Free tier still requires Claude until Phase 4.5 lands.

**(2) Push Phase 4.5 today** — implement option C (two-tier tool schema with server-side upgrade in `services/tutor.py`). ~3-4 hr. Outcome: AFM actually produces user-visible answers in the app. Free tier is functional. I can credibly run the customer test with AFM as the free local backend.

**(3) Park AFM for tonight, run the 3-study-group test now** — send the recruitment DMs I already have drafted. Use Claude as the free tier for the test (eat the API cost for 18 study-group seats × maybe 50 questions/month = trivial). When the test results come back in 30 days, I'll know whether I'm building for the right buyer at all, which is a higher-order question than which LLM serves the free tier.

**My specific asks of you:**

1. **Which option do you pick and why?** Don't hedge — make a recommendation.
2. **What's the meta-question I'm avoiding by framing this as engineering options?** Be direct.
3. **If you pick (1) or (2), how should I phrase the PR description and commit message to be honest about the limitation without underselling the work?**
4. **If you pick (3), what's the most important thing to maximize on in the recruitment DM and the 30-day test, given my current state?**
5. **What did I get wrong in how I framed the trade-offs above?**

---

## References (in case you want technical detail)

- `services/tutor.py:30-90` — the system prompt + tool schema causing the schema gap
- `services/tutor.py:705-755` — where AFM's flat output fails to populate `Claim` objects
- `ai/afm_client.py` — Python provider (~409 LOC); the `_parse_or_rescue` function already handles markdown fences and prose, but can't fix the missing nested `claims` array
- `macos-app/Sources/EinsteinAFMBridge/main.swift` — Swift CLI sidecar (~271 LOC) that talks to Apple's `LanguageModelSession`
- `docs/plans/afm-integration-2026-05-10.md` — the 9-phase implementation plan; this gap belongs as new "Phase 4.5"
- `docs/plans/afm-runbook-2026-05-10.md` — step-by-step commands to commit + ship Pass 1
- Latency profile of the actual production-path call: 10.1 s for an 8-chunk grounded answer (mostly inference; subprocess overhead ~50-200 ms; first-token ~3 s warm)

---

## One more piece of context that changes the framing

I'm not asking this question because I don't know what to do technically. Option C is the right architectural answer; I could write it in 3-4 hours and ship Pass 1 + 4.5 together as a working free tier by tomorrow.

I'm asking because I suspect the right answer is option (3), and I want someone to either confirm that or argue convincingly that the free tier needs to be functional before the customer test gives meaningful signal. The 6 months I've spent building this is a sunk cost; the 3-4 hours in front of me is the real decision.

Tell me what you actually think.
