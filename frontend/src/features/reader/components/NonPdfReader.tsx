import { Fragment } from "preact";
import { useEffect, useRef } from "preact/hooks";

import type { DocumentDetail } from "@/services/api/endpoints";
import { Button, Text, toast } from "@/design-system";
import { anchors } from "@/services/api/endpoints";

import { useReaderSelection } from "../hooks/useReaderSelection";
import { readerState } from "../state";
import styles from "./NonPdfReader.module.css";

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];

interface NonPdfReaderProps {
  chunks: ReaderChunk[];
  docId: string;
}

export function NonPdfReader({ chunks, docId }: NonPdfReaderProps) {
  const articleRef = useRef<HTMLElement>(null);
  const highlightedChunkId = readerState.highlightedChunkId.value;

  useReaderSelection(articleRef);

  useEffect(() => {
    if (!highlightedChunkId || !articleRef.current) {
      return;
    }

    const target = Array.from(
      articleRef.current.querySelectorAll<HTMLElement>("[data-chunk-id]")
    ).find((node) => node.dataset.chunkId === highlightedChunkId);
    if (!target) return;
    // JSDOM has no scrollIntoView; the effect can also fire after the test
    // tree has been torn down. Either way, falling through is fine.
    try {
      if (typeof target.scrollIntoView === "function") {
        target.scrollIntoView({ block: "center" });
      }
    } catch {
      /* no-op */
    }
  }, [highlightedChunkId]);

  let lastSection = "";

  return (
    <article className={styles.article} ref={articleRef}>
      {readerState.selectedText.value ? (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            void anchors.create({
              document_id: docId,
              quote_text: readerState.selectedText.value,
              origin: "highlight",
              confidence: 0.7
            })
              .then(() => {
                readerState.selectedText.value = "";
                toast.success("Anchor saved", "The highlight is now available in the Anchor Column.");
              })
              .catch(() => toast.error("Save failed", "Carrel could not save this highlight."));
          }}
        >
          Save selected text as anchor
        </Button>
      ) : null}
      {chunks.map((chunk) => {
        const showHeading = Boolean(chunk.section && chunk.section !== lastSection);
        if (chunk.section) {
          lastSection = chunk.section;
        }

        return (
          <Fragment key={chunk.id}>
            {showHeading ? (
              <Text as="h3" className={styles.section} variant="h2" weight="semibold">
                {chunk.section}
              </Text>
            ) : null}
            <Text
              className={[
                styles.paragraph,
                highlightedChunkId === chunk.id ? styles.highlighted : ""
              ]
                .filter(Boolean)
                .join(" ")}
              data-chunk-id={chunk.id}
            >
              {chunk.content}
            </Text>
          </Fragment>
        );
      })}
    </article>
  );
}
