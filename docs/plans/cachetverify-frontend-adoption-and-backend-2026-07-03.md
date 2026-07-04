# cachetverify.com — new frontend adoption + backend build (long-horizon plan)

> Date: 2026-07-03. This plan is for the **cachetverify.com website only**.
> The Carrel/Codex app (`frontend/src/cachet/`, macOS shell, main app) is OFF-LIMITS
> and is not touched anywhere in this plan.
> Supersedes the ad hoc `2026-07-02-cachet-handoff-build-decision.md`.

## 0. Scope lock

- **In scope:** the marketing + product *website* at cachetverify.com. Its current
  frontend (`cachet-landing/`, a single-page static site on Vercel) is **eliminated** and
  replaced by the new package (the zip: 10 `.dc.html` pages + `support.js`, per
  `Cachet - Build Package.md`). Then a production backend is built for that website.
- **Off-limits (do not touch):** the Carrel app. `frontend/src/cachet/`, the macOS shell,
  `main.py`/`routes/`/`services/` as the *app's* backend. We do NOT fold the website into
  the app and we do NOT modify the app to serve it.
- **Shared, read-only:** the `cachet_verify` deterministic kernel is reused as a versioned
  dependency (see §3.Q3). Depending on it is not "touching the app."

## 1. Grounding (verified in repo)

- **Current website = `cachet-landing/`.** Static HTML/CSS + one vanilla JS, self-hosted
  fonts, no build, deployed to Vercel with `Root Directory: cachet-landing`, domain
  `cachetverify.com`. This is what gets replaced.
- **New website = the zip.** 10 `.dc.html` pages + `support.js` (a ~1,658-LOC "dc-runtime"
  rendering via CDN `window.React`). Inline styles, no build, client-only `localStorage`,
  **zero network calls today** — every verdict is mock.
- **Kernel = `cachet_verify/`.** Frozen-contract deterministic engine (ADR-0015):
  `verify(claim, sources) -> verified | altered | could_not_check`. Wraps `services.legal`
  behind an additive-only contract; explicitly designed as the strangler-fig seed other
  surfaces migrate onto.

## 2. The load-bearing law: three surfaces, plane separation (write as ADR-0017)

The product promise is "runs on your device, zero data egress, provable." A hosted public
website cannot honor that for real user documents — the moment a document reaches the server
it has egressed. So:

- **Surface 1 — cachetverify.com (hosted, public).** Marketing, Login/PIN, Onboarding, Feed,
  Demo (over sample data), and the public Certificate viewer. **No real user-document
  verification happens here.**
- **Surface 2 — Website backend (new, own service).** Account plane: auth/session,
  certificate persistence + public share URLs, validity feed + email, teams/vaults, access
  capture. **Stores attestations (verdicts, receipts, claim spans, counts, IDs) — never
  document bodies.** Imports the kernel only to run the public *demo* on sample content.
- **Surface 3 — On-device verification (already exists, OFF-LIMITS).** Runs `cachet_verify`
  on the real document locally, produces the sealed certificate, and uploads the
  *attestation* (not the document) to Surface 2.

**Hard rule, enforced by test:** no Surface-2 store or route may persist or transmit document
body text. A `test_website_zero_content` suite is the guard (mirrors the existing
`test_cachet_verify_zero_egress` discipline).

## 3. Vulcan verdicts (the three judgment calls)

- **Q1 (hosted site vs on-device engine):** Reconcile only via §2 plane separation. Real
  verification is on-device; the site is marketing + account + public artifact + sample demo.
  *Principle: the zero-egress claim is a physical boundary, not a policy; Hyrum's Law makes a
  public "provable" claim load-bearing for everyone.*
