import { expect, test } from "vitest";

import { buildAskUrl, readAskQueryParams, scopeFromRoute } from "../../src/features/ask/askRoute";

test("buildAskUrl preserves complete document scope for auto-submit", () => {
  const url = buildAskUrl({
    q: " Explain capex ",
    auto: true,
    scope_kind: "document",
    doc_id: "doc-1"
  });

  expect(url).toBe("/ask?q=Explain+capex&auto=1&scope_kind=document&doc_id=doc-1");
});

test("buildAskUrl drops incomplete scoped auto-submit state", () => {
  expect(buildAskUrl({ q: "", auto: true, scope_kind: "document" })).toBe("/ask");
  expect(buildAskUrl({ q: "Explain", auto: true, scope_kind: "document" })).toBe(
    "/ask?q=Explain&auto=1"
  );
});

test("readAskQueryParams and scopeFromRoute preserve subject scope", () => {
  const params = readAskQueryParams("/ask?q=Margins&auto=true&scope_kind=subject&subject_name=Finance");
  const scope = scopeFromRoute(params, []);

  expect(params.question).toBe("Margins");
  expect(params.auto).toBe(true);
  expect(scope).toMatchObject({
    kind: "subject",
    subjectName: "Finance",
    readiness: "ready"
  });
});

test("scopeFromRoute resolves document title when documents are available", () => {
  const params = readAskQueryParams("/ask?q=Margins&scope_kind=document&doc_id=doc-1");
  const scope = scopeFromRoute(params, [{ id: "doc-1", filename: "Chapter 8.pdf" }]);

  expect(scope).toMatchObject({
    kind: "document",
    docId: "doc-1",
    docTitle: "Chapter 8.pdf",
    readiness: "ready"
  });
});
