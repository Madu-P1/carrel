import { Fragment } from "preact";
import { useEffect, useRef } from "preact/hooks";

import type { DocumentDetail } from "@/services/api/endpoints";
import { Text } from "@/design-system";

import { useReaderSelection } from "../hooks/useReaderSelection";
import { readerState } from "../state";
import styles from "./NonPdfReader.module.css";

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];

interface NonPdfReaderProps {
  chunks: ReaderChunk[];
}

export function NonPdfReader({ chunks }: NonPdfReaderProps) {
  const articleRef = useRef<HTMLElement>(null);
  const highlightedChunkId = readerState.highlightedChunkId.value;

  useReaderSelection(articleRef);

  useEffect(() => {
    if (!highlightedChunkId || !articleRef.current) {
      return;
    }

    Array.from(articleRef.current.querySelectorAll<HTMLElement>("[data-chunk-id]"))
      .find((node) => node.dataset.chunkId === highlightedChunkId)
      ?.scrollIntoView({ block: "center" });
  }, [highlightedChunkId]);

  let lastSection = "";

  return (
    <article className={styles.article} ref={articleRef}>
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
