import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { SubjectSection } from "@/features/library/components/SubjectSection";
import type { DocumentRow } from "@/services/api/endpoints";

const baseProps = {
  onDocumentDeleted: () => {},
  onSubjectRenamed: () => {},
  subject: "General",
};

const mockDoc: DocumentRow = {
  id: "doc-1",
  filename: "brief.pdf",
  summary: "",
  concept_count: 0,
  question_count: 0,
};

test("empty subject: renders the empty-state element", () => {
  render(<SubjectSection {...baseProps} documents={[]} />);
  expect(screen.getByTestId("subject-section-empty")).toBeTruthy();
});

test("populated subject: does not render the empty-state element", () => {
  render(<SubjectSection {...baseProps} documents={[mockDoc]} />);
  expect(screen.queryByTestId("subject-section-empty")).toBeNull();
});
