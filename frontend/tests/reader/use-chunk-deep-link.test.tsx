import { render, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { useChunkDeepLink } from "../../src/features/reader/hooks/useChunkDeepLink";
import { readerState } from "../../src/features/reader/state";

function ChunkDeepLinkProbe({
  chunkId
}: {
  chunkId: string | null;
}) {
  useChunkDeepLink(chunkId, [
    { content: "One", id: "chunk-1", page_num: 1, section: "A" },
    { content: "Two", id: "chunk-2", page_num: 4, section: "B" }
  ]);
  return null;
}

test("useChunkDeepLink highlights the matching chunk and requests its page", async () => {
  render(<ChunkDeepLinkProbe chunkId="chunk-2" />);

  await waitFor(() => {
    expect(readerState.highlightedChunkId.value).toBe("chunk-2");
    expect(readerState.requestedPage.value).toBe(4);
  });
});

test("useChunkDeepLink clears highlight when the chunk is missing", async () => {
  render(<ChunkDeepLinkProbe chunkId="missing" />);

  await waitFor(() => {
    expect(readerState.highlightedChunkId.value).toBe(null);
  });
});
