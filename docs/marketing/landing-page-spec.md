# Carrel landing page — designer brief

> Treat this as a single-source spec. A designer can build the page from this without further questions. Every copy line is final, every section has a defined job, every CTA is named. If something is not in this spec, it is not on the page.

---

## North star

The page exists to do exactly two things, in order:

1. **Convert the right visitor into a Free signup in under 90 seconds.** The person who reads this page should never see anything they have to scroll past to understand. The first scroll proves the wedge; the second scroll proves the system; the third scroll signs them up.
2. **Make the wrong visitor self-select out within 30 seconds.** Carrel is a study app for students with deadlines. Showing it to a non-student is wasted impression cost on both sides. The hero copy must filter aggressively.

If we measure one metric, it is: **% of unique visitors who reach `/signup` within 90 seconds of landing.** Target 8% on launch, 12% by month 3.

---

## Who lands on this page

Three real visitor types. The page is built for the first two; the third self-selects out cleanly.

- **The student in pain (60% of traffic).** Mid-semester, has a real deadline 3-14 days out, currently using 3-5 study apps and feeling like none of them are serving the deadline. They are skeptical, time-poor, and either in a coffee shop or in bed at 11pm. They will scroll fast.
- **The investor / journalist / curious operator (25% of traffic).** Looking at Carrel because they heard "AI-native study app, local-first, deadline-driven, solo-built." They want to see the wedge in 60 seconds and decide whether to take the meeting / write about it. They will read the hero, watch the demo, and bounce or save the link.
- **The wrong visitor (15% of traffic).** Random AI-tools tourist, marketers grazing the space, students looking for free homework help. The hero filters them.

Build for visitor 1. Test on visitor 2 before launching. Do not optimize for visitor 3.

---

## Information architecture

The full page, top to bottom, in order, with zero ambiguity:

1. **Hero** — wedge in one sentence + 90-second screen-recording loop + primary CTA + free-tier proof point
2. **The single demo** — a 30-second autoplaying GIF/MP4 of the citation flight, captioned in 8 words
3. **The deadline pillar** — Plan view screenshot + "Friday is the unit of work" copy
4. **The grounding pillar** — Ask view screenshot + the "every claim cites the source" promise
5. **The privacy pillar** — local-first explainer + the one screenshot that proves it
6. **The student stack** — comparison table vs Notion AI, Quizlet, NotebookLM, ChatGPT
7. **Pricing** — three cards, default selected: Student
8. **FAQ** — 6 questions, all real
9. **Sign-up CTA bar** — sticky on scroll past 60% of the page
10. **Footer** — minimal, honest

