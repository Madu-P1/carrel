import type { DocumentDetail } from "@/services/api/endpoints";

import { EmptyState } from "./EmptyState";
import styles from "./SourcePanel.module.css";

type ReaderConcept = NonNullable<DocumentDetail["concepts"]>[number];

function conceptName(concept: ReaderConcept): string {
  const name = concept.name;
  return typeof name === "string" && name.trim() ? name : "Unnamed concept";
}

function conceptDescription(concept: ReaderConcept): string {
  const description = concept.description;
  return typeof description === "string" ? description : "";
}

export function ConceptsList({ concepts }: { concepts: ReaderConcept[] }) {
  if (concepts.length === 0) {
    return (
      <EmptyState
        icon="sparkle"
        title="No concepts extracted yet."
        description="The tutor pulls key concepts the first time you study this source. They will appear here as soon as it runs."
      />
    );
  }

  return (
    <ul className={styles.rowList}>
      {concepts.map((concept, index) => {
        const description = conceptDescription(concept);
        return (
          <li
            className={styles.conceptRow}
            key={`${conceptName(concept)}-${index}`}
          >
            <div className={styles.rowHeader}>
              <span className={styles.rowTitle}>{conceptName(concept)}</span>
            </div>
            {description ? (
              <p className={styles.rowPreview}>{description}</p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
