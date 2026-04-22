import type { DocumentDetail } from "@/services/api/endpoints";
import { Pane, Text } from "@/design-system";

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
  return (
    <Pane title={`Concepts (${concepts.length})`}>
      <div className={styles.conceptList}>
        {concepts.map((concept, index) => (
          <div className={styles.conceptItem} key={`${conceptName(concept)}-${index}`}>
            <Text weight="semibold">{conceptName(concept)}</Text>
            {conceptDescription(concept) ? (
              <Text tone="secondary">{conceptDescription(concept)}</Text>
            ) : null}
          </div>
        ))}
      </div>
    </Pane>
  );
}
