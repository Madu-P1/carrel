import { summarizeCertificate, type CertClaim, type Certificate } from "./certificate";
import styles from "./attest.module.css";

/**
 * The sealed attestation record, rendered as a composed exhibit.
 *
 * This is the artifact the north star makes demandable: the same canonical
 * record every Cachet surface issues (app, daemon, CLI, companion), read here
 * the way a filed exhibit is read. Register rules from the certificate
 * renderer in the kernel: refusals carry the same weight as confirmations,
 * no celebratory language, oxblood marks alterations only, and every line
 * traces to the sealed body.
 */

const STATE_LINE: Record<string, string> = {
  verified: "Verified against the record",
  altered: "Altered from the record",
  could_not_check: "Could not be checked",
};

function stateClass(state: string): string {
  if (state === "altered") return styles.stateAltered;
  if (state === "verified") return styles.stateVerified;
  return styles.stateRefused;
}

function ClaimRuling({ claim, index }: { claim: CertClaim; index: number }) {
  return (
    <li className={styles.claim}>
      <div className={styles.claimHead}>
        <span className={styles.claimIndex}>{index + 1}</span>
        <span className={[styles.claimState, stateClass(claim.state)].join(" ")}>
          {STATE_LINE[claim.state] ?? STATE_LINE.could_not_check}
        </span>
      </div>
      <p className={styles.claimText}>{claim.claim}</p>
      {claim.checks
        .filter((check) => check.detail)
        .map((check, i) => (
          <p key={i} className={styles.receipt}>
            {check.detail}
            <span className={styles.provenance}> [{check.provenance}]</span>
          </p>
        ))}
    </li>
  );
}

export function AttestationRecord({ cert }: { cert: Certificate }) {
  const summary = summarizeCertificate(cert);
  return (
    <article className={styles.record} aria-label="Attestation record">
      <header className={styles.recordHead}>
        <p className={styles.recordKicker}>Cachet attestation record</p>
        <h2 className={[styles.ruling, stateClass(cert.state)].join(" ")}>
          {STATE_LINE[cert.state] ?? STATE_LINE.could_not_check}
        </h2>
        <dl className={styles.tally} aria-label="Statement tally">
          <div className={styles.tallyItem}>
            <dt className={styles.tallyTerm}>Examined</dt>
            <dd className={styles.tallyCount}>{summary.total}</dd>
          </div>
          <div className={styles.tallyItem}>
            <dt className={styles.tallyTerm}>Verified</dt>
            <dd className={styles.tallyCount}>{summary.verified}</dd>
          </div>
          <div className={styles.tallyItem}>
            <dt className={styles.tallyTerm}>Altered</dt>
            <dd className={[styles.tallyCount, summary.altered > 0 ? styles.tallyAltered : ""].join(" ")}>
              {summary.altered}
            </dd>
          </div>
          <div className={styles.tallyItem}>
            <dt className={styles.tallyTerm}>Could not check</dt>
            <dd className={styles.tallyCount}>{summary.couldNotCheck}</dd>
          </div>
        </dl>
      </header>

      <ol className={styles.claims}>
        {(cert.claims ?? []).map((claim, i) => (
          <ClaimRuling key={i} claim={claim} index={i} />
        ))}
      </ol>

      <footer className={styles.provenanceBlock} aria-label="Record provenance">
        <div className={styles.provRow}>
          <span className={styles.provKey}>Issued</span>
          <span className={styles.provVal}>{cert.issued_at}</span>
        </div>
        <div className={styles.provRow}>
          <span className={styles.provKey}>Kernel</span>
          <span className={styles.provVal}>
            cachet-verify {cert.kernel_version} · schema v{cert.schema_version}
          </span>
        </div>
        <div className={styles.provRow}>
          <span className={styles.provKey}>Draft</span>
          <span className={styles.provVal}>{cert.draft_sha256}</span>
        </div>
        {(cert.source_sha256s ?? []).map((hash, i) => (
          <div key={i} className={styles.provRow}>
            <span className={styles.provKey}>Source {i + 1}</span>
            <span className={styles.provVal}>{hash}</span>
          </div>
        ))}
        <div className={styles.provRow}>
          <span className={styles.provKey}>Seal</span>
          <span className={styles.provVal}>{cert.fingerprint}</span>
        </div>
        <p className={styles.disclaimer}>
          This record attests only what a deterministic engine could trace to the
          sources named above. A statement marked could-not-be-checked is neither
          confirmed nor accused.
        </p>
      </footer>
    </article>
  );
}
