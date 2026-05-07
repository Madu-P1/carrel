# Onboarding Tutorial Script — Maya's First Hour

The old FirstRunTour overlays the screen with abstract Source / Anchor / Draft mockup cards. A real user looks past the overlay at the actual app and sees nothing pointing to anything she can touch. This script replaces it with inline coachmarks that attach to live UI elements Maya is already looking at.

The thesis underneath: **the deadline is the unit of work.** Maya has a Cell Bio final in 9 days. Every step in this tutorial eventually ladders back to that. We do not name the thesis, we let her feel it.

## Maya's hour, minute by minute

**T+00:00** — Launches Carrel for the first time. Lands on Dashboard. The greeting reads "Good evening." She skims the eyebrow date, the sentence "Your study environment is ready," and the "Ask your library" composer. She types nothing. Skeptical face.

**T+00:45** — Notices the empty composer placeholder reads "Drop a source first, then ask anything about it." She thinks: fine, it's pointing me somewhere. Below the composer she sees two suggestion chips: "Import a source" and "Browse the library." She clicks **Import a source.**

**T+01:30** — Lands on the Library. Header reads "Your sources." The dropzone on the right side of the header is the loudest object on the page. She drags her **Cell Bio Lecture 7.pdf** onto it. The dropzone outline goes accent-tinted. She drops.

**T+02:15** — A toast appears: "Watch progress in Jobs. Ready sources appear in the Library." She is briefly confused about where "Jobs" is. She waits. About ten seconds later the file appears in a subject card on the grid. The card pops in with a small animation. She drags four more PDFs in succession into the dropzone. Then her syllabus HTML. Then both lecture decks (PPTX).

**T+04:30** — Library now shows two subject cards: an auto-grouped "Cell Biology" card and an "Unsorted" one. She clicks the Cell Biology card. The drill-in panel appears below with eight rows.

**T+05:30** — She clicks Lecture 7. Reader opens with the PDF rendered. There is a left rail listing sections. She does not know what to do here. She scrolls.

**T+07:00** — On page 4 she selects the sentence about chaperone proteins and Hsp70. A small banner appears at the top of the viewer that says **Selection captured: "..."** with a **Save anchor** button. She clicks it. A toast: "Anchor saved."

**T+08:00** — She hits the back arrow in the breadcrumb. Lands on Dashboard. Now the composer is no longer empty-state — the placeholder reads "What do you want to understand right now?" and the chips below say "Explain this simply" / "What's the main argument?" / "Summarise the cited evidence." She types: **"What does Hsp70 actually do during heat shock?"**

**T+09:00** — Routed to the Ask view. The eyebrow says "Live ask," the heading says "Ask from your sources." She sees a scope pill. The answer streams in over a few seconds. There is an answer summary at the top, and below it three claim cards each with a numbered citation chip like `[1]`, `[2]`, `[3]`.

**T+11:00** — She clicks `[1]`. The view flips to Reader, opens Lecture 7 directly to the chunk that grounded the claim. She actually says "huh." Out loud.

**T+12:30** — Back in Ask. On the same claim card she notices a **Save as anchor** button. Clicks. Toast: "Anchor saved."

**T+14:00** — She navigates to Library, clicks Lecture 7, opens the source panel on the right and clicks the **Anchors** tab. Both her saved anchors are there. She clicks one. A dialog titled **Card Draft Drawer** appears with two flashcard drafts. She picks the cleaner one and clicks **Save card**. Toast: "Card saved. The Anchor is now in your review queue."

**T+18:00** — She clicks **Plan** in the sidebar. Sees the heading "Your week, source-grounded." A horizontal rail labeled **Working toward** is empty: "No deadlines yet. Add one to start the coach planning toward it." She clicks **+ Add.**

**T+19:30** — Dialog opens. She types "Cell Biology Final" and picks a date 9 days out. Saves. The deadline appears in the rail with red severity tinting and "in 9 days." She adds the Biochem mid-term too. Both rail cards are now visible.

**T+22:00** — She returns to Dashboard. The "Best time to study" card is now populated. The first row says "Cell Biology Final — Free block tomorrow 2-4pm. 8 days of runway." She thinks: that is the right time. Doesn't accept yet — wants to feel out the rest of the app.

