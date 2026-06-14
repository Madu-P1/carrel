# Touchstone consult: Cachet validation

> Produced by the Touchstone validation-strategist agent (`~/.claude/agents/touchstone.md`)
> on 2026-06-14, grounded in the verified 39-test reference at
> `docs/research/startup-validation-tests-reference.md`. This is the design for
> getting validation, not the validation itself.

## 1. The bet, restated

The single sentence that has to be true: **a regulated in-house legal team that legally cannot put client data into cloud AI will pay real money, on a recurring basis, for an on-device tool that verifies AI-generated claims against their own executed contracts and that earns its keep by refusing as often as it confirms.**

Everything else (the litigator wedge, the refusal-as-trust-moment, zero-egress proof, macOS) is downstream of that sentence. If that sentence is false, the engine is a beautiful answer to a question nobody is funding.

## 2. Riskiest assumption

The recommendation I am about to make is that the riskiest assumption is paid demand, not anything technical. Let me steelman the opposite first, because the team has clearly done real engineering and the instinct is to say "the hard part is proving zero-egress and getting the refusal logic correct."

The strongest version of that counter: in a regulated, security-reviewed sale, the product can be killed at the procurement/security gate no matter how much the lawyer wants it, so the riskiest assumption is "can this clear the institutional veto," not "will a lawyer pay." That is a real risk and it is in the test plan below. But it is the second domino, not the first. You only reach a security review after someone with budget has already decided they want to buy. A product that no economic buyer wants never gets to fail security review.

So the riskiest assumption stands: **regulated in-house counsel will pay for on-device contract-claim verification.** Name it precisely, because three softer assumptions are wearing its clothes, and the Lebanon plan as written is aimed at the soft ones:

- **Soft assumption A: "lawyers have the contract-verification problem."** Almost certainly true and almost worthless. Lawyers verify claims against source documents all day. Having a problem is not the same as having a budget line for your solution to it.
- **Soft assumption B: "lawyers like the concept / find the refusal trustworthy."** This is the one six lawyers already validated, and it is the one the Lebanon interviews will mostly re-validate. It is desirability, not viability.
- **Soft assumption C: "the no-cloud constraint is a real, binding purchase driver."** Plausibly the moat, but a lawyer telling you "yes, we can't use cloud AI" in an interview confirms the constraint exists. It does not confirm they will spend budget to satisfy it with your tool rather than by simply banning AI, waiting for their incumbent (iManage, Litera, Relativity, Microsoft) to ship an on-prem feature, or doing nothing.

The hard RAT is C-into-payment: not "does the constraint exist" but "is the constraint painful enough, and your solution fit enough, that a budget owner moves money this cycle instead of waiting." The Lebanon round as designed tests A and B and gestures at C. It does not test payment. That is the gap.

One more honest cut. The team has correctly written down that "six lawyers love it" is not the paid-demand gate. Good. But the *plan* has not internalized that, because the plan's primary instrument is still more interviews. You cannot escape stated-preference territory by running better stated-preference tests.

## 3. What the Lebanon interview round can and cannot prove

Place interviews on the signal ladder honestly. Weakest to strongest: compliments and opinions, then stated future intent, then an email or signup, then real time and data given, then reputation staked (referral, intro, signed LOI), then money down. **A standard interview lives in the bottom two rungs.** It is stated preference. It is the same currency as the six "I love the concept" reactions, just more of it.

This is not a reason to skip Lebanon. Interviews are the right *problem-and-buyer-mapping* instrument, and the civil-law point is sharp and correct: Lebanon kills Wedge 1, so testing only Wedge 2 there is the right call. The bridge-to-GCC-clients logic is also sound, because it correctly identifies that the firm is a channel and the firm's regulated clients are the economic buyers.

What a strong Lebanon round entitles you to conclude:
- The no-cloud contract-verification problem is real and described in consistent language across independent lawyers (convergence at 3+ unprompted is a genuine signal).
- You can name the actual economic buyer inside a target client org (a GC, a CISO, a head of legal ops) and the firm partner will make a *calendar introduction*, not an email forward. That introduction is the first rung where the signal climbs above talk, because it costs the partner reputation.
- The shape of the buying committee and the veto-holders (security, IT, procurement) for the GCC clients.

