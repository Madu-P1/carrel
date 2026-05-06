import { anchors } from "@/services/api/endpoints";

import type { CitationRecord } from "./types";

export const ASK_ANCHOR_DRAFTS_STORAGE_KEY = "einstein.ask.anchor-drafts";

export interface AskAnchorDraft {
  id: string;
  title: string;
  body: string;
  sourceKind: "answer-summary" | "claim" | "fallback-passage";
  citation: {
    chunkId: string | null;
    documentId: string | null;
    documentName: string | null;
    pageNum: number | null;
  };
  savedAt: string;
}

interface SaveAskAnchorDraftInput {
  title: string;
  body: string;
  sourceKind: AskAnchorDraft["sourceKind"];
  citation?: CitationRecord | null;
}

function safeLocalStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function readDrafts(): AskAnchorDraft[] {
  const storage = safeLocalStorage();
  if (!storage) {
    return [];
  }

  try {
    const raw = storage.getItem(ASK_ANCHOR_DRAFTS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as AskAnchorDraft[]) : [];
  } catch {
    return [];
  }
}

function writeDrafts(drafts: AskAnchorDraft[]): void {
  const storage = safeLocalStorage();
  if (!storage) {
    throw new Error("storage_unavailable");
  }
  storage.setItem(ASK_ANCHOR_DRAFTS_STORAGE_KEY, JSON.stringify(drafts));
}

export function saveAskAnchorDraft({
  title,
  body,
  sourceKind,
  citation
}: SaveAskAnchorDraftInput): { draft: AskAnchorDraft; status: "created" | "updated" } {
  const chunkId = citation?.chunk_id ?? null;
  const documentId = citation?.document_id ?? null;
  const dedupeId = [sourceKind, documentId ?? "no-doc", chunkId ?? "no-chunk", title].join("::");
  const draft: AskAnchorDraft = {
    id: dedupeId,
    title,
    body,
    sourceKind,
    citation: {
      chunkId,
      documentId,
      documentName: citation?.document_name ?? null,
      pageNum: citation?.page_num ?? null
    },
    savedAt: new Date().toISOString()
  };

  const existing = readDrafts();
  const next = existing.filter((item) => item.id !== draft.id);
  const status = next.length === existing.length ? "created" : "updated";
  writeDrafts([draft, ...next]);
  return { draft, status };
}

export async function copyAskCardText(text: string): Promise<void> {
  if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
    throw new Error("clipboard_unavailable");
  }
  await navigator.clipboard.writeText(text);
}

export async function saveCitationAnchor({
  citation,
  claimText,
  quoteText,
  sourceKind
}: {
  citation?: CitationRecord | null;
  claimText: string;
  quoteText: string;
  sourceKind: AskAnchorDraft["sourceKind"];
}) {
  if (!citation?.document_id) {
    return saveAskAnchorDraft({
      title: claimText,
      body: quoteText,
      sourceKind,
      citation
    });
  }
  const response = await anchors.create({
    document_id: citation.document_id,
    chunk_id: citation.chunk_id ?? null,
    page_num: citation.page_num ?? null,
    quote_text: quoteText || citation.snippet || citation.content || claimText,
    claim_text: claimText,
    origin: "ai_answer_citation",
    confidence: citation.score ?? 0.7
  });
  return { anchor: response.anchor, status: "created" as const };
}
