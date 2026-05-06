# Carrel — Investor FAQ

> Read these BEFORE the meeting. Memorise the first sentence of each. The rest is detail you reach for if pressed.

## On the product

**Q: Why students, not professionals?**
Students have hard deadlines, low tool inertia, cohort-based viral distribution, and a budget already allocated to study apps (Notion + Quizlet + ChatGPT averages $50/mo). Professionals are a year-2 expansion via the same engine at higher prices (MBA, residency, bar/CFA prep). The student wedge is faster, cheaper, and self-spreading.

**Q: Why macOS only today, and what's the Android plan?**
macOS-native gave us premium polish in the build phase. Android ships next via Capacitor wrapping the existing Vite + Preact bundle, which means the same codebase serves both platforms instead of forking. Investing the full round in two parallel native apps is wasteful at this stage; Capacitor lets one engineer cover both surfaces. iOS follows on the same wrapper.

**Q: Why local-first?**
Three reasons. One: researchers won't upload unpublished papers, clinicians can't upload patient notes, lawyers can't upload privileged docs. Cloud-only is locked out of the highest-value use cases. Two: it's a brand position competitors can't copy without throwing away their architecture. Three: local LLMs (Llama 3.1, Apple Intelligence, Phi-3) finally crossed the quality bar in 2025. The architectural bet pays off now.

**Q: Doesn't Anthropic API mean the user's content goes to Anthropic?**
For the Pro tier, yes — for the question + the retrieved spans, never the whole library. Free tier runs Llama on-device, zero data leaves. We're explicit about this in onboarding. The privacy-conscious user picks the local tier; the speed-and-quality user picks the API tier. They both win.

**Q: How do you stop hallucination?**
Three guards. (1) Retrieval: hybrid FTS5 + sqlite-vec returns the actual document spans. (2) Prompt: spans are wrapped in escaped XML envelopes, instructed as data only. (3) UI: every claim renders with a citation chip that flies to the source span on click. The user can verify in one gesture. We tested this with an 18-probe adversarial suite; all blocked.

## On the market

**Q: Isn't this just NotebookLM?**
NotebookLM is cloud-only, Google-account-gated, no SRS, no calendar coach, no native app, no offline. It's the demo for the category — proof the appetite exists. We win the long tail that Google won't serve: privacy-sensitive, native-app, prosumer, education.

**Q: How is this different from Humata / ChatPDF?**
Two ways. (1) We're a workspace, they're a chat-with-PDF utility. The concept graph and SRS turn a one-shot question into a study system. (2) We're local-first; they're cloud SaaS that uploads your PDFs. For research, law, medicine, finance — they can't be used at all.

**Q: Why won't Apple ship this themselves with Intelligence?**
Apple ships horizontal primitives, not vertical workflows. They give you Writing Tools and Summarize; they don't give you spaced repetition tied to citation graphs tied to calendar blocks. Same reason Notion exists despite Apple Notes.

**Q: TAM?**
Bottom-up: 9M active researchers + 220M students. We're not chasing all of them. We're chasing the prosumer who already pays $99/yr for Readwise + $96/yr for Notion + $200/yr for Obsidian Sync. That overlap is ~3M wallets at $20/mo = $720M ARR ceiling, plus institutional. The first $1M ARR comes from 4,200 prosumer subs.

## On competition

**Q: What stops Notion / Readwise / Obsidian from building this?**
Architecture. Notion is cloud-collaborative-first; making it local-first guts their model. Readwise is read-it-later; the AI cite-and-verify loop is a different surface. Obsidian is plugin-DIY; great for tinkerers, brutal for the prosumer who wants it to just work. We've shipped what each of them would need 18 months and a brand pivot to ship.

**Q: What about open-source competitors?**
We don't compete with PrivateGPT or Local LLM tooling — those are infrastructure for builders. Carrel is a finished product for readers. The one to watch is anything in the "Granola for documents" shape; we're 6–12 months ahead architecturally.

## On the company

**Q: Solo founder?**
Yes today, no in 90 days. The first hire with this round is a senior eng to own the iOS / iPad shell. Solo build is a feature, not a bug — it's how we shipped a 9-feature product to test-passing quality with a 60 KB JS budget. But to scale we need a partner.

**Q: How long until first revenue?**
60 days from the round. Pro tier is built; we gate it behind a license-key check, open a closed beta to 50 design partners, then toggle Stripe. The honest framing: today there are zero paying users. The path is paid revenue inside the first quarter post-funding, 1,000 Pro subs by month 12.

**Q: What kills this?**
Three risks. (1) Apple ships a "Notes with Citations" feature in WWDC '27. We move faster and own the prosumer surface they won't touch. (2) Local LLM quality plateaus and the free tier feels weak. We mitigate by ensuring Pro is so good it pulls upgrade. (3) The macOS-only bet keeps the TAM small until we ship Windows. We accept this; depth beats breadth for v1.

## On the ask

**Q: $750K — what does that buy?**
12 months runway at burn rate ~$60K/mo. That's me full-time, one senior eng hire, a design contractor at 20 hrs/week, ~$8K/mo Anthropic API for free-trial period during launch, ~$5K/mo infra, plus legal/incorporation/EU privacy work and a modest launch-marketing budget. The math is in the data room. The kill metric is 1,000 paying Pro subs by month 12 — miss it, no seed round.

**Q: Why not raise more?**
Smaller round = smaller cap = better outcome for me at the seed. We're going to have hard proof of paid traction within 6 months. Seed is for momentum, not for runway.

**Q: Lead vs party?**
Looking for a lead at $400K+ who can write a check and bring two follow-on intros. Comfortable with party-round structure if no lead emerges, but a single committed partner is materially better for the next round.