What a strong Lebanon round does **not** entitle you to conclude, and must not be allowed to feel like it does:
- That anyone will pay. No money moved. No budget line was created. Enthusiasm in an interview and a purchase order are different decisions made by sometimes different people.
- That the product is built right. Liking a demo of a refusal is not the same as relying on a refusal under deadline pressure with a real contract and a partner waiting.
- That the GCC clients want it. The firm's lawyers are a proxy for their clients, and a proxy's enthusiasm systematically overstates the principal's willingness to pay. The firm has every social incentive to be encouraging to the co-founder's father's contact.

The single most dangerous outcome of the Lebanon round is a deck of warm transcripts that the team reads as a green light. Warm transcripts from a warm channel are the textbook false positive: the relationship cannot be separated from the demand.

## 4. The test sequence that actually resolves the go/no-go

Ranked by signal-per-effort for the in-house no-cloud wedge. The cheapest test that can actually kill the RAT goes first. The principle: stop spending effort on stated preference and start extracting behavioral currency as early as the channel allows.

1. **Past-spend probe, embedded inside the Lebanon interviews (near-zero marginal cost).** You are already doing the interviews. Add the one discipline that converts them from opinion-gathering into evidence: ask only about the past. "Walk me through the last time an AI-drafted claim about a contract turned out to be wrong. What did you do? What does your team pay today, in tools, in associate hours, or in outside counsel, to check AI output against source documents?" Discard every future-tense answer ("we would," "I'd love that"). This is the cheapest thing that can start to kill the RAT, because zero existing spend across a coherent segment is strong evidence the pain is real but not budget-worthy.

2. **The economic-buyer introduction test (cost: one ask per interview).** At the end of each Lebanon interview, ask the partner or the lawyer to book a calendar meeting with the actual budget owner at a GCC client. A champion books the meeting; a coach forwards an email. If, after two asks, no introduction to a budget holder materializes, treat the channel as unqualified for the buyer you actually need. This is the test that converts the firm from a comfort blanket into a real bridge, and it costs almost nothing.

3. **The budget test (cost: one conversation with a budget owner).** Once you reach a budget owner, do not pitch. Ask: "If you decided to solve this, whose budget line does it come from, and what is it competing against this cycle?" A buyer who can name the line and the competing priorities has run the internal conversation. A buyer who says "interesting, come back next quarter" with no named owner and no date has given you a polite no dressed as a maybe.

4. **A paid concierge pilot on one real client's contracts (cost: weeks of your manual labor, not engineering).** This is the first test that produces money-down signal. You, by hand, run the verification service against a GCC client's actual executed contracts, with the lawyer in the loop, and you charge a non-zero fee. It tests the moat (can the work even be done on their data inside their walls), the refusal (do they trust "not in your contract" when it is their contract and their deadline), and willingness to pay simultaneously. It is the highest-signal test you can run before building the scaled product.

5. **The procurement / security-review gauntlet (cost: high, runs only after a buyer says yes).** Front-load the vendor security package (whatever you have: a security questionnaire response, data-handling description, the zero-egress runtime proof) into the *first* real GCC deal and watch whether it survives. This is where macOS-only collides with Windows/VDI shops, and where "local-first" gets stress-tested against an actual CISO. It is last not because it is unimportant but because it can only be run on a live deal with a real budget behind it. A deal dying here, across 3+ accounts on the same objection, is your clearest architectural signal.

Note the inversion: tests 1, 2, 3 are bolted onto the Lebanon round you are already running and cost almost nothing. They climb the ladder without adding a new program. Tests 4 and 5 are the ones that actually resolve the go/no-go, and they require a real buyer, which is exactly what tests 2 and 3 are designed to produce.

## 5. The revealed-preference tests to add

For each: the protocol, the currency it extracts, and a pre-registered pass/kill threshold. Score these against the pre-registered arithmetic before you run them, not after.

### Past-spend probe (currency: revealed past behavior)
- **Protocol:** In every Wedge-2 interview, anchor to a concrete recent episode. Ask what they already pay (associate hours, outside counsel, a tool) to verify AI claims against contracts. Tabulate after every 5 interviews: how many name existing recurring spend, how many surfaced the problem unprompted.
- **Pass:** At least 5 of the first 10 lawyers in the same segment name concrete existing spend (hours or dollars) on this exact job, and the problem surfaces unprompted in a majority. The B2B baseline for pattern confidence is **30 companies interviewed (Forum Ventures, confirmed)**, with **5 to 10 enough to surface initial patterns (contested, treat as directional)**. Do not declare conviction below 30.
- **Kill:** Across 15+ interviews, the dominant answer is "we just handle it manually, it doesn't really cost us" with no existing spend and no prior search for a solution. Per Fitzpatrick, if they never looked for a solution, they will not buy yours.
- **Watch the documented false positive:** a legal team that spent heavily on a *neighbouring* problem (e-discovery, document review) will report that spend and make the budget look real. e-Discovery spend with an IT buyer is not contract-verification spend with a GC. Confirm the spend is on *this* job, *this* buyer, *this* budget line.

