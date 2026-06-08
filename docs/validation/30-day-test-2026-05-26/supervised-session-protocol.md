# Supervised session protocol — Carrel validation pilot

T65 Deliverable 3. The watch-session playbook for the 30-day validation test, run as
**supervised sessions** (litigator uses Carrel on the operator's machine, in person or over
screen-share) rather than solo-distributed software. This is the interim method while
standalone distribution (bundled backend + in-app keys + signing) is unbuilt; it is also the
*right* method for validation, because the operator observing the litigator's reaction is the
data.

## The one question each session answers
**Would this litigator change what they file because of Carrel, and is that worth paying for?**
Everything below serves that. We are testing demand for an *independent verification layer*, not
collecting a feature wishlist. A session that produces ten feature requests and no trust/pay
signal is a failed session.

## Pre-session checklist (operator, ~10 min before)
- [ ] Backend up with real keys: `./script/build_and_run.sh` from the repo with `ANTHROPIC_API_KEY` **and** `COURTLISTENER_API_TOKEN` in `.env`. Confirm a verify call actually runs (provider resolves to `claude`, not `ai_disabled`) — the catch-test showed a silent provider-off no-ops the whole engine.
- [ ] Pace awareness: free CourtListener tier is 5/min. A real brief with 20+ cites will rate-limit mid-session. Either pre-warm the cites you'll hit, keep the draft short, or have the upgraded tier in place. Decide before the litigator is watching.
- [ ] Material ready, in priority order: (1) **the litigator's own real draft** — highest signal; ask them to bring one they've filed or are about to. (2) A seeded memo (`seed-memos/`) as fallback if they bring nothing. Their own work beats a synthetic memo every time.
- [ ] Screen recording + explicit consent. One shared notes doc open for verbatim quotes.
- [ ] Neutral framing ready (below). Do not prepare a demo script — you are not pitching.

## Framing the ask (to the litigator, 60 seconds, neutral)
"This checks a draft's citations against public records and flags anything it can't stand behind.
Paste something you've worked on and react out loud — tell me where you'd trust it and where you
wouldn't. I'm not selling you anything today; I want to know if it's wrong or useless." Then stop
talking. Do not narrate the product. Let them hit it cold.

## Session flow (~45-60 min)
1. **Cold first contact (5 min).** They paste a draft and run it. Say nothing. Watch the first verdict land.
2. **Let them drive (20-25 min).** They read the verdicts. You only answer direct questions, and even then minimally. Resist explaining what a verdict "means" — if they can't tell, that's a finding.
3. **The hard cases (10 min).** Steer toward a flagged cite and a refusal if the draft surfaced them; otherwise run the seeded memo's Lochner-style mismatch and the phantom. Watch the reaction to "cannot verify" specifically.
4. **Probe (10 min).** Open questions only (below).
5. **Close.** No commitments asked. Thank them. Debrief yourself within the hour.

## The five moments to watch (the actual data)
1. **First verdict.** Do they believe it, or immediately distrust it? Trust is the whole game.
2. **A flag (mismatch / fabrication).** Relief ("good catch") or defensiveness ("it's wrong")? Do they click through to the source to check the checker?
3. **The refusal — "cannot verify" (the gem).** Do they *respect* it (a tool honest about its limits) or are they *frustrated* (want a confident guess)? The discovery thesis is that the refusal is the saleable trust signal. This session tests that thesis. Note their exact words.
4. **One-click-to-source.** Do they use it unprompted? A verifier nobody audits is not trusted; a verifier they spot-check once and then rely on is.
5. **A wrong verdict, if one occurs.** A false flag on a good cite vs a miss on a bad one — which one makes them stop trusting the whole tool? (Hypothesis: false positives are far more corrosive. Confirm.)

## Probe questions (non-leading — do not put words in their mouth)
- "Walk me through what you just did and why."
- "What would you do with this verdict — file as-is, fix it, ignore it?"
- "Would you have caught that yourself? How long would it have taken?"
- "What would make you *not* trust this?"
- "When in your workflow would you run this, if ever?"
- "Who in your firm decides whether to pay for something like this?" (Only near the end. Never lead with price.)
- Silence is a probe. Let them fill it.

## What NOT to do
- Don't demo features or give a tour. Cold contact is the signal.
- Don't defend the tool when they criticize it. Write the criticism down verbatim.
- Don't lead ("isn't it great that..."). You will get false positives that poison the validation.
- Don't fix bugs live or promise fixes. Note them; move on.
- Don't ask "would you pay for this?" as a yes/no. Watch for *unprompted* value language instead; it's the only pay signal that means anything.

## Capture template (fill within 1 hour, per session)
```
Session: <date> · <litigator pseudonym> · <practice area> · <years out> · <AI-in-workflow? y/n>
Material: own-draft | seed-memo · cites checked: N · engine errors/rate-limits hit: ...
Trust (first verdict): believed | skeptical | verified-by-clicking — quote: "..."
Flag reaction: relief | defensive | indifferent — quote: "..."
Refusal reaction (THE GEM): respected | frustrated | didn't notice — quote: "..."
Behavior change: would-run-before-filing | maybe | no — quote: "..."
Pay signal (unprompted only): strong | weak | none — quote: "...", who-buys: ...
Wrong verdict observed? false-positive | miss | none — trust impact: ...
One-line verdict for the decision rule: COMMIT-leaning | FALLBACK-leaning | KILL-leaning
```

## How sessions roll into the go/no-go
Each session's one-line verdict feeds the binding **COMMIT / FALLBACK / KILL** decision rule (T65
Deliverable 4 in `../../plans/t65-validation-test-prep-2026-05-29.md` — thresholds are the
founder's to ratify before sessions begin, so the bar is set *before* we see results and can't be
rationalized after). Capture the demand and trust signal honestly even when it cuts against the
product; a clean KILL signal at 8 sessions is a successful validation test, not a failure.

## Operator note on the interim method
Supervised-on-your-machine sidesteps both unbuilt distribution pieces (no bundled backend, no
in-app key entry). It caps reach at how many sessions you can personally run, which is correct for
validation — you want depth of observation, not volume. If the test returns COMMIT, standalone
packaging (bundle backend + in-app API-key settings + Keychain + sign/notarize) becomes the first
build of the next phase, justified by proven demand.
