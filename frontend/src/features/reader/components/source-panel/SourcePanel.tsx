import { useEffect, useMemo, useState } from "preact/hooks";

import type { DocumentDetail, EvidenceResolution } from "@/services/api/endpoints";
import { notes as notesApi } from "@/services/api/endpoints";
import { createQuery } from "@/lib/query";
import { Button, Icon, Stack, Tabs } from "@/design-system";
import type { TabItem } from "@/design-system";

import { CardAiDraftDialog } from "@/features/study/CardAiDraftDialog";

import { ChunksList } from "./ChunksList";
import { ConceptsList } from "./ConceptsList";
import { EmptyState } from "./EmptyState";
import { MetadataStripe } from "./MetadataStripe";
import { NoteComposer } from "./NoteComposer";
import { NotesList } from "./NotesList";
import { EvidenceInspector } from "./EvidenceInspector";
import { AnchorColumn } from "./AnchorColumn";
import { readerState } from "../../state";
import styles from "./SourcePanel.module.css";

type TabId = "chunks" | "concepts" | "anchors" | "notes" | "related";

interface SourcePanelProps {
  detail: DocumentDetail;
  docId: string;
  selectedEvidence?: EvidenceResolution | null;
  /** Opens the manual New Card dialog (mounted by the Reader). Omitted
   *  for non-PDF sources, which hides the New Card button. */
  onCreateCard?: () => void;
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
export function SourcePanel({ detail, docId, selectedEvidence = null, onCreateCard }: SourcePanelProps) {
  const chunks = detail.chunks ?? [];
  const concepts = detail.concepts ?? [];

  // Notes are fetched per-document, not carried on `detail`: the Notes
  // tab both writes and views, so it needs an independently
  // refetchable list (write a note -> refetch -> it appears). The old
  // `detail.notes` cast read a field the backend never populated.
  const notesQuery = useMemo(
    () => createQuery(() => notesApi.list({ doc_id: docId, limit: 100 })),
    [docId]
  );
  useEffect(() => {
    const unsubscribe = notesQuery.subscribe();
    void notesQuery.refetch();
    return unsubscribe;
  }, [notesQuery]);
  const noteRecords = notesQuery.data.value?.notes ?? [];

  const [tab, setTab] = useState<TabId>(selectedEvidence ? "related" : "chunks");
  const [aiDraftOpen, setAiDraftOpen] = useState(false);
  const currentPage = readerState.currentPage.value || null;

  useEffect(() => {
    if (selectedEvidence) {
      setTab("related");
    }
  }, [selectedEvidence]);

  const items: TabItem[] = [
    { id: "chunks", label: "Chunks", count: chunks.length },
    { id: "concepts", label: "Concepts", count: concepts.length },
    { id: "anchors", label: "Anchors", count: 0 },
    { id: "notes", label: "Notes", count: noteRecords.length },
    { id: "related", label: selectedEvidence ? "Evidence" : "Related", count: selectedEvidence ? 1 : 0 }
  ];

  return (
    <div className={styles.panel}>
      <MetadataStripe doc={detail.document} />
      {/*
        PR 0a — auto-card-generation on upload is off. Users now opt
        into AI card drafting from the document detail surface. The
        button reuses the existing CardAiDraftDialog (which posts to
        /api/srs/cards/ai-draft); no tier check today.
      */}
      <Stack direction="horizontal" gap={2}>
        {onCreateCard ? (
          <Button onClick={onCreateCard} variant="secondary">
            New card
          </Button>
        ) : null}
        <Button
          leadingIcon={<Icon name="sparkle" />}
          onClick={() => setAiDraftOpen(true)}
          variant="secondary"
        >
          Draft cards with AI
        </Button>
      </Stack>
      <CardAiDraftDialog
        onCardsCreated={() => {
          // Card creation is its own surface; the source panel doesn't
          // own the card list. Closing is handled by the dialog itself.
        }}
        onClose={() => setAiDraftOpen(false)}
        open={aiDraftOpen}
      />
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
        {tab === "anchors" ? <AnchorColumn docId={docId} pageNum={currentPage} /> : null}
        {tab === "notes" ? (
          <Stack gap={3}>
            <NoteComposer
              docId={docId}
              documentName={detail.document?.filename ?? undefined}
              onSaved={() => void notesQuery.refetch()}
            />
            <NotesList notes={noteRecords} />
          </Stack>
        ) : null}
        {tab === "related" && selectedEvidence ? (
          <EvidenceInspector evidence={selectedEvidence} />
        ) : null}
        {tab === "related" && !selectedEvidence ? (
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
