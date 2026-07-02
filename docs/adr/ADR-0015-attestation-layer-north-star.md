# ADR-0015: Cachet's north star is the independent attestation layer

- Status: Accepted (operator directive, 2026-07-02)
- Date: 2026-07-02
- References:
  - Council transcripts + verdict: `.forge/debates/cachet-universal-verification-layer/`
  - Blueprint: `docs/notes/2026-07-02-cachet-attestation-layer-blueprint.md`
  - North-star doc: `~/Desktop/Cachet-DataRoom/cachet-north-star.md` (reset 2026-07-02;
    2026-06-30 version archived beside it)
  - [ADR-0014] (kernel-with-surfaces, Proposed, on `cachet/foundry-verify-hardening-2026-07-01`),
    [ADR-0008](ADR-0008-v2-pivot-validation-first-sequencing.md)

## Context

The founder's thesis: as AI output normalizes, trust rises, and hallucination damage
scales — so the world needs a verification layer riding alongside AI, as big as AI, a
must-have for every user. A five-seat council (Harvey / Bellwether / Vulcan-read /
adversary / synthesizer) was convened on 2026-07-02 to design that vision and the case
against it.

The council converged, across four independent seats, on a directional correction:
verification becomes universal *behavior*, not a universal *customer*. Consumers verify
for free; platform owners bundle proven safety layers at $0; the kernel's own honesty
(`could_not_check` on unanchored input) makes an ambient consumer companion useless most
of the time by design. Willingness to pay exists where damage is attributable, personal,
and liability-bearing. The billion-dollar version is compulsion-gated: the
"auditor-independence moment" (a court rule, bar opinion, or carrier policy refusing AI
vendors' self-verification and requiring an independent verifier).

## Decision

The operator ratifies the council's shape as the north star:

**Cachet is the independent attestation layer for liability-bearing, document-grounded
AI output — one signed, on-device, zero-egress deterministic attestation daemon with a
curl-able 3-state verdict contract, sold first as legal pre-flight, expanded only via
domain packs structurally incapable of pronouncing green.**

Build order (binding):
1. **Parity test first** (council revisit-trigger #3): the domain-agnostic residue
   (quote, money, date, duration, percent) against non-legal fabrications. Its result
   sizes the kernel bet.
2. **Kernel extraction** (`cachet-verify`) behind the executable honesty contract:
   frozen verdict algebra + `combine()` + closed comparator set + mandatory provenance;
   parity corpus as a CI conformance gate in both repos; the companion's vendored fork
   deleted strangler-fig.
3. **The loopback daemon** as the single embedding target (zero-egress is a process
   property; provable by socket ban + packet capture). Wire contract is the forever-API:
   schema-first, additive-only.
4. **Surfaces as adapters** over the daemon.

Do-not-build until a trigger fires: the ambient consumer companion as a growth motion,
second surfaces, the third-party plugin loader, new OS surfaces, the platform narrative.

GTM: sell the demand side (the certificate must be demandable by a third party — judges'
standing orders, firm GCs, outside-counsel guidelines, carriers); lead with independence
+ attribution; distribution via licensing into tools the buyer already has open. The
Lebanon round's pre-registered gate stands and is founder work in parallel.

## Consequences

- The 3-state verdict shape + provenance freezes now as the forever-API.
- New domains are evidence-provider plugins; only the kernel pronounces verdicts; the
  semantic-assessor return type has no `verified` variant (ADR-0013 generalized).
- The honest ceiling is stated, not hidden: a lying evidence root can deceive the kernel;
  every green is therefore scoped, attributable, and policy-excludable.
- Six testable revisit triggers are recorded in the blueprint; the verdict reverses on
  trigger #1 (compulsion) and shrinks on trigger #3 (trivial parity result).
- Dissent recorded: no seat argued the pure pro-thesis case; the operator may convene a
  designated-advocate round at any time without violating this ADR.