### Economic-buyer introduction (currency: reputation staked)
- **Protocol:** Ask the lawyer or partner to book a calendar meeting with the GCC client's budget owner. Calendar invite, not "I'll forward something."
- **Pass:** At least 2 of your warm Lebanon contacts book a live introduction to a named budget owner within two weeks of asking.
- **Kill:** Zero introductions materialize after two asks each across the warm channel. If your warmest possible channel cannot put you in front of a single budget owner, the bridge does not exist and the GCC-client thesis is unvalidated.

### The budget test (currency: organizational commitment, no money yet)
- **Protocol:** With a budget owner, map where the money would come from and what it competes against. Ask for a forward action: a line item, an LOI with a number, or a paid-pilot scope with a finance stakeholder named.
- **Pass:** The buyer names the budget line and the competing priorities unprompted, and offers a next concrete step (intro to finance, request for a security questionnaire, a pilot scope).
- **Kill:** "Bring it up next cycle" with no named owner, no date, no next meeting. The reference is explicit that budget-cycle deferral without a calendar checkpoint is statistically indistinguishable from a polite no. There is no hard public number for this test; score it on the behavioral tells, not a percentage.

### LOI with pricing terms (currency: reputation staked, paper not money)
- **Protocol:** A 1 to 2 page LOI that names the specific problem, the price the client would sign under (per-seat or per-matter), a conversion timeline, and a willingness to take an investor reference call. Walk it through as if closing a real contract.
- **Pass:** **4 to 6 signed LOIs each with a dollar figure (contested benchmark from JumpStart Inc.; treat as directional, not gospel).** Quality tell: the buyer negotiates the price terms aggressively. Negotiation is buying behavior.
- **Kill:** LOIs only from innovation-lab or "interested" contacts without budget authority, or LOIs with no pricing. The reference is blunt that an LOI without a dollar figure is a polite endorsement and nearly worthless. A single big-firm-logo LOI is a vanity signal, not repeatable demand.
- **Honest caveat:** even signed LOIs renege regularly ("the LOI fallacy"). An LOI is a stronger rung than an interview, but it is paper, not money. Do not treat it as the finish line.

### Paid concierge pilot on a real client's contracts (currency: money down, highest pre-build signal)
- **Protocol:** Manually deliver the verification service against one GCC client's actual executed contracts, lawyer in the loop, fully on their infrastructure, and charge a non-zero fee from the start. Document every manual step. Track whether they re-engage and whether they pay again. Charge from session one; a free pilot tests nothing.
- **Pass (concierge framing):** **15 to 25 percent of a trial cohort converts to paying, and 30 percent re-engage within 30 days (practitioner benchmarks, not peer-reviewed; treat as directional).** For the enterprise-pilot framing: a structured paid pilot at **10 to 30 percent of expected ACV credited to year one** that converts. The confirmed conversion benchmark once you are executing well is **70 percent or more of completed paid pilots converting to annual contracts (Lemkin/SaaStr, confirmed; full range 60 to over 90 percent, confirmed)**. With a deployment-heavy product expect the low end near 60 percent.
- **Kill:** They will not pay even a nominal fee, or the pilot runs past 90 days with no conversion decision (perpetual-pilot trap). A free pilot they "agreed to try" is a zero-evidence event.

### Procurement / security gauntlet (currency: deal survival)
- **Protocol:** Push your vendor security package into the first real GCC deal proactively, request a structured review call with their CISO or IT lead, and log every objection as fixable-in-weeks, fixable-in-months, or structurally incompatible. The macOS-only-versus-Windows/VDI objection lands here.
- **Pass:** A deal clears the full standard review with no fatal objection and no exception carve-out, and the pattern repeats across 3+ independent accounts in the same segment.
- **Kill:** The same structural objection (most likely platform: macOS-only against a Windows/VDI shop) kills the deal across multiple accounts. One deal dying is noise; a pattern is the signal.
- **Watch the false positive:** a pilot that passes on an informal waiver ("we'll accept your readiness letter for now") does not generalize. A waiver-aided pilot approval is not org-buyer validation. Note: the widely circulated "73% of enterprise sales for startups fail during vendor assessment" stat has no traceable primary source. Do not anchor on it.