- **Q2 (`.dc.html`/`support.js` as a long-term foundation):** Keep it (mandate stands). Ship
  the marketing pages on it, possibly forever. Pay down its one real tax now: **self-host
  React** (kill the CDN dep) and **extract the shared nav/brand into one component** (kill the
  10-file change amplification). Migrate only the *interactive* app pages (Feed, Journal,
  Onboarding, Verify, Profile) to a real framework later, page-by-page, **only when real
  state/auth/network pain justifies it** — never preemptively. *Principle: prefer boring and
  proven; let the system evolve (Gall's Law); name the future fork, don't force it.*
- **Q3 (reuse the kernel vs fork):** Reuse `cachet_verify` as a shared, versioned dependency;
  never fork the verdict logic. Extract `cachet_verify` + the deterministic `services.legal`
  parts into a standalone package both the app and the website backend depend on. *Principle:
  single source of truth for the honesty contract; depend on a stable abstraction.*

## 4. What the backend IS and IS NOT

**IS:** an account + attestation-storage + content plane, plus a clean handoff to the
on-device engine. Concretely: identity/PIN auth, certificate store + public share, validity
feed + email cadences, teams/vaults, access/waitlist capture.

**IS NOT:** a "verify my uploaded document" cloud service. That would break the promise.

Each localStorage key in the Build Package is the exact spec for a backend endpoint:

| localStorage key (today) | Backend service (new) | Stores document content? |
|---|---|---|
| `cachet_login_email`, `cachet_login_verified` | Identity + session | No |
| `cachet_prefs` | Feed preferences | No |
| `cachet_journal_*` | Draft persistence (stays LOCAL — do not server-store bodies) | Local only |
| `cachet_journal_sources` | Sources list (stays LOCAL) | Local only |
| certificate (static today) | Certificate store + public `GET /c/{id}` | No (attestation only) |
| `cachet_demo_unlocked` | Access/demo capture | No |

## 5. Staged roadmap (each stage independently shippable)

### Stage 0 — Adopt the new frontend + kill the old (0.5 wk)
- Replace the contents of `cachet-landing/` with the new package (10 `.dc.html` + `support.js`
  + `uploads/`). Update `vercel.json` for the multi-page routing (clean URLs per page).
- Self-host React/ReactDOM (pin the version; drop the CDN `<script>`). Extract the shared nav
  + brand marquee into one `support.js` component.
- Ship to cachetverify.com as static (no backend yet — it still runs on `localStorage`,
  exactly as designed). **This alone gives a live, upgraded marketing site today.**
- Write ADR-0017 (three-surface plane model, §2).
- Exit: site live on Vercel; Lighthouse pass; reduced-motion path verified; old single-page
  site gone.

### Stage 1 — Extract the shared kernel package (0.5 wk)
- Extract `cachet_verify` + deterministic `services.legal` into a standalone, versioned,
  pip-installable package. The app keeps importing it unchanged (no app edits beyond the
  import path if even that). The website backend depends on it.
- Exit: package builds; existing `test_cachet_verify_*` suites pass against the extracted
  package; app still green (verified, not modified in behavior).

### Stage 2 — Website backend skeleton + access capture (0.5 wk)
- New service (own repo/deploy — see §6). FastAPI, its own DB. First endpoints: access/
  waitlist capture (the Site access form) and the demo gate. Content-free.
- Wire the `.dc.html` access form + demo gate to real endpoints (progressive enhancement:
  `localStorage` remains the fallback).
- Exit: `test_website_zero_content` scaffold green; access form persists server-side.

### Stage 3 — Identity + PIN (1 wk)
- Email -> PIN issue -> PIN verify -> session token. Password path with the live checklist
  (9 chars, upper, lower, number). Social buttons stub to the same session mint (real OAuth
  in Stage 7).
- Replace the `cachet_login_*` gates.
- Exit: auth unit tests; zero-content assertion on the session store.

### Stage 4 — Certificate service + public share (1.5 wk) — the growth loop
- Persist a sealed certificate (verdicts, receipts, counts, claim spans, source *count*,
  timestamp, ID — never bodies). Mint public share URLs. The `Certificate.dc.html` page
  becomes a real hydrated public route (`GET /c/{id}`), unauthenticated.
- On-device surface (off-limits app) uploads its attestation here via a documented API
  contract. We define the contract; we do not modify the app.
- Exit: stored certificate provably contains no source text (grep-assert test); public route
  works signed-out; honest error path ("could not load... nothing was sent anywhere").

### Stage 5 — Onboarding + Feed + email (1 wk)
- `cachet_prefs` -> preference store. Three-column feed (peer pieces, "what you need to know",
  most-checked), personalized from prefs, defaults when empty. Everything not-yet-live labeled
  mock per the voice rules. The three email cadences (access-granted, validity digest,
  certificate-ready), all content-free.
- Exit: feed personalizes; no document content in any feed row or email payload.

### Stage 6 — Teams / vaults (gated on demand) (1.5 wk)
- Shared vault + admin for the Firm tier; regulated/enterprise procurement story. Start only
  when a real buyer signal justifies it.

### Stage 7 — Real OAuth (gated on demand) (1 wk)
- Real Google/LinkedIn/Apple. Until then, the buttons mint a session like the email path.

## 6. Where the website + backend live (recommendation)

Recommend the **new website (frontend + its backend) becomes its own repo/deployable**,
mirroring how `cachet-companion` is separate. Reason: it keeps the app repo untouched (your
hard constraint), gives the website its own deploy cadence, and depends on the shared kernel
package (Stage 1) rather than the app's internals. Interim: Stage 0 can replace
`cachet-landing/` in-place for the fastest live ship; the backend service is separate from day
one regardless. Confirm this repo split before Stage 2.

## 7. Verify discipline (website, separate from the app's chain)
- `test_website_zero_content` (the guard: no Surface-2 store/route persists or transmits
  document body) — non-negotiable, added in Stage 2.
- `test_website_auth`, `test_website_certificates`, `test_website_feed` as those stages land.
- Static site: Lighthouse + a reduced-motion smoke check in CI.

## 8. Sequencing against the real constraint
Mission lock is booked validation interviews, not shipped infrastructure. Ruthless cut:
- **Do now, cheap, high-leverage:** Stage 0 (live upgraded marketing site) + Stage 1 (kernel
  extraction, unblocks everything, no app risk).
- **Do next if a demo needs it:** Stage 2 (access capture makes the "Request access" CTA real).
- **Hold behind a demand signal:** Stages 3-7. Auth, persisted certificates, feed, teams are
  real product infrastructure that earns its keep only once demand is proven.

## 9. Risks
- **Egress-promise regression** — any Surface-2 leak of document content voids the core claim.
  Guard: `test_website_zero_content`.
- **Two React runtimes / bespoke framework tax** — keep `support.js` self-contained; self-host
  React; extract shared components; migrate interactive pages only on real pain.
- **Kernel drift** — never fork the verdict logic; one shared package is the source of truth.
- **Scope bleed into the app** — the app is off-limits; the only shared artifact is the
  extracted kernel package, consumed read-only.
