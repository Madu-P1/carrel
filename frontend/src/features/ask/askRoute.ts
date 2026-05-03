import type { AskScopeKind, AskScopeValue } from "./components/ScopePill";

export interface AskRouteParams {
  q: string;
  auto?: boolean;
  scope_kind?: AskScopeKind;
  doc_id?: string;
  subject_name?: string;
}

export interface ParsedAskRouteParams {
  question: string | null;
  auto: boolean;
  scopeKind: AskScopeKind;
  docId: string | null;
  subjectName: string | null;
  cacheKey: string;
}

export function buildAskUrl(params: AskRouteParams): string {
  const qs = new URLSearchParams();
  const question = params.q.trim();
  if (question) qs.set("q", question);
  if (question && params.auto) qs.set("auto", "1");

  const scopeKind = normalizeScopeKind(params.scope_kind ?? null);
  if (scopeKind === "document" && params.doc_id) {
    qs.set("scope_kind", "document");
    qs.set("doc_id", params.doc_id);
  } else if (scopeKind === "subject" && params.subject_name) {
    qs.set("scope_kind", "subject");
    qs.set("subject_name", params.subject_name);
  } else if (params.scope_kind === "library") {
    qs.set("scope_kind", "library");
  }

  const query = qs.toString();
  return query ? `/ask?${query}` : "/ask";
}

export function readAskQueryParams(rawPath: string): ParsedAskRouteParams {
  try {
    const fallback =
      typeof window !== "undefined"
        ? `${window.location.pathname}${window.location.search}`
        : "/ask";
    const url = new URL(rawPath && rawPath.includes("?") ? rawPath : fallback, "https://carrel.local");
    const q = url.searchParams.get("q");
    const auto = url.searchParams.get("auto");
    const scopeKind = normalizeScopeKind(url.searchParams.get("scope_kind"));
    const docId = cleanParam(url.searchParams.get("doc_id"));
    const subjectName = cleanParam(url.searchParams.get("subject_name"));
    const question = q && q.trim().length > 0 ? q : null;
    return {
      question,
      auto: auto === "1" || auto === "true",
      scopeKind,
      docId,
      subjectName,
      cacheKey: JSON.stringify({
        q: question,
        auto,
        scopeKind,
        docId,
        subjectName
      })
    };
  } catch {
    return {
      question: null,
      auto: false,
      scopeKind: "library",
      docId: null,
      subjectName: null,
      cacheKey: "empty"
    };
  }
}

export function scopeFromRoute(
  params: ParsedAskRouteParams,
  documents: Array<{ id: string; filename?: string | null }>,
): AskScopeValue {
  if (params.scopeKind === "document" && params.docId) {
    const doc = documents.find((item) => item.id === params.docId);
    return {
      kind: "document",
      docId: params.docId,
      docTitle: doc?.filename ?? undefined,
      readiness: "ready"
    };
  }
  if (params.scopeKind === "subject" && params.subjectName) {
    return {
      kind: "subject",
      subjectName: params.subjectName,
      readiness: "ready"
    };
  }
  return { kind: "library", readiness: "ready" };
}

function cleanParam(value: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function normalizeScopeKind(value: string | null): AskScopeKind {
  if (value === "document" || value === "subject" || value === "library") {
    return value;
  }
  return "library";
}