### Fake checkout / pre-commitment (currency: behavioral click-through; lowest fit here)
- **Honest steer:** For a tiny, named, regulated buyer reached through a warm channel, a public fake-checkout landing page is the wrong instrument. Its strength is volume (the reference wants **1,000+ targeted visitors**, **0.5 percent click-through as the floor of viability, confirmed**), and you do not have a volume motion. The B2B equivalent is the LOI form, which you are already running. Skip the consumer-style fake door. If you want a top-of-funnel reading from the existing cachetverify.com landing page, treat it only as directional interest, never as demand, and only if traffic is genuinely targeted at in-house counsel.

## 6. How to weight "six lawyers love the concept"

On the ladder, this is the bottom rung: compliments and opinions. It is worth exactly this much and no more:

- **It is worth:** evidence that the problem is legible and the framing is not insane. It de-risks "will a lawyer understand what we built." It got you a warm channel. That is genuinely useful and not nothing.
- **It is not worth:** any conclusion about demand, willingness to pay, or retention. Six people being nice to a founder, several through a relationship chain, is the canonical false positive. The team already wrote down that this is not the paid-demand gate. Hold that line, because the gravitational pull of the Lebanon round will be to quietly upgrade "they loved it" into "they'll buy it." They are different decisions. Compliments measure politeness; only behavior measures demand.

Concretely: if the only output of the next two months is "now twelve lawyers love it," you have not climbed the ladder at all. You have just gathered more of the same currency.

## 7. Sequencing and the one move this week

Sequencing rule: problem, then solution, then demand, then retention, then channel. You are at the problem-to-demand boundary for Wedge 2. The Lebanon interviews are the right problem-stage instrument, but you must bolt the behavioral tests onto them now, because you will not get a second pass through this warm channel.

**The one move this week:** rewrite the Lebanon interview protocol before the first interview so it does two things it currently does not. First, make every question past-tense and spend-anchored (the past-spend probe). Second, end every single interview with the economic-buyer introduction ask: "Can you put a 30-minute meeting on the calendar with the person at one of your regulated clients who would own the budget for this?" That one ask, repeated, is what converts the firm from a flattering audience into a tested channel, and it is the cheapest possible step toward the only thing that resolves the RAT: a budget owner, a pilot, and money down. Pre-register, in writing, what number of booked introductions counts as pass and what counts as kill, before the first interview, so the result cannot be rationalized after the fact.

Do not build anything new this week. The engine is demo-ready. The constraint is not product; it is evidence.

## 8. Signal check

**My confidence:** High that the riskiest assumption is paid demand from in-house counsel, not anything technical, and high that the current Lebanon plan tests the softer assumptions while leaving the hard one untouched. Moderate on the specific thresholds, because several B2B benchmarks here are contested or practitioner-only (the 4 to 6 LOI count, the 15 to 25 percent concierge conversion, the 10 to 30 percent pilot fee); the confirmed anchors are the 70 percent-plus paid-pilot conversion, the 30-company interview floor, and the 0.5 percent fake-checkout viability floor. Treat the contested ones as directional.

**What none of this can tell you:** whether the GCC market is large enough to be a company even if every test passes. These tests resolve "will this segment pay"; they do not size the segment or tell you the incumbents (iManage, Litera, Microsoft) will not ship an on-prem checkbox that erases your moat before you scale. Market size and incumbent-response risk are separate questions these experiments do not touch.

**The strongest way these tests could fool you:** the warm Lebanese channel produces enthusiastic interviews, a couple of introductions, and even a discounted pilot, all driven by relationship and courtesy to the co-founder's father rather than genuine pull, and you read it as validation. The guard is in the design: insist on cold-or-cool confirmation. Count a pilot or LOI from a warm-network contact at a steep discount as weak, and weight any conversion that comes from a buyer with no social obligation to you as worth several warm ones. If the only people who will pilot are friends of the firm, you have validated the friendship, not the market.

**The next assumption in line, once paid demand is resolved:** deal survival through the GCC institutional veto, with the macOS-only-versus-Windows/VDI platform question as the named, most-likely killer. That is test 5, and it can only run once a budget owner has said yes.

A closing line, in character: do not mistake this memo for the validation. It is the design for getting it. The only thing that will actually tell you whether Cachet is gold is a regulated buyer, with no obligation to be kind to you, moving money. Everything above is just how to get that buyer in the room and read the result honestly when they are.
