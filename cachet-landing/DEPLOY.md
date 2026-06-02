# Deploying cachetverify.com

The live landing page is the static site in this directory (`cachet-landing/`):
plain HTML + CSS + one vanilla JS file, self-hosted fonts, no build step. Host:
Vercel (static). Headers, clean URLs, and caching are in `vercel.json`.

## What is already wired (in this repo)
- Paper/ink/oxblood brand re-skin, slowed motion, logo draw, hero image plate.
- Favicons + Apple touch icon + OG/Twitter meta, from `assets/brand/web/`.
- "Request access" points at the live signal form (opens in a new tab).
- "See a sample report" points at the in-page ledger (`#proof`), not the old archive.
- Vercel Web Analytics tag (cookieless; activates once on Vercel).
- `robots.txt`, `sitemap.xml`, `vercel.json`, canonical URL.

## 1. Create the Vercel project
The Vercel CLI is not installed on the build machine, so use the dashboard (or
`npm i -g vercel` then `vercel`, which will prompt you to log in).

Dashboard: New Project -> import this Git repo, then:
- **Root Directory:** `cachet-landing`
- **Framework Preset:** Other
- **Build Command:** (empty)
- **Output Directory:** `.`

## 2. Add the domain
Project -> Settings -> Domains: add `cachetverify.com` and `www.cachetverify.com`.
Set the apex as primary; Vercel redirects `www` -> apex automatically.

## 3. DNS (at the registrar)
| Type  | Name  | Value                  |
|-------|-------|------------------------|
| A     | `@`   | `76.76.21.21`          |
| CNAME | `www` | `cname.vercel-dns.com` |

SSL (Let's Encrypt) provisions automatically once DNS resolves.

## 4. Turn on analytics
Project -> Settings -> Analytics -> enable Web Analytics. The tag is already in
`index.html`; nothing else to add.

## 5. Confirm + finish (small)
- **Form URL / channel:** the CTA points at
  `/forms/d/e/1FAIpQLSdl_9xDwCUbzguWHUDgsT6lbwJXuR8Sgfg4SgTl-UU9DtiYkg/viewform`.
  Confirm that is the live form. To attribute site traffic, add a `website` value
  to the form's channel codebook (currently `warm | sanction | directory |
  community`) and append `?usp=pp_url&entry.107530061=website` to the CTA href.
- **OG card (nice-to-have):** `og:image` currently uses the square
  `assets/brand/web/icon-512.png`. A proper 1200x630 card (paper + the
  `cachet-lockup.svg` + the tagline) will preview better when shared. Replace the
  `og:image` / `twitter:image` URLs and switch `twitter:card` to
  `summary_large_image` once it exists.

## 6. Verify the deploy
Re-run the acceptance checklist in `BUILD-SPEC.md` §13 against the live URL: touch
targets >=44px, no color emoji, curly apostrophes, AA contrast (now on paper),
reduced-motion, no-JS, fonts self-hosted, LCP < 1.5s / CLS < 0.1, slop scan.

## Housekeeping (does not affect the deploy)
`docs/marketing/landing-page.html` is the stale pre-pivot Carrel student page. It
is outside the deploy root, so it does not ship, but archive or delete it so
`cachet-landing/` is unambiguously the one source of truth.