**T+28:00** — A status chip has appeared above the greeting that reads "1 card due now." She clicks it. Lands on Study. Heading: "Ready for review?" with "1 card due." She clicks **Start a session.**

**T+29:00** — Her flashcard front shows the Hsp70 question. She thinks for ten seconds. Hits **Reveal the source-grounded answer.** The back side appears with the reference to her Lecture 7 chunk. She rates **Good.**

**T+30:00** — "Reviewed 1 card." Back-to-review screen. She comes back to the Dashboard.

**T+34:00** — She accepts the suggested study block. Toast: "Added to Calendar." She drags two more PDFs into Library, asks two more questions, saves anchors from each, drafts cards. By T+50 she has 7 cards, 2 deadlines, and a study block on her calendar. The Dashboard hero now reads as a real cockpit, not a placeholder. She closes the app and says "okay."

## On-app tutorial script

Each step is a tooltip or coachmark anchored to a real UI element. Tooltips dismiss on the trigger action or on a small "Got it" affordance in the bubble's corner. State is per-step in `localStorage` (`carrel.tutorial.step.<n>=done`). If Maya completes the underlying action without seeing the coachmark, the step auto-marks done and the next one fires when its trigger condition matches.

### Step 1 — Welcome from the composer
- **Screen:** Dashboard
- **Where to look:** the **HeroAskPrompt** under the greeting. Eyebrow reads "Ask your library."
- **Trigger:** first time user lands on Dashboard with an empty library
- **Callout copy:** Carrel answers from sources you import. Drop your first PDF in and we will start there.
- **Next:** click the "Import a source" chip below the composer (auto-advance) or the **Library** sidebar item
- **Why this step:** sets the wedge in one line. Tells Maya the next move without lecturing.

### Step 2 — The dropzone is the door
- **Screen:** Library
- **Where to look:** the **Import sources** card in the upper-right of the header. Big dashed outline, "Drop in anything you study from."
- **Trigger:** user arrives in Library with zero documents
- **Callout copy:** Drag any PDFs, slides, or notes here. Anything you study from goes in this box.
- **Next:** auto-advance when the first file is dropped or "Or choose files" is clicked
- **Why this step:** removes the "where do I start" dead space. The dropzone is already the loudest object; we just name it.

### Step 3 — Ingestion is fine, you can keep going
- **Screen:** Library
- **Where to look:** the toast that fires after upload, near the top-right: "Watch progress in Jobs. Ready sources appear in the Library."
- **Trigger:** first successful upload
- **Callout copy:** Carrel parses your file in the background. It will land in a subject card in a few seconds.
- **Next:** auto-dismiss when the document row appears in the grid
- **Why this step:** the only ingestion-anxiety moment. Closes the "did it work" loop.

### Step 4 — Subject cards are auto-grouped
- **Screen:** Library
- **Where to look:** the **SubjectCardGrid** below the header. The new "Cell Biology" card.
- **Trigger:** first document finishes ingesting
- **Callout copy:** Sources auto-group by subject. Click a card to drill in.
- **Next:** click the subject card or "Got it"
- **Why this step:** Maya doesn't know subjects came from filename heuristics. One sentence makes it feel intentional.

### Step 5 — Open a source the way she'll always open one
- **Screen:** Library subject drill-in
- **Where to look:** the document row in the drill-in panel beneath the grid
- **Trigger:** subject card is clicked
- **Callout copy:** Click any source to open the Reader. Citations from Ask will fly back to this same view.
- **Next:** click any document row
- **Why this step:** plants the citation-flight idea before she's even asked anything. Makes the Step 9 click feel earned.

### Step 6 — Highlight to anchor
- **Screen:** Reader (PDF)
- **Where to look:** the PDF body. There is no callout until selection. When she selects text, the **Selection captured** banner appears at the top of the viewer with a **Save anchor** button.
- **Trigger:** user has spent more than 5 seconds on a Reader page without selecting
- **Callout copy:** Highlight a sentence to save it as an Anchor. Anchors become flashcards later.
- **Next:** auto-dismiss the moment text is selected; banner takes over
- **Why this step:** Anchors are invisible until used. Tells her selection is the entry point without forcing her to find a "highlight tool" that doesn't exist.

