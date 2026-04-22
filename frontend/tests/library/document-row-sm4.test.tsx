import { act, cleanup, render } from "@testing-library/preact";
import { afterEach, describe, expect, test } from "vitest";

import { DocumentRow } from "@/features/library/components/DocumentRow";
import type { DocumentRow as DocumentRowType } from "@/services/api/endpoints";

function makeDoc(overrides: Partial<DocumentRowType> = {}): DocumentRowType {
  return {
    id: "doc-a",
    filename: "sample.pdf",
    subject_name: "General",
    file_type: "pdf",
    upload_date: "2026-04-21T00:00:00Z",
    status: "processing",
    summary: "",
    page_count: 12,
    concept_count: 0,
    question_count: 0,
    chunk_count: 0,
    srs_card_count: 0,
    confidence: null,
    ingested_at: null,
    updated_at: null,
    storage_name: null,
    ...overrides,
  } as unknown as DocumentRowType;
}

describe("DocumentRow SM-4 (ingest complete pulse)", () => {
  afterEach(() => {
    cleanup();
  });

  test("applies anim-pulseOnce when status transitions processing → ready", () => {
    const doc = makeDoc({ status: "processing" });
    const { rerender, container } = render(
      <DocumentRow document={doc} onDelete={() => {}} onOpen={() => {}} />,
    );
    const card = container.querySelector(`button[data-doc-id="doc-a"]`);
    expect(card?.className).not.toMatch(/anim-pulseOnce/);

    const readyDoc = makeDoc({ status: "ready" });
    act(() => {
      rerender(<DocumentRow document={readyDoc} onDelete={() => {}} onOpen={() => {}} />);
    });
    const after = container.querySelector(`button[data-doc-id="doc-a"]`);
    expect(after?.className).toMatch(/anim-pulseOnce/);
  });

  test("does NOT pulse on the very first render (no prior status)", () => {
    const doc = makeDoc({ status: "ready" });
    const { container } = render(
      <DocumentRow document={doc} onDelete={() => {}} onOpen={() => {}} />,
    );
    const card = container.querySelector(`button[data-doc-id="doc-a"]`);
    expect(card?.className).not.toMatch(/anim-pulseOnce/);
  });

  test("does NOT pulse on ready → ready no-op updates", () => {
    const doc = makeDoc({ status: "ready" });
    const { rerender, container } = render(
      <DocumentRow document={doc} onDelete={() => {}} onOpen={() => {}} />,
    );
    act(() => {
      rerender(<DocumentRow document={doc} onDelete={() => {}} onOpen={() => {}} />);
    });
    const card = container.querySelector(`button[data-doc-id="doc-a"]`);
    expect(card?.className).not.toMatch(/anim-pulseOnce/);
  });
});
