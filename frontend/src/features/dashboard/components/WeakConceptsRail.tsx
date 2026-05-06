import { navigateTo } from "@/app/shell/useAppShell";
import { Icon } from "@/design-system";
import type { WeakConcept } from "@/services/api/endpoints";

import styles from "./WeakConceptsRail.module.css";

/**
 * Weak-concepts rail.
 *
 * The visible end of Carrel's SRS-feedback loop:
 *   review rating → mastery_engine → concepts.mastery → this rail
 *
 * Surfaces up to 5 concepts the user HAS been tested on (last_tested
 * is non-null) but hasn't cleared the fluency band on (mastery ≤ 0.7).
 * Renders as a horizontal-scrollable strip of compact cards. Each card
 * carries:
 *   - the concept name
 *   - a thin accent mastery bar (0..100%)
 *   - the source (document · subject)
 *   - a "→" affordance that navigates to /reader/{document_id} so the
 *     user can re-read the chunk that taught the concept
 *
 * Renders nothing when the list is empty — no "you're great!" filler.
 * The rail is for action; absence is silence.
 *
 * Why a strip and not a plain list: this sits BETWEEN the dominant
 * NextBestAction card and the QuickActionGrid. A vertical list there
 * would compete with both for visual weight. A horizontal strip reads
 * as "ambient signal," not "decision required."
 */
interface WeakConceptsRailProps {
  concepts: WeakConcept[];
}

export function WeakConceptsRail({ concepts }: WeakConceptsRailProps) {
  if (concepts.length === 0) return null;

  return (
    <section className={styles.wrap} aria-label="Concepts to revisit">
      <header className={styles.header}>
        <span className={styles.eyebrow}>Revisit</span>
        <h2 className={styles.title}>Concepts you tested on but haven't cleared.</h2>
      </header>
      <ul className={styles.strip}>
        {concepts.map((concept) => (
          <WeakConceptCard key={concept.id} concept={concept} />
        ))}
      </ul>
    </section>
  );
}

interface WeakConceptCardProps {
  concept: WeakConcept;
}

function WeakConceptCard({ concept }: WeakConceptCardProps) {
  // Mastery is 0..1. Floor at 4% so even brand-new struggles render a
  // visible nub on the bar; ceiling is the WEAK_CONCEPT_MASTERY_CEILING
  // server-side (0.7), so cards naturally fill ~6% to 70%.
  const masteryPct = Math.max(4, Math.round(concept.mastery * 100));
  const handleClick = () => {
    // Open the source in the Reader. From there the user can re-read
    // the chunk that introduced the concept; the existing
    // useChunkDeepLink + useCitationFlight pulse the deep-linked chunk.
    navigateTo(`/reader/${encodeURIComponent(concept.document_id)}`);
  };

  return (
    // Native <li><button> nesting keeps the screen-reader's "N of M list
    // items" announcement AND preserves the button's "clickable, will
    // activate on Enter/Space" semantics. The previous shape (button
    // with role="listitem") stripped the button role entirely on some
    // ATs, masking activation. Caught by adversarial review.
    <li className={styles.cardItem}>
      <button
        type="button"
        className={styles.card}
        onClick={handleClick}
        aria-label={`${concept.name}, ${masteryPct}% mastery, in ${concept.document_name ?? "source"}. Click to open in Reader.`}
      >
        <div className={styles.cardHeader}>
          <span className={styles.conceptName} title={concept.name}>
            {concept.name}
          </span>
          <span className={styles.cardArrow} aria-hidden>
            <Icon name="arrow-right" size={12} />
          </span>
        </div>
        <div className={styles.masteryRow}>
          <div className={styles.masteryBar}>
            <div
              className={styles.masteryFill}
              style={{ width: `${masteryPct}%` }}
              aria-hidden
            />
          </div>
          <span className={styles.masteryValue}>{masteryPct}%</span>
        </div>
        <div className={styles.cardMeta}>
          {concept.document_name ?? "Source"}
          {concept.subject_name ? ` · ${concept.subject_name}` : ""}
        </div>
      </button>
    </li>
  );
}