### Step 7 — Now ask something real
- **Screen:** Dashboard
- **Where to look:** the **HeroAskPrompt** input. Placeholder now reads "What do you want to understand right now?"
- **Trigger:** user returns to Dashboard with at least one ingested source and at least one anchor
- **Callout copy:** Type a real question. Carrel will only answer with what your sources actually support.
- **Next:** auto-advance on form submit
- **Why this step:** the no-fabrication promise lands strongest the first time, before she's seen citations.

### Step 8 — The scope pill keeps the answer honest
- **Screen:** Ask
- **Where to look:** the **ScopePill** in the question card, above the QuestionInput. Small badge labeled with the current scope ("Library" by default).
- **Trigger:** Ask view opens for the first time
- **Callout copy:** Retrieval is bounded to this scope. Tap the pill to ask only one source or one subject.
- **Next:** "Got it" or scope-pill click
- **Why this step:** the scope pill looks decorative until you know it's a knob. Without this, users ask library-wide questions and assume Carrel is bad at narrow ones.

### Step 9 — Citation chips fly
- **Screen:** Ask, after first answer
- **Where to look:** any **CitationChip** beneath a claim card. Small numbered chip like `[1]`.
- **Trigger:** first grounded answer renders
- **Callout copy:** Click `[1]` to jump straight to the passage that grounds this claim.
- **Next:** auto-advance on first chip click; route handler navigates to Reader
- **Why this step:** this is the aha moment. If she clicks one chip, she trusts the system. If she doesn't, she doesn't.

### Step 10 — Save the claim, not just the highlight
- **Screen:** Ask
- **Where to look:** the **Save as anchor** action on the AnswerFeedCard footer (next to **Copy**)
- **Trigger:** user has clicked at least one citation chip and returned to Ask
- **Callout copy:** Like a claim? Save it as an Anchor and Carrel can draft a flashcard from it.
- **Next:** "Got it" or button click
- **Why this step:** bridges Ask and Study. The claim-to-card path is the loop that keeps her coming back.

### Step 11 — Anchors live in the source panel
- **Screen:** Reader, source panel right side
- **Where to look:** the **Anchors** tab in the SourcePanel tab strip
- **Trigger:** user opens Reader after saving at least one Anchor
- **Callout copy:** Your Anchors for this source live here. Click one to draft a card from it.
- **Next:** auto-advance on Anchors-tab click
- **Why this step:** without this, the Anchors she saved feel lost. The tab is unobtrusive on purpose; the coachmark just points.

### Step 12 — The Card Draft Drawer
- **Screen:** Reader, on top of the source panel
- **Where to look:** the **Card Draft Drawer** dialog, specifically the **Save card** button in the action bar
- **Trigger:** drafts have loaded inside the drawer
- **Callout copy:** Pick the strongest draft and save it. It goes straight into your review queue.
- **Next:** "Got it" or Save card click
- **Why this step:** there's no UI hint that the dialog is editable-then-save. One sentence removes the guesswork.

### Step 13 — Plan is where deadlines live
- **Screen:** Plan
- **Where to look:** the **Working toward** rail at the top of the page, specifically the **+ Add** pill in the rail header
- **Trigger:** user navigates to Plan for the first time
- **Callout copy:** Add a deadline you actually have. Carrel will plan study blocks toward it.
- **Next:** auto-advance on "+ Add" click
- **Why this step:** this is the deadline-as-unit-of-work moment, in plain language, exactly once.

### Step 14 — The coach picks a time
- **Screen:** Dashboard
- **Where to look:** the **Best time to study** card (StudyInsertionsCard), the first row's **Add** affordance
- **Trigger:** user has at least one deadline and returns to Dashboard
- **Callout copy:** Carrel found an open block before your deadline. Add it to your calendar with one click.
- **Next:** auto-advance on Add click, or "Got it"
- **Why this step:** ties Library + Plan into a tangible action. This is the surface that proves the loop closed.

### Step 15 — The status chip is your nudge
- **Screen:** Dashboard
- **Where to look:** the **status chips row** above the greeting (the "X cards due now" pill)
- **Trigger:** first time the chip appears (≥1 card due)
- **Callout copy:** When cards are due, the chip lives here. Click it any time you have five minutes.
- **Next:** auto-advance on chip click
- **Why this step:** the chip is the daily re-entry point. If she finds it now, she finds it again tomorrow.

