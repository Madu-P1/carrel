import { useEffect, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { Spinner } from "@/design-system";
import {
  evidence,
  type EvidenceResolution,
  type VerifyClaimVerdict
} from "@/services/api/endpoints";

import type { ClaimDisposition } from "./claimDisposition";
import styles from "./VerifyView.module.css";

type Citation = NonNullable<VerifyClaimVerdict["citations"]>[number];
type CaseBatch = NonNullable<VerifyClaimVerdict["case_verdicts"]>[number];
type CaseVerdict = NonNullable<CaseBatch["verdicts"]>[number];

function locationLabel(kind: EvidenceResolution["location_kind"]): string {
  return kind === "bbox" || kind === "text_offset" ? "Exact span" : "Approximate passage";
}

/**
 * One cited corpus source, resolved to its exact span. Deliberately renders
 * no confidence score: on the verify surface a verdict is a finding, not a
 * percentage. Falls back to the stored snippet if the live resolve fails so
 * the litigator still sees the cited text.
 */
function CitationSource({ citation }: { citation: Citation }) {
  const docId = citation.document_id;
  const nodeId = citation.node_id != null ? String(citation.node_id) : "";
  const fallbackQuote = (citation.snippet ?? citation.content ?? "").trim();
  const [resolved, setResolved] = useState<EvidenceResolution | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    let active = true;
    setStatus("loading");
    setResolved(null);
    void evidence
      .resolve({ documentId: docId, chunkId: nodeId || null })
      .then((data) => {
        if (active) {
          setResolved(data);
          setStatus("ok");
        }
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [docId, nodeId]);

  const documentName = resolved?.document_name ?? citation.document_name ?? "Source";
  const pageNum = resolved?.page_num ?? citation.page_num ?? null;
  const section = resolved?.section ?? citation.section ?? null;
  const quote = (resolved?.quote_text ?? fallbackQuote).trim();

  const openInReader = () => {
    navigateTo(`/reader/${encodeURIComponent(docId)}?node=${encodeURIComponent(nodeId)}`);
  };

  return (
    <div className={styles.sourceItem}>
      <div className={styles.sourceItemHead}>
        <span className={styles.sourceDoc}>{documentName}</span>
        <span className={styles.sourceLoc}>
          {pageNum ? `p. ${pageNum}` : "page unknown"}
          {section ? ` · ${section}` : ""}
        </span>
      </div>
      {status === "loading" ? (
        <div className={styles.sourceLoading}>
          <Spinner size={16} />
          <span>Resolving the cited span…</span>
        </div>
      ) : quote ? (
        <blockquote className={styles.sourceQuote}>“{quote}”</blockquote>
      ) : (
        <p className={styles.sourceMuted}>The cited span could not be read from this source.</p>
      )}
      <div className={styles.sourceFoot}>
        {status === "ok" && resolved ? (
          <span className={styles.sourceLocKind}>{locationLabel(resolved.location_kind)}</span>
        ) : status === "error" ? (
          <span className={styles.sourceLocKind}>Showed the stored snippet; live resolve failed.</span>
        ) : (
          <span />
        )}
        {nodeId ? (
          <button type="button" className={styles.sourceOpen} onClick={openInReader}>
            Open in reader
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** One cited case, linking out to the actual opinion on CourtListener. */
function CaseSource({ verdict }: { verdict: CaseVerdict }) {
  const url = verdict.absolute_url ?? null;
  return (
    <div className={styles.sourceItem}>
      <div className={styles.sourceItemHead}>
        <span className={styles.sourceDoc}>{verdict.case_name ?? verdict.citation}</span>
        <span className={styles.sourceLoc}>{verdict.citation}</span>
      </div>
      {verdict.holding_excerpt ? (
        <blockquote className={styles.sourceQuote}>“{verdict.holding_excerpt}”</blockquote>
      ) : null}
      <div className={styles.sourceFoot}>
        <span />
        {url ? (
          <a className={styles.sourceOpen} href={url} target="_blank" rel="noopener noreferrer">
            Open opinion
          </a>
        ) : null}
      </div>
    </div>
  );
}

interface SourceInspectorProps {
  card: VerifyClaimVerdict;
  disposition: ClaimDisposition;
  onClose: () => void;
}

/**
 * The cited sources for a claim, without any chrome. Shared by the legacy
 * split-pane `SourceInspector` and the PR5b Examination drawer so both render
 * the same source content (the resolve/fetch path lives in `CitationSource`).
 */
export function SourceInspectorBody({
  card,
  disposition
}: {
  card: VerifyClaimVerdict;
  disposition: ClaimDisposition;
}) {
  const citations = (card.citations ?? []) as Citation[];
  const cases: CaseVerdict[] = (card.case_verdicts ?? []).flatMap((b) =>
    b?.ok ? ((b.verdicts ?? []) as CaseVerdict[]) : []
  );
  const hasSources = citations.length > 0 || cases.length > 0;
  return (
    <>
      {citations.length > 0 ? (
        <section className={styles.sourceGroup}>
          <h3 className={styles.sourceGroupLabel}>From your sources</h3>
          {citations.map((c, i) => (
            <CitationSource key={`${c.document_id}-${String(c.node_id)}-${i}`} citation={c} />
          ))}
        </section>
      ) : null}
      {cases.length > 0 ? (
        <section className={styles.sourceGroup}>
          <h3 className={styles.sourceGroupLabel}>Cited cases</h3>
          {cases.map((v, i) => (
            <CaseSource key={`${v.citation}-${i}`} verdict={v} />
          ))}
        </section>
      ) : null}
      {!hasSources ? (
        <p className={styles.sourceMuted}>
          {disposition.kind === "could_not_check"
            ? "No source was loaded to check this statement against. Add the documents this draft relies on, then verify again."
            : "No source is attached to this statement."}
        </p>
      ) : null}
    </>
  );
}

/**
 * The right-hand source panel: the cited source beside the claim. Land on the
 * exact span, not a top-of-document guess. The make-or-break interaction for a
 * litigator, who lives or dies on getting to the page.
 */
export function SourceInspector({ card, disposition, onClose }: SourceInspectorProps) {
  return (
    <aside className={styles.inspector} aria-label="Source for the selected statement">
      <header className={styles.inspectorHead}>
        <span className={styles.inspectorTitle}>Source</span>
        <button
          type="button"
          className={styles.inspectorClose}
          onClick={onClose}
          aria-label="Close source panel"
        >
          Close
        </button>
      </header>
      <p className={styles.inspectorClaim}>{card.claim_text}</p>
      <SourceInspectorBody card={card} disposition={disposition} />
    </aside>
  );
}
