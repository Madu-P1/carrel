import { useState } from "preact/hooks";

import type { DocumentDetail } from "@/services/api/endpoints";
import { Tabs } from "@/design-system";
import type { TabItem } from "@/design-system";

import { ChunksList } from "./ChunksList";
import { ConceptsList } from "./ConceptsList";
import { EmptyState } from "./EmptyState";
import { MetadataStripe } from "./MetadataStripe";
import { NotesList } from "./NotesList";
import styles from "./SourcePanel.module.css";

type TabId = "chunks" | "concepts" | "notes" | "related";

interface SourcePanelProps {
  detail: DocumentDetail;
  docId: string;
}

/**
 * SourcePanel — the Reader's right rail.
 *
 * Premium rebuild ship 3b: the rail now renders a compact MetadataStripe
 * on top, then a segmented Tabs row, then a single scrollable tabpanel.
 * The prior flat layout stacked four separate `Pane` sections, which
 * meant the user had to scroll past Chunks to see Concepts — in a 320px
 * column that was painful. Tabs let each list own the whole panel.
 *
 * Tab structure:
 *   Chunks     the source-chunk list (grouped by page where applicable)
 *   Concepts   AI-extracted key concepts
 *   Notes      user notes anchored to this source
 *   Related    scaffold for "other sources that cite or are cited by
 *              this one" (pending the related-sources index)
 *
 * Scripted empty states per tab (no blank voids allowed). "Related"
 * always renders the empty state for now — the feature ships later.
 */
export function SourcePanel({ detail, docId }: SourcePanelProps) {
  const chunks = detail.chunks ?? [];
  const concepts = detail.concepts ?? [];
  const notes = Array.isArray((detail as Record<string, unknown>).notes)
    ? ((((detail as Record<string, unknown>).notes) as unknown[]) as Array<{
        content?: string;
        title?: string;
      }>)
    : [];

  const [tab, setTab] = useState<TabId>("chunks");

  const items: TabItem[] = [
    { id: "chunks", label: "Chunks", count: chunks.length },
    { id: "concepts", label: "Concepts", count: concepts.length },
    { id: "notes", label: "Notes", count: notes.length },
    { id: "related", label: "Related", count: 0 }
  ];

  return (
    <div className={styles.panel}>
      <MetadataStripe doc={detail.document} />
      <Tabs
        ariaLabel="Source panel sections"
        items={items}
        onChange={(next) => setTab(next as TabId)}
        value={tab}
        variant="segmented"
      />
      <div
        aria-label={`${tab} tab panel`}
        className={styles.tabPanel}
        role="tabpanel"
      >
        {tab === "chunks" ? <ChunksList chunks={chunks} docId={docId} /> : null}
        {tab === "concepts" ? <ConceptsList concepts={concepts} /> : null}
        {tab === "notes" ? <NotesList notes={notes} /> : null}
        {tab === "related" ? (
          <EmptyState
            icon="library"
            title="No related sources yet."
            description="When another source in your library shares concepts with this one, it will show up here with a jump link."
          />
        ) : null}
      </div>
    </div>
  );
}