That is 10 sections. The page is exactly that. No about-us, no team, no blog, no testimonials yet (we don't have them), no integrations matrix, no "trusted by" logo strip we can't actually substantiate.

---

## Section 1 — Hero

**Goal:** in five seconds, a stranger knows (a) what Carrel does, (b) who it is for, (c) why it is different. In ninety seconds, they sign up.

**Layout:** full-bleed dark canvas. Eyebrow + headline + subhead + two CTAs on the left half. A 90-second autoplay loop of the actual macOS app on the right half. No splash images, no abstract orbs, no laptop mockup.

**Copy (final, do not edit without explicit founder approval):**

```
Eyebrow:    THE STUDENT SOFTWARE FOR PEOPLE WITH DEADLINES
Headline:   Friday is the unit of work.
Subhead:    Drop in your lectures. Add your exam. Carrel plans your week,
            runs the spaced review, and answers questions with citations
            you can click and verify. Local-first. macOS-native.
Primary CTA:    Download for macOS  (≈ Free, no signup needed)
Secondary CTA:  See it in 90 seconds  (scrolls to demo)
Below CTAs:     Free tier never leaves your laptop. Pro is $10/month with .edu.
```

**Design notes:**

- Headline in Instrument Serif at 64-80px. Subhead in SF Pro Text at 18-20px, color `--color-text-secondary`. Line length under 60ch.
- Eyebrow uses the same accent treatment as the in-app eyebrows (uppercase, 11px, 0.12em letter-spacing, `--color-text-tertiary`).
- Primary CTA: solid `--color-accent` background, `--color-text-inverse` text, 44px tall, 24px horizontal padding. Hover lifts opacity to 100% from 92%, no scale. Keyboard `↵` indicator on the right.
- Secondary CTA: ghost button, same height, same padding. No icon.
- "Free tier never leaves your laptop" line below in `--color-text-tertiary` at 13px. This line is the single most important hero detail — it removes the "is this another data-harvesting AI app" objection before the visitor types it.
- Right half: an MP4 / WebM looping silently. Show the macOS app: drop in a PDF, ask one question, click the citation chip, watch it fly to the source span, the chunk pulses. ~7 second loop. Source-of-truth file: `docs/pitch/citation-flight.mp4` (founder records once, served from CDN).
- Mobile (< 768px): the loop moves to below the CTAs, full-width. CTAs stack vertically. Headline drops to 44px.

**Anti-patterns for this section:**
- No "Get started for free" generic CTA copy. Be specific: "Download for macOS."
- No three-pill social proof badge ("Loved by students ★★★★★"). We have no users yet.
- No animated background gradient. The product is the animation.
- No "AI-powered study assistant" anywhere on the page. "AI" is the technology, not the value. Lead with the value.

---

## Section 2 — The single demo

**Goal:** prove the wedge in one moment of motion. The student looks at this and thinks "oh — *that's* the difference."

**Layout:** the same MP4 from the hero, but full-bleed and 2x size, with a one-line caption above and a single explanatory line below. Section background slightly elevated above hero (color `--color-bg-elevated`).

**Copy:**

```
Eyebrow:    THE WEDGE
Headline:   Click any claim. Land on the source. 420ms.
Caption:    Every answer in Carrel flies back to the verbatim chunk it
            came from. No fabrication, no "trust me," no re-reading the
            paper to check.
```

**Design notes:**

- The MP4 has a subtle outer glow (`--shadow-card`) and a 1px hairline border in `--color-border-subtle`.
- Below the MP4, a tight three-icon row: 📄 *PDFs* · 📑 *Slides* · 📚 *EPUB textbooks* — with caption text "and 50+ other formats." Use the Icon primitive from the design system, not emoji. Mobile: drops to two rows.

---

## Section 3 — The deadline pillar

**Goal:** prove the unique product claim. This is what no other study app does.

**Layout:** two-column on desktop, stacked on mobile. Left column: copy. Right column: a screenshot of the actual Plan view showing the WORKING TOWARD rail with three deadlines (high / normal / low severity) plus a coach-generated study block on the WeekTimeGrid.

**Copy:**

```
Eyebrow:    PLAN
Headline:   The deadline schedules itself backward.
Body:       Add the exam, the paper, the problem set. Carrel ranks the
            soonest free block in your real calendar and offers a 60-min
            study session, weighted by how close the deadline is and
            how weak the underlying concept is. Every Friday is fed
            from the work you do every Tuesday.
Pull-out:   "Notion stores your notes. Anki drills your cards.
             Carrel knows your Friday."
```

**Design notes:**

- Pull-out is set in Instrument Serif 28px italic, indented 24px, with a 2px accent-color left border. Treat as a block quote.
- Screenshot in the right column: same `--shadow-card` treatment as the demo MP4. 1.5x the height of the body text block. Annotate three things with subtle accent-colored callouts:
  1. The "+ Add" button on the rail
  2. A high-severity card (Bio midterm)
  3. A coach-generated study block on the grid

---

## Section 4 — The grounding pillar

**Goal:** prove the trust claim that everything else depends on. This is what the AI section is, and it has to be tighter than every competitor's.

**Layout:** three-column horizontal, screenshot of an Ask answer with claim list and citation chips. Each column shows ONE quality of the answer.

**Copy:**

```
Eyebrow:    ASK
Headline:   Source-grounded by architecture, not by promise.

Column 1 — Cited
Every claim links to the verbatim span the model used.
Click the chip, the Reader scrolls to the source, the
chunk highlights for one beat. You can ship the answer.

Column 2 — Bounded
Carrel only answers from sources you've imported. If
the answer isn't in your library, Carrel says so —
loudly — instead of guessing.

Column 3 — Auditable
The unsupported-spans list shows you exactly what
the model could not back up. Three guards: hybrid
retrieval, escaped XML envelopes, verbatim citations.
```

**Design notes:**

- Each column has its own micro-icon at the top (12px, accent color). Use existing Icon primitive: "link" / "source" / "shield-check".
- The full-width screenshot above is a real Ask view — claim list visible, two citation chips visible, one unsupported span visible. Show that "loud" honesty.

---

## Section 5 — The privacy pillar

**Goal:** address the silent objection every privacy-aware student will ask before they install. Make local-first feel like a craft commitment, not a marketing line.

**Layout:** single column, narrow. One screenshot. Three sentences.

**Copy:**

```
Eyebrow:    LOCAL-FIRST
Headline:   Your library never leaves your laptop unless you say so.

Body:       The Free tier ingests, retrieves, and answers entirely
            on-device using a local LLM. Pro upgrades you to Claude
            for harder questions, and only the question plus the
            retrieved chunks travel — never your full library, never
            your highlights, never your reading patterns. We do not
            train on your data. We do not store it on a server.
            We do not have a server.

Footnote:   Open-source the retrieval guardrails on GitHub.
```

**Design notes:**

- Visual element: a single elegant diagram. Box labelled "Your laptop" containing a smaller box "Your library." Outside the laptop box, only one thin arrow labelled "Pro tier: question + retrieved chunks → Claude." Everything else stays inside the laptop boundary. Use thin 1px lines, accent color for the labelled arrow only.
- Footnote links to a real GitHub repo URL once it exists. Until then, omit the footnote entirely. **Never ship a broken link.**

---

## Section 6 — The student stack

**Goal:** position Carrel against the actual apps a student is currently using. The reader recognizes themselves in the row labelled "Today" and wants to be in the row labelled "With Carrel."

**Layout:** comparison table, four rows, four columns. Mobile: collapses to a stacked card-per-tool view.

**Table:**

| | Deadline planning | Universal ingest | Spaced review | Cited answers |
|---|---|---|---|---|
| **Notion AI** | No | No | No | No |
| **Quizlet / Anki** | No | Partial | Yes | No |
| **NotebookLM** | No | Partial | No | Partial |
| **ChatGPT Study Mode** | No | Partial | No | No |
| **Carrel** | **Yes** | **Yes** | **Yes** | **Yes** |

**Design notes:**

- Carrel row has a 1px accent left-border, slightly elevated background, and bold cell text. Other rows: muted text, default surface.
- Cell content: green check + word for "Yes," gray dash for "No," uppercase amber word for "Partial."
- Caption below the table: *"You probably use 3 of these now. The point isn't that Carrel is better at any single column. The point is that no other app is in all four."*

---

## Section 7 — Pricing

**Goal:** make the Student tier obviously the right choice for the page audience. Make Pro feel like a natural upgrade. Don't try to upsell Teams; that's an enterprise sales motion, not a self-serve one.

**Layout:** three cards horizontal. Student card is visually emphasized (border-left in accent color, "RECOMMENDED" pill at top). Mobile: stacks vertically with Student first.

**Copy per card:**

```
─── Free ───
$0 forever
On-device LLM (Llama 3.1 8B)
10 sources max
All product features
Acquisition wedge — never expires
[ Get Carrel Free ]

─── Student · $10/mo ───  (RECOMMENDED, visually emphasized)
.edu address required
Unlimited sources
Claude-powered Ask
Calendar coach + spaced review
Sync across your devices
[ Get the Student plan ]

─── Pro · $20/mo ───
For grad students, MBA, residency, bar prep
Unlimited everything
Priority API for harder questions
Earlier access to new features
[ Get Pro ]
```

**Design notes:**

- Card height equal across all three. Use `--shadow-card` on Student only; the other two use `--shadow-hairline`. This visual hierarchy beats text emphasis.
- "RECOMMENDED" pill at the top of the Student card is `--color-accent` background, `--color-text-inverse` text, 11px uppercase, same eyebrow letter-spacing.
- Below the card row, a single line: *"Annual prepay saves 20%. Cancel any time. We don't auto-renew without an email warning a week ahead."* — this last clause is the single highest-trust line on the page after the privacy section. Founders who break this contract get publicly skewered; saying it out loud is a commitment device.

---

## Section 8 — FAQ

**Goal:** answer the six real objections that block signup. Not the questions we wish people asked, the ones they actually ask.

**Layout:** accordion list. Default state: all closed. Click to expand. Background is `--color-bg-base`, no card per item. 1px hairline borders between items.

**Six questions, in this exact order:**

1. **"Is this just NotebookLM?"** — *No. NotebookLM is a cloud-only, account-gated chat-with-PDF tool from Google. Carrel is a local-first study workspace built around your deadlines, with spaced repetition, calendar planning, and auditable citations. NotebookLM is the demo for the category. Carrel is the system you actually study with.*
2. **"Does my library go to the cloud?"** — *No on the Free tier — everything runs on-device. On Pro, only the question + retrieved chunks go to Claude per request, never your full library. We don't train on your data and we don't have a server to store it on.*
3. **"How is this different from Anki?"** — *Anki drills cards you already wrote. Carrel writes the cards from your sources, schedules the review against your real calendar, and ties the whole queue to whatever exam you have on Friday.*
4. **"What if my professor doesn't share PDFs?"** — *Drop in your lecture slides. Or your scanned notes (Carrel runs OCR via Apple Vision). Or a YouTube link to the lecture (audio support coming Q3). The point is the deadline, not the format.*
5. **"Why macOS only?"** — *Because we ship deeply on one platform before stretching across three. Android is in development for September; Windows is on the year-2 roadmap. If you don't have a Mac, leave us your email and we'll let you know when your platform ships — no marketing list, just one email.*
6. **"What does the founder do if this doesn't work?"** — *Refund any active subscription, open-source the engine, and put a forwarding link on this page to whichever tool succeeded us. We mean it. The line is in our terms of service.*

**Design notes:**

- Each question is set in 17px SF Pro Text semibold. Click expands the answer in 14px regular. Answer line-height 1.55. Max-width 720px.
- Question 6 is the highest-trust question on the page. It appears last so the visitor reads it last and remembers it. Do not move it.
- The chevron on the right rotates 90° on expand. Use a Tier 1 functional motion duration (`--dur-base` 180ms).

---

## Section 9 — Sticky sign-up CTA bar

**Goal:** capture the visitor who scrolled past the third pillar and is convinced.

**Layout:** sticks to the bottom of the viewport once the visitor scrolls past 60% of the page. Slim — 56px tall. Slides up over 240ms with a soft drop-shadow. Dismisses with an X on the right.

**Copy:**

```
Friday is closer than you think.   [ Get Carrel Free ]   ✕
```

**Design notes:**

- Background `--color-bg-elevated` with a top hairline. The CTA button uses the same accent treatment as the hero.
- Mobile: the full bar slides in but truncates to "Get Carrel Free →" without the leading sentence.
- Dismiss X writes a 7-day localStorage flag so we don't pester the same visitor on every load.

---

## Section 10 — Footer

**Goal:** minimal trust signals. Don't pretend to be bigger than we are.

**Three columns:**

```
─── PRODUCT ───       ─── COMPANY ───       ─── LEGAL ───
Download for macOS    Email the founder      Privacy
Pricing               Changelog              Terms of service
What's new            GitHub                 Refund policy
```

**Below the columns, one line:**

```
Built solo by [Founder Name] in [City]. © 2026 Carrel.
```

No logo strip. No "Trusted by 10,000+ students" line. No newsletter signup form. The page already has the signup CTA; the footer doesn't need a second one.

---

## Voice rules + banned phrases

These are absolute. The page does not ship if any of these slip through.

**Banned phrases:**
- "AI-powered" anything
- "Revolutionize" / "reimagine" / "next-generation"
- "Smart" as a marketing adjective ("smart study tool")
- "Seamless" / "intuitive" / "delightful"
- "Cutting-edge" / "state-of-the-art"
- "Empower"
- "Unleash"
- Em dashes anywhere in copy. Use commas, periods, or "..." instead. (Inline lists in the FAQ are fine because they're conversational, not marketing voice.)
- Exclamation marks anywhere in copy except the "loudly" line in Section 4.
- Any sentence longer than 22 words.

**Voice attributes:**
- Lab-notebook concrete. "60-min slot before Bio midterm" beats "AI-scheduled study session."
- Verb-led headlines. "Click any claim. Land on the source." not "The source-grounded experience."
- Specifics over promises. "420ms" beats "fast." "$10/mo" beats "affordable."
- The reader is a student, not a "learner" or "user."

---

## Visual + design system

The landing page is a different surface than the app, but it shares the design system. Hard rules:

- **Type:** Instrument Serif for the headline of every section + the pull-out quote in Section 3 only. SF Pro Text for everything else. No third typeface.
- **Color tokens:** the same dark palette as the app (`--color-bg-base #0e0e10`, `--color-bg-elevated #16161a`, `--color-accent #4f8cff`). Light mode is OFF on this page. Dark is the brand.
- **Accent usage:** primary CTAs, the "RECOMMENDED" pill, the privacy diagram's data-flow arrow, the Carrel row's left-border in the comparison table. Nothing else. Repeat: NOTHING ELSE.
- **Spacing:** 4px base. Sections separated by 96px on desktop, 64px on mobile.
- **Imagery:** every screenshot is from the actual running app. Never mock a screenshot in Figma. If a screenshot would require a feature that doesn't ship, cut the section instead of faking it.
- **Animation:** every motion is sub-300ms except the citation-flight loop. No looping decorative animations anywhere on the page.

---

## Performance + tech

- **First Contentful Paint < 1.0s** on a slow 4G throttle. The hero is HTML + inline critical CSS + a deferred MP4. No SSR-blocking JS.
- **Total page weight under 1.5 MB** including the citation-flight MP4. The MP4 is < 800 KB at 480p, encoded with x264 high profile.
- **No Google Fonts CDN.** Bunny Fonts or self-hosted woff2 for Instrument Serif. The same lesson the app learned the hard way.
- **No analytics on first paint.** Plausible loads after onload, fires once per visit. No Mixpanel, no Hotjar, no full-session recording. The page itself is a privacy statement.
- **Hosted on Cloudflare Pages or Vercel** with edge cache. Static HTML + one MP4. No backend.

---

## What we are NOT putting on this page

Explicit list, so a designer doesn't add these out of habit:

- Logo strip ("Trusted by Stanford, MIT, and Harvard students") — we don't have permission and the visitor will feel lied to.
- A team page, an about page, an investors page, a press kit. Email link in the footer is enough.
- A blog. Either commit to weekly publishing or don't pretend to have one.
- Newsletter signup. Use the in-app email collection instead, after they've installed.
- A live chat widget. The product is the conversation.
- Cookie consent banner — we don't set cookies. The page is static.
- A "what's coming next" roadmap section. It always either disappoints or invites debate. The product earns the next feature; the marketing page doesn't promise it.
- Award badges, Product Hunt embeds, Twitter testimonial embeds. We launch them on social where they belong; the landing page stays clean.

---

## Day-1 A/B tests to ship

Three deliberate splits at launch. All measured against the same primary metric (visitor → signup within 90 seconds).

1. **Hero headline:** "Friday is the unit of work." vs "The study app that doesn't lie to you." vs "Drop your lectures. Add your exam. Carrel does the rest." Hypothesis: the deadline frame outperforms because it filters more aggressively.
2. **Demo placement:** hero (current spec) vs Section 2 only. Hypothesis: hero placement converts faster but increases mid-page bounce; section 2 placement increases scroll depth but decreases top-of-page CTR.
3. **Pricing default selection:** Student card highlighted (current spec) vs Free card highlighted. Hypothesis: emphasizing Free wins on signup count but loses on 30-day-paid conversion.

Run each split for 2 weeks or 5,000 unique visitors, whichever comes first. Decision rule: > 1.5x lift on primary metric, p < 0.10. Otherwise keep the spec default.

---

## The single most important page-load metric

Not Lighthouse score. Not Largest Contentful Paint. The number that matters is:

**Time from page load to the visitor seeing the citation chip fly to the source span.**

If this number is over 6 seconds, the page failed. The hero MP4 should be playing the flight by second 3. The whole motion completes by second 5. By second 6, the visitor's brain has formed the thought "wait, that's actually clever," which is the entire reason they will sign up.

If the founder optimizes one thing about this page after launch, it is that number.

---

## What "perfect" looks like

A page that you can show to:
- A 19-year-old biology student in Lagos and they understand it before their phone overheats
- A YC partner and they say "send me the demo URL" before they finish reading the hero
- A privacy-paranoid grad student and they don't bounce on the first scroll
- A designer at Linear and they can find one thing to compliment

If the page can do all four, ship it.
