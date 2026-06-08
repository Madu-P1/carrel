import { useEffect, useRef, useState } from "preact/hooks";

import { Spinner } from "@/design-system";
import {
  evidence,
  reader,
  type EvidenceResolution,
  type ReaderNodeResponse,
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
 * The cited passage in its surrounding clause, opened over the record. An
 * overlay, not a route: VerifyView holds its result in local state and the
 * Cachet shell unmounts a view on navigation, so routing away to a reader would
 * discard an unsaved verification. The record stays mounted beneath the scrim.
 *
 * Honest highlight: the validated quote is ink-underlined only on an exact
 * (case-insensitive) substring match of the source passage. If it cannot be
 * located the passage is shown plain with a visible note, never a fabricated
 * highlight. If the typed node is unavailable the panel says so and falls back
 * to the cited quote. No generation.
 */
function SourcePassageOverlay({
  nodeId,
  quote,
  documentName,
  locator,
  onClose
}: {
  nodeId: string;
  quote: string;
  documentName: string;
  locator: string;
  onClose: () => void;
}) {
  const [node, setNode] = useState<ReaderNodeResponse | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    setStatus("loading");
    setNode(null);
    const id = Number(nodeId);
    if (!Number.isFinite(id) || id <= 0) {
      setStatus("error");
      return;
    }
    void reader
      .fetchNode(id)
      .then((data) => {
        if (active) {
          setNode(data);
          setStatus("ok");
        }
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [nodeId]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const passage = (node?.verbatim_text ?? "").trim();
  const heading = (node?.heading_path ?? "").trim();
  const runIndex = quote && passage ? passage.toLowerCase().indexOf(quote.toLowerCase()) : -1;
  const located = runIndex >= 0;

  return (
    <div className={styles.sourceScrim} role="presentation" onClick={onClose}>
      <div
        className={styles.sourcePanel}
        role="dialog"
        aria-modal="true"
        aria-label={`Cited passage in ${documentName}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className={styles.sourcePanelHead}>
          <div className={styles.sourcePanelLoc}>
            <span className={styles.sourcePanelDoc}>{documentName}</span>
            <span className={styles.sourcePanelMeta}>{heading || locator}</span>
          </div>
          <button
            ref={closeRef}
            type="button"
            className={styles.inspectorClose}
            onClick={onClose}
            aria-label="Close source passage"
          >
            Close
          </button>
        </header>
        {status === "loading" ? (
          <div className={styles.sourcePanelBody}>
            <div className={styles.sourceLoading}>
              <Spinner size={16} />
              <span>Opening the cited passage…</span>
            </div>
          </div>
        ) : status === "error" ? (
          <div className={styles.sourcePanelBody}>
            <p className={styles.sourceMuted}>
              This source passage is not available to open in place. The cited text:
            </p>
            {quote ? <blockquote className={styles.sourceQuote}>“{quote}”</blockquote> : null}
          </div>
        ) : located ? (
          <div className={styles.sourcePanelBody}>
            <p className={styles.sourcePassage}>
              {passage.slice(0, runIndex)}
              <mark className={styles.sourceRun}>
                {passage.slice(runIndex, runIndex + quote.length)}
              </mark>
              {passage.slice(runIndex + quote.length)}
            </p>
          </div>
        ) : (
          <div className={styles.sourcePanelBody}>
            <p className={styles.sourcePassage}>{passage}</p>
            <p className={styles.sourceMuted}>
              Could not locate the exact cited run in this passage.
            </p>
          </div>
        )}
      </div>
    </div>
  );
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
  const [sourceOpen, setSourceOpen] = useState(false);

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
  const locator = `${pageNum ? `p. ${pageNum}` : "page unknown"}${section ? ` · ${section}` : ""}`;

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
          <button
            type="button"
            className={styles.sourceOpen}
            onClick={() => setSourceOpen(true)}
          >
            Open in source
          </button>
        ) : null}
      </div>
      {sourceOpen ? (
        <SourcePassageOverlay
          nodeId={nodeId}
          quote={quote}
          documentName={documentName}
          locator={locator}
          onClose={() => setSourceOpen(false)}
        />
      ) : null}
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
