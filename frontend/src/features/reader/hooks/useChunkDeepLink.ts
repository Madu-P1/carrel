import { useEffect } from "preact/hooks";

import type { DocumentDetail } from "@/services/api/endpoints";

import { requestReaderPage, readerState } from "../state";

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];

export function buildReaderChunkPath(docId: string, chunkId?: string | null): string {
  const encodedDocId = encodeURIComponent(docId);
  if (!chunkId) {
    return `/reader/${encodedDocId}`;
  }
  return `/reader/${encodedDocId}?chunk=${encodeURIComponent(chunkId)}`;
}

export function useChunkDeepLink(chunkId: string | null | undefined, chunks: ReaderChunk[]) {
  useEffect(() => {
    if (!chunkId) {
      readerState.highlightedChunkId.value = null;
      return;
    }

    const matchedChunk = chunks.find((chunk) => chunk.id === chunkId);
    if (!matchedChunk) {
      readerState.highlightedChunkId.value = null;
      return;
    }

    readerState.highlightedChunkId.value = matchedChunk.id;
    if (matchedChunk.page_num != null) {
      requestReaderPage(matchedChunk.page_num);
    }
  }, [chunkId, chunks]);
}
