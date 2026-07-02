> SUPERSEDED 2026-07-02 by the Claude Design handoff (~/Downloads/design_handoff_cachet; applied main d75d409a8: OKLCH neutral + oxblood accent, light/dark). This Docket note is historical.

# Cachet redesign: "The Docket" (2026-07-02)

Ground-up visual reinvention per the operator's redesign brief
(`~/Downloads/cachet-frontend-redesign/`). The engine, wire contract, routes,
and the nine honesty invariants are fixed; everything visual is new. This note
is the design thesis and system of record; the implementation lives in
`cachet.module.css`, `VerifyView.module.css`, `attest.module.css`,
`examine.module.css` (CSS-first: the pure logic modules and component DOM are
untouched, so every honesty behavior and its test lock carries over).

## 1. Thesis

**Cachet is no longer software examining a document at night. It is the filed
instrument itself, in daylight.**

The prior identity ("The Examination") was a dark desk: warm ink, a lamp, a
cinematic mood. A skeptical senior lawyer reads mood as performance. The thing
they trust arrives on bright bond paper with numbered rules, a typewritten
procedural register, and a stamp — the aesthetic of a document that expects to
be FILED, not admired. So the new identity is **pleading paper**: cold bond
ground, iron-gall blue-black ink, a typewriter voice for everything procedural,
a reading serif for the draft under review, and exactly one color in the whole
product — the red pen.

The open-ring mark finally lands on its native ground: on paper, the severed C
reads as a stamp that deliberately declined to complete its impression. The
refusal treatment is built from it.

## 2. The system

### Palette (all AA-checked against the locked contrast test)

| Token | Value | Role |
|---|---|---|
| paper / surface-0 | `#f4f3ee` | the page ground (cold bond, not cream) |
| sheet / surface-1 | `#fbfaf7` | the raised document sheet |
| surface-2 | `#ebe9e2` | inset wells, source passages |
| ink-1 / text-primary | `#1b1e25` | iron-gall blue-black; 15.0:1 on paper |
| ink-2 / text-secondary | `#454b57` | secondary; 8.0:1 |
| ink-3 / text-tertiary | `#5f6572` | procedural metadata; 5.2:1 (4.8:1 on surface-2) |
| flag | `#a3242e` | THE red pen. Deterministic flags only. 6.6:1 |
| hair / hair-soft | `rgba(27,30,37,.16/.08)` | the ruled line |

No green anywhere (derived from invariant 1: affirmation invites over-trust —
this survives from the old identity because it derives from the invariant, not
the skin). No glass: floating chrome becomes opaque paper with a hard rule and
a shallow document shadow — an instrument does not refract.

### Typography — three voices, three jobs

1. **Procedure — the typewriter.** System mono (`--font-mono`), 11–12px,
   uppercase, letterspaced. Nav, check labels, hashes, timestamps, buttons,
   badges, coverage notes. The docket-stamp voice; it cannot be mistaken for
   the document.
2. **The document — the reading serif.** Charter (`--font-serif-body`) carries
   the draft read-back and all long-form reading at 16–17px/1.6.
3. **The caption — the engraved display.** Libre Caslon Display
   (`--font-serif`, unchanged binding — test-pinned) for room titles only,
   like a case caption.

### The four tiers — different KINDS of thing (invariant 4)

| Tier | Treatment | Semiotics |
|---|---|---|
| **pass** | set type, unmarked; findings row in plain ink prose | the absence of a problem IS the signal (inv. 1) |
| **flag** | the red pen: `#a3242e` left edge, red badge, and the exact altered token marked (inv. 6) | a stamped deterministic accusation |
| **assistive** | pencil: italic, graphite ink-2, dotted underline, "for your review" | a hand annotation, physically lighter than ink |
| **refusal** | **the registrar's stamp**: reversed block (ink ground, paper small-caps mono), the open-ring glyph, double-rule left edge — the heaviest typographic object on the page, zero chroma | a deliberate withholding with more presence than a pass (inv. 2) |

### Layout

The chrome is the instrument's margin: the left rail restyles as pleading
paper's **ruled margin** (double rule on its right edge), carrying the mark,
the room glyphs, and — because provenance is a feature (inv. 8) — the
`ON DEVICE` attestation in the rail foot, always visible. Content rooms are
the sheet: a bounded reading column (72ch), generous top margin, headers set
as case captions.

### Motion

Near-still, unchanged discipline (no keyframes in the verify surface — test-
locked). Checks ink in with 160–200ms opacity/rise transitions; the one
signature moment is **the press**: sealing scales the exhibit 0.985→1 with a
settle, like a stamp impression. Reduced-motion clamps everything.

## 3. Invariant mapping (the rationale, per the brief's item 4)

1. verified quiet → pass tier has literally no mark and no accent.
2. refusal is the hero → the only reversed-ink object in the product.
3. three states only → unchanged logic modules; no meter anywhere.
4. deterministic ≠ assistive → stamp/red-pen vs pencil register.
5. fail-closed streaming → untouched SSE machine; skeletons in mono
   procedural voice so "checking" never resembles a settled verdict.
6. exact token marked → flagged_spans keep the red-pen underline treatment,
   reserved to flags.
7. exhibit reads filed → bond sheet, mono hashes, dated caption, equal-weight
   refusal rows.
8. on-device shown → rail-foot attestation line + exhibit statement.
9. voice → unchanged strings (component DOM untouched this pass).

## 4. The case against this direction, answered

**Too quiet for software?** The product's one job is to be believed. Loud
verdicts are the failure mode the invariants ban; the Docket spends its whole
contrast budget on the two things that matter — the red pen and the stamp.
**Too literal (pleading-paper cosplay)?** The register is borrowed, not the
props: no skeuomorphic texture, no fake letterhead, no serif-everything. Mono
carries procedure because typewritten procedure is the genre's native voice,
not because it is retro.
**Light theme fatigue at night?** The prior dark identity is preserved in git;
a dark instrument variant is a token-swap away if operators demand it. Bond
paper ships first because the exhibit, printed or screen-shared to a court,
must look like what it claims to be.
