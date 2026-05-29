import { Button } from "@/design-system";

import type { CertificationModel } from "./certification";
import styles from "./VerifyView.module.css";

function formatStamp(iso: string): string {
  return iso
    .replace("T", " ")
    .replace(/\.\d+Z$/, " UTC")
    .replace(/Z$/, " UTC");
}

interface CertificationExhibitProps {
  model: CertificationModel;
  onClose: () => void;
}

/**
 * The exportable certification: a dated, fingerprinted, court-exhibit-shaped
 * record. Exported via the OS print dialog (Save as PDF), so it needs no PDF
 * dependency. The "items requiring attorney review" section leads; the human is
 * kept in the chair (the tool checks, the attorney certifies). No confidence
 * numbers, by design.
 */
export function CertificationExhibit({ model, onClose }: CertificationExhibitProps) {
  const stamp = formatStamp(model.generatedAtISO);
  return (
    <div
      className={styles.certOverlay}
      role="dialog"
      aria-modal="true"
      aria-label="Verification certification"
    >
      <div className={styles.certToolbar}>
        <button type="button" className={styles.inspectorClose} onClick={onClose}>
          Close
        </button>
        <Button type="button" onClick={() => window.print()}>
          Save as PDF
        </Button>
      </div>

      <article className={[styles.verifyScope, styles.certExhibit].join(" ")}>
        <header className={styles.certHead}>
          <h2 className={styles.certTitle}>Verification certification</h2>
          <dl className={styles.certMeta}>
            <div>
              <dt>Generated</dt>
              <dd>{stamp}</dd>
            </div>
            <div>
              <dt>Document fingerprint</dt>
              <dd className={styles.certMono}>{model.fingerprint}</dd>
            </div>
            <div>
              <dt>Statements checked</dt>
              <dd className={styles.certMono}>{model.totalStatements}</dd>
            </div>
            {model.provider ? (
              <div>
                <dt>Checked by</dt>
                <dd>{model.provider}</dd>
              </div>
            ) : null}
          </dl>
        </header>

        <section className={styles.certSection}>
          <h3 className={styles.certSectionLabel}>Items requiring attorney review</h3>
          {model.flagged.length === 0 ? (
            <p className={styles.certMuted}>
              No items were flagged. Every statement was grounded in the sources provided. This
              confirms grounding, not legal correctness.
            </p>
          ) : (
            <ol className={styles.certList}>
              {model.flagged.map((it) => (
                <li key={it.index} className={styles.certItem}>
                  <span className={styles.certItemLabel}>{it.label}</span>
                  <span className={styles.certItemClaim}>{it.claimText}</span>
                  {it.sources.length > 0 ? (
                    <span className={styles.certItemSources}>{it.sources.join("; ")}</span>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className={styles.certSection}>
          <h3 className={styles.certSectionLabel}>All statements checked</h3>
          <ol className={styles.certList}>
            {model.allItems.map((it) => (
              <li key={it.index} className={styles.certItem}>
                <span className={styles.certItemLabel}>{it.label}</span>
                <span className={styles.certItemClaim}>{it.claimText}</span>
                {it.sources.length > 0 ? (
                  <span className={styles.certItemSources}>{it.sources.join("; ")}</span>
                ) : null}
              </li>
            ))}
          </ol>
        </section>

        <footer className={styles.certFooter}>
          <p>
            This report records an automated check of the statements above against the sources
            provided, as of {stamp}. It confirms grounding against those sources only. It does not
            assess legal correctness, strategy, or completeness.
          </p>
          <p className={styles.certSign}>
            Reviewed by ______________________. The reviewing attorney is responsible for the
            filing; this report did not draft or approve it.
          </p>
        </footer>
      </article>
    </div>
  );
}
