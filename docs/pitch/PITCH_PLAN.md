# Carrel — Investor Pitch Plan

> Plan, not a script. Audit before walking in. Live demo is the centerpiece — the deck supports it, the deck is not the show.

## The decision you want the investor to make

Wire a check large enough to take Carrel from "production-grade macOS app, solo build" to "10 paying design partners + a second engineer." That's the only ask. Don't muddy it.

Suggested scope: **pre-seed $750K SAFE, $6M post-money cap.** Rationale: 12 months of solo operator + one hire + infra + ~$50k for design and brand polish. Cap is honest for solo + pre-revenue; better outcome at the seed when traction lands. Adjust to room.

Tie the ask to a kill-or-keep metric so the round funds proof, not vibes: **1,000 paying Pro subs by month 12. Miss it, do not raise seed.**

## Audience read (do this in the first 30 seconds)

- **Consumer / edtech investor (Reach, GSV, Owl Ventures, Learn Capital):** lead with "students churn through 8 study apps in 18 months and miss the deadline anyway." Show the Plan view first, then the deadline draft, then the citation flight as the trust closer.
- **Generalist seed (Initialized, Founders Inc, a16z scout, YC):** open with the demo cold. The 30-second Plan-view-with-deadline lands harder than any slide.
- **AI/infra investor:** lead with universal ingest + cited Ask + on-device tier. Frame as "the AI study workspace that works because it cannot lie and is structured around your deadlines."

## The shape of the meeting (30-min slot)

| Min | What | Why |
|---|---|---|
| 0–2 | Cold open: live demo. Drop a PDF, ask a question, click a citation chip, watch it fly to the source span. | Memorable. Sells the thing in 90 seconds without a single slide. |
| 2–10 | Walk the deck (slides 1–6). Problem, insight, product, why-now. | Frame what they just saw. |
| 10–18 | Market, competition, moat, traction. (slides 7–10) | The "is this venture-scale" gate. |
| 18–22 | Team, build proof, ask. (slides 11–12) | Close the loop. |
| 22–30 | Q&A. Have the FAQ doc open. | Where the real conversation happens. |

If they cut you to 15 minutes: skip slides 4 and 8 (product detail + competition); demo carries product, the FAQ covers competition.

## Pre-meeting prep (24 hours before)

1. **Rebuild fresh.** `bash script/build_and_run.sh run`. App launches clean every time, never improvise.
2. **Seed a believable library.** 4–6 PDFs in real subjects (2 textbooks, 1 paper, 1 lecture deck, 1 dense article, 1 meeting notes). Not 200 random files.
3. **Prime the questions.** Have 3 pre-tested questions that produce strong grounded answers with multi-page citations. Memorise them.
4. **Test the citation flight.** This is the wow moment. If it stutters, fix that before anything else.
5. **Disable notifications.** Do Not Disturb on. Slack quit. Calendar quit. One window only.
6. **Battery + adapter.** Plug in 30 min before. Demo on battery is a tempting flex; outage is a brand-killer.
7. **Have the FAQ doc open in a hidden tab.** See `FAQ.md` below.
8. **Dress the room.** If on Zoom: no Picture-in-Picture, full screen, screen-share window not display. If in person: external display tested, app launched on it.

## Anti-mistakes (Garry-style)

- Do not open with the team. The product is the wedge. Team is slide 11.
- Do not run a slide-only meeting. If you can't demo, reschedule. The demo IS the moat signal.
- Do not over-promise on the AI. Carrel's edge is "we don't hallucinate" — every claim flows back to a verbatim span. Lean into that.
- Do not bring up the IAF code in this repo. Different product, different audience. Stay on Carrel.
- Do not bury the local-first story. The Snowden-era investor wants this; the AI-fatigue consumer wants this; the EU regulator wants this. Three constituencies in one feature.

## The follow-up (within 24h)

Send a one-page recap email with:
- The PDF deck attached
- A 90-second screen recording of the citation flight (record once, send to every meeting)
- A link to a private TestFlight or .dmg they can install (gated by your email — one click, they're in)
- The next-meeting ask, named: "Happy to do a 30-min product deep dive next week."

## Slide-by-slide narrative (12 slides, ~3 min each)

| # | Title | One-line | Speaker note |
|---|---|---|---|
| 1 | Carrel | "A study workspace that doesn't lie to you." | Pause. Let the title sit. |
| 2 | The problem | Researchers drown in PDFs. Every AI tool hallucinates. SaaS leaks their reading. | One slow sentence each. |
| 3 | The insight | Local-first + source-grounded. Every claim cites a span you can click and verify. | This is the wedge. Say it twice. |
| 4 | Product | Library, Reader, Ask, Sessions, Concept Graph, Plan. One workspace, four reading modes. | Run them through what they just saw. |
| 5 | The wow | Citation chip flight: ask → answer → click → land on the verbatim span. | If you didn't demo cold, demo here. |
| 6 | Why now | Local LLMs got viable in 2025. Privacy backlash is mainstream. AI-tool fatigue is real. Three tailwinds, one product. | Cite Llama 3.1, GDPR enforcement, Apple Intelligence positioning. |
| 7 | Market | Students 220M, researchers 9M, knowledge workers who read for a living 80M+. Bottom-up: 50k prosumer @ $20/mo = $12M ARR in 24 months. | Don't oversell TAM. Show the path to first $1M. |
| 8 | Competition & moat | NotebookLM (cloud, Google-locked), Humata (cloud, hallucinates), Readwise (no AI), Obsidian + plugins (DIY). Carrel = native + local + grounded. Moat: design taste + verbatim guarantee + macOS-native polish. | Don't mock competitors. Position. |
| 9 | Build proof | Production-grade macOS app, full design system, signal-backed routing, prompt-injection-tested LLM layer, 346 frontend tests + 364 backend tests, all green. Solo built. | Show, don't say. Have CLAUDE.md and AUDIT.md ready to flash. |
| 10 | Business model | Free local tier (10 sources, on-device LLM). Pro $20/mo (Claude API, unlimited sources, calendar coach). Teams $40/seat/mo (shared library, citation governance). Edu site license. | Three tiers, one product. |
| 10 | Today (traction-honest) | What's real now (shipped app, end-to-end demo, solo build). What's next 90 days (50 design partners, Stripe live, first 10 paid subs). | Do not hide that paying users = 0. The honesty IS the signal. |
| 11 | Team & ask | [Founder name], previously [shipped X]. Built solo because [domain reason]. $750K SAFE / $6M post / 12-mo runway / kill metric: 1,000 Pro subs. | Personal sentence on slide 1 already established the founder; here you concretize the ask. |
| 12 | Close | "If you read for a living, you'll never close this app." | One line. Stop talking. |
