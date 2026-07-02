# Cachet: the attestation-layer blueprint (council verdict, 2026-07-02)

Five-seat council (Harvey, Bellwether, Vulcan-read, adversary, synthesizer) on the
founder's thesis: "as AI normalizes, trust rises, hallucination damage scales; Cachet
should become the universal verification layer, must-have for every user, as big as AI."
Full seat transcripts + verdict: `.forge/debates/cachet-universal-verification-layer/`.

## The ruling in one paragraph

The thesis is half right, and the half that is wrong is "for every user." The wave is
real (verification becomes universal BEHAVIOR) but the customer is not universal:
consumers verify for free and platforms bundle safety layers at $0 the moment they go
universal. What survives every seat is a sharper company: **Cachet is the independent
attestation layer for liability-bearing, document-grounded AI output — where independence
is compulsory or the incumbent architecturally cannot go.** The billion-dollar version is
not consumer adoption; it is compulsion: the "auditor-independence moment," when a court
rule, bar opinion, or malpractice carrier formally refuses AI vendors' self-verification
and requires an independent verifier. The 2026 record (courts sanctioning filings prepared
WITH CoCounsel/Westlaw Precision; Stanford RegLab's 17–33% hallucination findings against
"hallucination-free" marketing) is exactly the pressure that produces that rule.

## What Cachet should BE BUILT LIKE (the build directive)

One signed, on-device, zero-egress **deterministic attestation daemon** with a curl-able
3-state verdict contract (`verified | altered | could_not_check` + mandatory provenance),
sold first as legal pre-flight, expanded only via domain packs that are structurally
incapable of pronouncing green.

- **Kernel:** extract `cachet-verify` behind the executable honesty contract (parity
  corpus + verdict schema + `combine()`), per ADR-0014. Parity corpus becomes a CI
  conformance gate in both repos; the companion's vendored fork dies. The verdict wire
  shape freezes forever now (3-state + provenance, additive-only).
- **Plugin boundary (internal seam only, no loader yet):** plugins provide claim
  structure and evidence; ONLY the kernel pronounces verdicts. Anchor extractors are pure
  functions with namespaced types bound to kernel-owned comparators (cannot mint a
  green). Corpus adapters return evidence + provenance + SHA-256 attestation; the kernel
  compares. Semantic assessors' return type has no verified variant (propose/dispose,
  ADR-0013 generalized). Honest ceiling stated: a lying evidence root can still deceive —
  every green is therefore scoped, attributable, and policy-excludable.
- **Packaging:** local loopback daemon, not a native lib (zero-egress is a PROCESS
  property, provable by socket ban + packet capture), not WASM yet (rewrite burns the
  hardened false-accusation fixes; legitimate second target). Every future surface — IDE,
  CI gate, OS service, extension — is "POST claim+sources to 127.0.0.1."
- **The certificate is the product's demand side:** the sealed SHA-256 brief must be
  DEMANDABLE by a third party. Sell to the people who ASK for it — judges' standing
  orders, firm GCs, outside-counsel guidelines, carriers offering premium credits. The
  reflex ("where's the Cachet cert?") is institutional, not UX.
- **Expansion ladder (only after the wedge gate clears):** tax practitioners first
  (IRC 6694 / Circular 230 — "substantial authority" is literally citation-grounding;
  kernel changes ~nothing), then audit/financial reporting (PCAOB AS 1105 traceable-
  evidence duty; wedge-2 shape), clinical documentation last (biggest TAM, worst kernel
  fit, EHR-locked).
- **Distribution:** license the kernel into tools the buyer already has open (Word/
  Outlook add-in, iManage/Relativity), plus direct regulated-buyer sales. Never bet on
  browser/OS/AI-vendor channels — they bundle, they don't distribute.

## Do-not-build list (until triggers fire)

Ambient consumer companion as a growth motion; second surfaces; the plugin loader; new
OS surfaces; the platform narrative. The Grammarly analogy failed the transfer test
(value-frequency inverted: constant-small builds habits, rare-catastrophic is insurance
economics; Grammarly itself fled the category via the Superhuman pivot).

## Convergent findings (4 independent seats, same conclusions)

1. Universal consumer layer: wrong target (4/4 seats).
2. The 3-state honest-refusal kernel is real, rare, worth protecting (4/4, incl. the
   adversary's sole concession).
3. Distribution decides it, against Cachet-owned-universal (3 seats).
4. Willingness-to-pay exists only where damage is attributable, personal, liability-
   bearing (3 seats).
5. The 2/8 Lebanon validation state outranks every pattern argument: the next unit of
   founder work is calls, not code (3 seats).

## Revisit triggers (testable)

1. **Flips to the full thesis:** any court rule / bar opinion / carrier policy requiring
   INDEPENDENT verification and refusing vendor self-check. Watch for it; it is the
   category's IPO moment.
2. **Unlocks the extraction budget:** Wedge 2 clears its pre-registered gate.
3. **Shrinks the kernel bet (RUN THIS WEEK, cheapest test):** run the parity corpus + a
   non-legal draft through the kernel with legal packs unplugged. If the domain-agnostic
   residue (quote/money/date/duration/percent) catches only a trivial fraction of real
   non-legal fabrications, the "universal kernel" is a family of domain products wearing
   a shared library, and the 90 days belong to the legal pack.
4. **Kills wedge-1:** KeyCite-integrated cite-check demonstrably ends sanctions among
   Westlaw users (only the no-cloud wedge survives).
5. **Collapses the on-device moat's necessity:** buyers accept "signed zero-retention" —
   then server-side inside the buyer's DPA beats the Apple-Silicon tax.

## Recorded dissent

- Adversary's concession (the pro-thesis line that survived): the domain-agnostic kernel
  + honest 3-state refusal "is a real and rare discipline... expansion to adjacent
  verticals is real optionality, not vaporware."
- Vulcan's conditional: even the kernel extraction is gated on trigger #3 coming back
  positive.
- Synthesizer's process flag: no seat argued the PURE pro-thesis case; the founder may
  legitimately request a second round with a designated advocate before treating this
  as binding.