### Step 16 — One review, then we close
- **Screen:** Study
- **Where to look:** the **Reveal the source-grounded answer** primary button on the card
- **Trigger:** user starts a session for the first time
- **Callout copy:** Read the front, think, then reveal. Rate honestly. The scheduler handles the rest.
- **Next:** auto-advance on Reveal click
- **Why this step:** SRS is intimidating. Three sentences make it feel like a normal flashcard.

### Step 17 — Closing the loop
- **Screen:** Dashboard
- **Where to look:** centered toast or inline ribbon under the greeting (no anchor)
- **Trigger:** user has completed Steps 2, 6, 9, 12, 13, 16
- **Callout copy:** You've done the loop: import, ask, anchor, card, plan, review. From now on Carrel just keeps going.
- **Next:** "Got it"
- **Why this step:** names what just happened. Makes the hour feel like progress instead of feature-tasting.

## What we are NOT teaching in v1

These exist and work, but pulling them into the first hour dilutes the loop. Skip them.

- **Concepts** sidebar item and ConceptGraphView. Useful later, mystifying on day one.
- **Search** sidebar item. Library search bar covers the obvious case.
- **Sessions** view (focused study sessions, distinct from Study reviews). Two SRS-shaped surfaces in one hour is one too many.
- **All eight `⌘1`–`⌘8` keyboard shortcuts.** Show shortcuts only when she repeats an action three times.
- **Calendar feed connection** (AddFeedDialog with iCal URL). The deadline rail covers the wedge without it. Reveal the FeedList only when she clicks Plan a second time.
- **Companion bus animations** (the cardAgain / cardGood reactions). Charming, easy to over-explain.
- **Duplicate cleanup banner.** Surfaces only when there are duplicates; it self-explains.
- **NonPdf reader paths** (DOCX, EPUB, XLSX). Same shape as PDF for tutorial purposes.
- **Manage cards view.** She'll find it from Study when she needs it.
- **Dashboard StatStrip + StreakRing + WeakConcepts rail.** Honest data, but premature; let it accrue.

## Implementation notes for the designer

**Primitive.** Build a new `Coachmark` component on top of the existing `Tooltip` primitive in `frontend/src/design-system/primitives/Tooltip/`. Difference from Tooltip: persistent until dismissed, has a small "Got it" caret, supports an arrow pointing at any side, and accepts `anchorRef` plus `placement`. Do not use the modal Dialog primitive — modals lose the "the app is right there" feel.

**One on screen at a time.** A coachmark queue lives in `frontend/src/features/onboarding/`. Steps register their `triggerCondition` and `targetSelector`. The queue renders the first eligible step whose `localStorage` flag is unset and whose anchor element is currently mounted. Re-mounting is fine; don't try to be clever about route changes.

**State.** Per step: `localStorage["carrel.tutorial.step." + id] = "done" | "skipped"`. Plus a master `carrel.tutorial.complete = "true"` after Step 17. The replay button already exists in `AppShell.tsx` — wire it to clear all step keys.

**Dismissal mid-flow.** Every coachmark gets a small "Skip the tour" link in the bottom-right of the bubble (smaller than "Got it"). It sets master complete to true and clears the queue. Do not show a "are you sure" dialog — the cost of a wrong skip is one click on the replay button later.

**Anchor stability.** Steps 6, 9, 12, 14 anchor to elements that mount conditionally (selection banner, citation chip, draft drawer, study insertion row). The queue must observe DOM mutation on the relevant container and only fire when the anchor exists. If the anchor unmounts before the user clicks "Got it," hold the step in `pending` and re-show on next mount.

**Toast vs coachmark.** Step 3 reuses the existing post-upload toast text. Don't add a second bubble on top of it — append a single sentence to the toast body.

**Telemetry.** Each step emits `events.track("tutorial.step_seen", { step_id })` on mount and `tutorial.step_done` on dismissal. Use these to find the step that drops the most users. Step 9 is the one that matters — if she clicks the citation chip, she stays.

**Screenshot pack.** For the designer's first pass, capture: empty Dashboard, empty Library, Library after first upload (subject card visible), Reader with selection banner showing, Ask with grounded answer + chips, Reader Anchors tab, Card Draft Drawer, Plan with empty deadline rail, Plan with deadlines, Dashboard with study insertion row, Dashboard with cards-due chip, Study front, Study reveal. Thirteen screens cover all seventeen steps.
