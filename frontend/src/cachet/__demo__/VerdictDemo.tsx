/**
 * Dev-only fixture harness (cachet.html?demo=verdicts).
 *
 * Renders the settled document-as-hero surface (WorkspaceMargin) against a
 * deterministic fixture so the signature verdict moments can be built and
 * screenshotted without the backend (or coaxing the live LLM into a refusal):
 *
 *   - a fabricated citation  -> the oxblood flag (SM-V3 The Catch target)
 *   - a could-not-check claim -> the ink-bracket refusal (SM-V5 target)
 *   - a real case cited wrong -> the assistive pencil query
 *   - a clean claim           -> unmarked (the pass)
 *
 * Not shipped in the real flow; gated behind the query param in CachetApp.
 */
import type { VerifyClaimVerdict } from "@/services/api/endpoints";
import { navigateTo } from "@/app/shell/useAppShell";
import { WorkspaceMargin } from "@/features/verify/WorkspaceMargin";
// The verify token layer (paper surfaces + the scoped --verify-flag oxblood).
// The real VerifyView root provides it; the demo must too, or scoped tokens
// (the oxblood strike) resolve to nothing.
import verifyStyles from "@/features/verify/VerifyView.module.css";

const CLAIMS: { text: string; build: (i: number, s: number, e: number) => VerifyClaimVerdict }[] = [
  {
    text:
      "As the court held in Marbury v. Wilson, 999 U.S. 412, the disclaimer was controlling on its face.",
    build: (claim_index, s, e) =>
      ({
        claim_index,
        claim_text:
          "As the court held in Marbury v. Wilson, 999 U.S. 412, the disclaimer was controlling on its face.",
        verdict: "verified",
        citations: ["999 U.S. 412"],
        unsupported_reason: null,
        case_verdicts: [
          {
            ok: true,
            verdicts: [
              {
                citation: "999 U.S. 412",
                status: 404,
                exists: false,
                case_name: null
              }
            ]
          }
        ],
        placement: { placed: true, method: "exact", char_start: s, char_end: e }
      }) as unknown as VerifyClaimVerdict
  },
  {
    text: "Plaintiff's implied-warranty theory fails as a matter of law.",
    build: (claim_index, s, e) =>
      ({
        claim_index,
        claim_text: "Plaintiff's implied-warranty theory fails as a matter of law.",
        verdict: "unknown",
        citations: [],
        unsupported_reason: null,
        case_verdicts: [],
        placement: { placed: true, method: "exact", char_start: s, char_end: e }
      }) as unknown as VerifyClaimVerdict
  },
  {
    text:
      "The opinion in Lochner v. New York, 198 U.S. 45, makes such fee schedules categorically permissible.",
    build: (claim_index, s, e) =>
      ({
        claim_index,
        claim_text:
          "The opinion in Lochner v. New York, 198 U.S. 45, makes such fee schedules categorically permissible.",
        verdict: "verified",
        citations: ["198 U.S. 45"],
        unsupported_reason: null,
        case_verdicts: [
          {
            ok: true,
            verdicts: [
              {
                citation: "198 U.S. 45",
                status: 200,
                exists: true,
                case_name: "Lochner v. New York",
                holding_match: false,
                holding_concern:
                  "Lochner concerns liberty of contract under the Due Process Clause, not fee schedules."
              }
            ]
          }
        ],
        placement: { placed: true, method: "exact", char_start: s, char_end: e }
      }) as unknown as VerifyClaimVerdict
  },
  {
    text: "Each count premised on the implied warranty must therefore be dismissed.",
    build: (claim_index, s, e) =>
      ({
        claim_index,
        claim_text: "Each count premised on the implied warranty must therefore be dismissed.",
        verdict: "verified",
        citations: [],
        unsupported_reason: null,
        case_verdicts: [],
        placement: { placed: true, method: "exact", char_start: s, char_end: e }
      }) as unknown as VerifyClaimVerdict
  }
];

const DRAFT = CLAIMS.map((c) => c.text).join(" ");

const CARDS: VerifyClaimVerdict[] = CLAIMS.map((c, i) => {
  const start = DRAFT.indexOf(c.text);
  return c.build(i, start, start + c.text.length);
});

export function VerdictDemo() {
  // Match VerifyView's real wrapper: .root is the bounded, centered 920px page
  // (max-width + margin auto + padding) and .verifyScope is the paper-sheet
  // palette + shadow. Without .root the sheet spans the full viewport and the
  // content strands in the middle with the sheet's bottom shadow reading as a
  // full-width divider line. The fixture must frame itself exactly as the
  // product does, or it lies about the layout.
  return (
    <div className={[verifyStyles.root, verifyStyles.verifyScope].join(" ")}>
      <WorkspaceMargin
        draftText={DRAFT}
        cards={CARDS}
        unattributedQuotes={[]}
        examined={null}
        onExamine={() => {}}
        onResolve={() => navigateTo("/sources")}
      />
    </div>
  );
}
