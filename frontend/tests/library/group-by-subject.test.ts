import { expect, test } from "vitest";

import type { DocumentRow } from "../../src/services/api/endpoints";
import { groupBySubject } from "../../src/features/library/utils/group-by-subject";

const docs: DocumentRow[] = [
  {
    concept_count: 1,
    confidence: 0.9,
    extracted_at: null,
    file_type: "pdf",
    filename: "doc-a.pdf",
    id: "doc-a",
    page_count: 2,
    parser_diagnostics: {},
    parser_status: "ready",
    question_count: 2,
    source_hash: null,
    source_kind: "uploaded_file",
    status: "ready",
    storage_name: null,
    subject_name: "Biology",
    summary: "A summary",
    updated_at: null,
    upload_date: null,
    duplicate_of: null
  },
  {
    concept_count: 1,
    confidence: 0.7,
    extracted_at: null,
    file_type: "docx",
    filename: "doc-b.docx",
    id: "doc-b",
    page_count: 1,
    parser_diagnostics: {},
    parser_status: "ready",
    question_count: 1,
    source_hash: null,
    source_kind: "uploaded_file",
    status: "ready",
    storage_name: null,
    subject_name: null,
    summary: "B summary",
    updated_at: null,
    upload_date: null,
    duplicate_of: null
  }
];

test("groupBySubject groups rows by subject and falls back to General", () => {
  const grouped = groupBySubject(docs);

  expect(Object.keys(grouped)).toEqual(["Biology", "General"]);
  expect(grouped.Biology?.[0]?.id).toBe("doc-a");
  expect(grouped.General?.[0]?.id).toBe("doc-b");
});
