import { useCallback, useEffect, useState } from "preact/hooks";

import { Button, Dialog, Stack, Text, toast } from "@/design-system";
import { anchors, type AnchorCardDraft, type AnchorRecord } from "@/services/api/endpoints";

import styles from "./SourcePanel.module.css";

function CardDraftDrawer({
  anchor,
  onClose,
  onPromoted
}: {
  anchor: AnchorRecord | null;
  onClose: () => void;
  onPromoted: () => void;
}) {
  const [drafts, setDrafts] = useState<AnchorCardDraft[]>([]);
  const [selected, setSelected] = useState(0);

  useEffect(() => {
    if (!anchor) return;
    setDrafts([]);
    setSelected(0);
    void anchors.draftCards(anchor.id)
      .then((response) => setDrafts(response.cards))
      .catch(() => toast.error("Draft failed", "Carrel could not draft cards from this Anchor."));
  }, [anchor]);

  const draft = drafts[selected];
  return (
    <Dialog
      open={!!anchor}
      title="Card Draft Drawer"
      description="Edit the strongest draft, then save it to Study."
      onClose={onClose}
      actions={
        <Stack direction="horizontal" gap={2}>
          <Button variant="ghost" onClick={onClose}>Close</Button>
          <Button
            disabled={!anchor || !draft}
            onClick={() => {
              if (!anchor || !draft) return;
              void anchors.promoteCard(anchor.id, {
                front: draft.front,
                back: draft.back,
                card_type: "anchor"
              })
                .then(() => {
                  toast.success("Card saved", "The Anchor is now in your review queue.");
                  onPromoted();
                  onClose();
                })
                .catch(() => toast.error("Save failed", "Carrel could not promote this Anchor."));
            }}
          >
            Save card
          </Button>
        </Stack>
      }
    >
      <Stack gap={3}>
        {drafts.length === 0 ? <Text tone="secondary">Drafting cards...</Text> : null}
        {drafts.map((item, index) => (
          <button
            className={[styles.anchorDraft, index === selected ? styles.anchorDraftSelected : ""].filter(Boolean).join(" ")}
            key={`${item.front}-${index}`}
            onClick={() => setSelected(index)}
            type="button"
          >
            <strong>{item.front}</strong>
            <span>{item.back}</span>
            {item.duplicate_warning ? <em>Possible duplicate</em> : null}
          </button>
        ))}
      </Stack>
    </Dialog>
  );
}

export function AnchorColumn({ docId, pageNum }: { docId: string; pageNum: number | null }) {
  const [items, setItems] = useState<AnchorRecord[]>([]);
  const [active, setActive] = useState<AnchorRecord | null>(null);

  const refresh = useCallback(() => {
    void anchors.listForDocument(docId, pageNum).then((response) => setItems(response.anchors));
  }, [docId, pageNum]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <Stack gap={3}>
      {items.length === 0 ? (
        <Text tone="secondary">No Anchors on this page yet.</Text>
      ) : (
        items.map((anchor) => (
          <button
            className={styles.anchorRow}
            key={anchor.id}
            onClick={() => setActive(anchor)}
            type="button"
          >
            <span>{anchor.claim_text || anchor.quote_text}</span>
            <em>{anchor.promotion_state}</em>
          </button>
        ))
      )}
      <CardDraftDrawer anchor={active} onClose={() => setActive(null)} onPromoted={refresh} />
    </Stack>
  );
}
