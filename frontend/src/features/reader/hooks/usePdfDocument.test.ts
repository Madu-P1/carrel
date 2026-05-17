import { expect, test } from "vitest";

import { deriveOutlineFromChunks } from "./usePdfDocument";

// Minimal chunk-shape helper. The real chunk type has many fields but
// deriveOutlineFromChunks only reads `section` and `page_num`, so a
// partial cast through the function's own parameter type keeps the
// test honest without exporting ReaderChunk just for tests.
type ChunkUnderTest = Parameters<typeof deriveOutlineFromChunks>[0][number];
function chunk(section: string, page_num: number | null): ChunkUnderTest {
  return { section, page_num } as ChunkUnderTest;
}

test("deriveOutlineFromChunks returns empty array for empty input", () => {
  // Sanity: the fallback must not synthesize phantom nodes from no data.
  expect(deriveOutlineFromChunks([])).toEqual([]);
});

test("deriveOutlineFromChunks dedupes adjacent same-section + same-page runs", () => {
  // The dominant case for academic PDFs: ingestion produces 5 chunks
  // for one Chapter 1 page; the rail should show ONE node, not five.
  const result = deriveOutlineFromChunks([
    chunk("Chapter 1", 1),
    chunk("Chapter 1", 1),
    chunk("Chapter 1", 1),
    chunk("Chapter 2", 5),
  ]);
  expect(result).toHaveLength(2);
  expect(result[0].title).toBe("Chapter 1");
  expect(result[0].pageNumber).toBe(1);
  expect(result[1].title).toBe("Chapter 2");
  expect(result[1].pageNumber).toBe(5);
});

test("deriveOutlineFromChunks treats same section on different pages as separate nodes", () => {
  // Long chapters span pages — each page within the same section is its own
  // outline entry so the rail reflects the document's reading order, not
  // just its section structure.
  const result = deriveOutlineFromChunks([
    chunk("Chapter 1", 1),
    chunk("Chapter 1", 5),
    chunk("Chapter 1", 12),
  ]);
  expect(result).toHaveLength(3);
  expect(result.map((node) => node.pageNumber)).toEqual([1, 5, 12]);
});

test("deriveOutlineFromChunks keeps non-adjacent same sections separate", () => {
  // Real documents revisit prior sections (e.g., "Intro" referenced again
  // late in the document). The rail should reflect actual sequence, not
  // pretend the document is sorted by section.
  const result = deriveOutlineFromChunks([
    chunk("Intro", 1),
    chunk("Chapter 1", 2),
    chunk("Intro", 10),
  ]);
  expect(result).toHaveLength(3);
  expect(result.map((node) => node.title)).toEqual(["Intro", "Chapter 1", "Intro"]);
});

test("deriveOutlineFromChunks falls back to 'Source section' when section is empty", () => {
  // Some chunks have no section metadata (early or unstructured chunks).
  // The rail still needs a label so the entry is clickable; "Source
  // section" is the agreed fallback.
  const result = deriveOutlineFromChunks([chunk("", 5), chunk("   ", 6)]);
  expect(result).toHaveLength(2);
  expect(result[0].title).toBe("Source section");
  expect(result[1].title).toBe("Source section");
});

test("deriveOutlineFromChunks preserves null page_num", () => {
  // Page-less chunks (e.g., metadata pages, or non-paged source types)
  // pass through with null pageNumber so the rail can degrade
  // gracefully rather than render a bogus page anchor.
  const result = deriveOutlineFromChunks([chunk("A", 1), chunk("B", null)]);
  expect(result[0].pageNumber).toBe(1);
  expect(result[1].pageNumber).toBeNull();
});

test("deriveOutlineFromChunks always returns child-less leaf nodes", () => {
  // The fallback is a flat outline — there's no nesting information in
  // chunk metadata. Each node ships with children:[] so OutlineRail can
  // treat the result identically to a real PDF.js outline.
  const result = deriveOutlineFromChunks([chunk("A", 1), chunk("B", 2)]);
  for (const node of result) {
    expect(node.children).toEqual([]);
  }
});
