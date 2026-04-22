import type { TutorQueryResponse } from "@/services/api/endpoints";

type TutorClaimRecord = NonNullable<TutorQueryResponse["claims"]>[number];
export type CitationRecord = NonNullable<TutorClaimRecord["citations"]>[number];

export interface ClaimRecord extends Omit<TutorClaimRecord, "citations"> {
  citations: CitationRecord[];
}

export interface GroundedAnswerEnvelope
  extends Omit<
    TutorQueryResponse,
    | "actions"
    | "citations"
    | "claims"
    | "misconceptions"
    | "scaffold_steps"
    | "scaffolds"
    | "source_cards"
    | "unsupported_spans"
  > {
  actions: NonNullable<TutorQueryResponse["actions"]>;
  citations: CitationRecord[];
  claims: ClaimRecord[];
  misconceptions: string[];
  scaffold_steps: string[];
  scaffolds: string[];
  source_cards: CitationRecord[];
  unsupported_spans: string[];
}

export function normalizeGroundedAnswer(raw: TutorQueryResponse): GroundedAnswerEnvelope {
  return {
    ...raw,
    actions: raw.actions ?? [],
    citations: raw.citations ?? [],
    claims: (raw.claims ?? []).map((claim) => ({
      ...claim,
      citations: claim.citations ?? []
    })),
    misconceptions: raw.misconceptions ?? [],
    scaffold_steps: raw.scaffold_steps ?? [],
    scaffolds: raw.scaffolds ?? [],
    source_cards: raw.source_cards ?? [],
    unsupported_spans: raw.unsupported_spans ?? []
  };
}
