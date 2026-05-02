import { toast } from "@/design-system";

import { copyAskCardText, saveCitationAnchor } from "../anchorDrafts";
import type { CitationRecord, ClaimRecord } from "../types";
import { AnswerFeedCard } from "./AnswerFeedCard";
import { CitationChip } from "./CitationChip";
import styles from "../AskView.module.css";

interface ClaimListProps {
  claims: ClaimRecord[];
  onCitationClick?: (citation: CitationRecord) => void;
}

function normalizedText(value: string): string {
  return value.replace(/[^a-z0-9\s]/gi, "").replace(/\s+/g, " ").trim().toLowerCase();
}

function supportTextForClaim(claim: ClaimRecord): string {
  const firstCitation = claim.citations[0];
  const candidate = (firstCitation?.snippet ?? firstCitation?.content ?? "").trim();
  const claimText = normalizedText(claim.text);
  const candidateText = normalizedText(candidate);
  if (
    candidate &&
    candidateText !== claimText &&
    !candidateText.includes(claimText) &&
    !claimText.includes(candidateText)
  ) {
    return candidate;
  }
  if (firstCitation?.document_name) {
    return `Supporting passage from ${firstCitation.document_name}${firstCitation.page_num ? ` on page ${firstCitation.page_num}` : ""}.`;
  }
  return "Supporting passage from your source library.";
}

function sourceLocationFor(citation: CitationRecord): string {
  return [
    citation.document_name ?? citation.document_id ?? "Source",
    citation.page_num ? `p.${citation.page_num}` : null,
    citation.chunk_id ? `chunk ${citation.chunk_id}` : null
  ]
    .filter(Boolean)
    .join(" · ");
}

export function ClaimList({ claims, onCitationClick }: ClaimListProps) {
  // Citations are indexed globally across the answer, not per-claim, so the
  // `[1]` `[2]` `[3]` in chip labels matches what the user scans visually.
  let runningIndex = 0;
  return (
    <div className={styles.claimList}>
      {claims.map((claim, index) => {
        const claimDelay = 80 + index * 60;
        const citationDelay = claimDelay + 120;
        const firstCitation = claim.citations[0];

        return (
          <AnswerFeedCard
            actions={[
              {
                label: "Copy",
                onClick: () => {
                  void copyAskCardText(claim.text)
                    .then(() => {
                      toast.success("Copied claim", "The claim text is on your clipboard.");
                    })
                    .catch(() => {
                      toast.error("Copy failed", "Clipboard access is unavailable in this context.");
                    });
                }
              },
              {
                label: "Save as anchor",
                onClick: () => {
                  try {
                    void saveCitationAnchor({
                      claimText: claim.text,
                      quoteText: supportTextForClaim(claim),
                      sourceKind: "claim",
                      citation: firstCitation
                    })
                      .then(() => {
                        toast.success("Anchor saved", firstCitation?.document_name ?? "Saved from this answer card.");
                      })
                      .catch(() => {
                        toast.error("Save failed", "Could not write this anchor.");
                      });
                  } catch {
                    toast.error("Save failed", "Could not write this anchor.");
                  }
                }
              }
            ]}
            body={supportTextForClaim(claim)}
            delayMs={claimDelay}
            evidence={
              <div className={styles.claimEvidence}>
                {claim.citations.length > 0 ? (
                  <div className={styles.citationRow}>
                    {claim.citations.map((citation) => {
                      runningIndex += 1;
                      return (
                        <CitationChip
                          citation={citation}
                          index={runningIndex}
                          delayMs={citationDelay}
                          key={`${claim.text}-${citation.chunk_id}`}
                          onClick={onCitationClick}
                        />
                      );
                    })}
                  </div>
                ) : null}
                {claim.citations.length > 0 ? (
                  <div className={styles.feedCardLocationList}>
                    {claim.citations.map((citation) => (
                      <span className={styles.feedCardLocation} key={`${claim.text}-${citation.chunk_id}-location`}>
                        {sourceLocationFor(citation)}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            }
            key={claim.text}
            title={claim.text}
          />
        );
      })}
    </div>
  );
}
