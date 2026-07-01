/**
 * Fetch a record's ORIGINAL bytes from the engine with the local-API token.
 *
 * The /api/documents/<id>/file route sits behind the PR-S1 token gate like
 * every other /api/* path, and a plain <iframe src> / pdf.js URL fetch would
 * not carry the header, so the bytes travel through an explicit fetch here.
 * Loopback only (API_BASE is 127.0.0.1); nothing leaves the machine.
 */
import { API_BASE, LOCAL_TOKEN_HEADER, resolveLocalApiToken } from "@/services/api/client";

export function documentFileUrl(docId: string): string {
  return `${API_BASE}/api/documents/${encodeURIComponent(docId)}/file`;
}

export async function authHeaders(): Promise<Record<string, string> | undefined> {
  const token = await resolveLocalApiToken();
  return token ? { [LOCAL_TOKEN_HEADER]: token } : undefined;
}

export async function fetchDocumentFile(docId: string): Promise<ArrayBuffer> {
  const headers = await authHeaders();
  let response: Response;
  try {
    response = await fetch(documentFileUrl(docId), { headers });
  } catch {
    throw new Error("The engine is not reachable. Start Cachet's engine, then reopen the record.");
  }
  if (response.status === 404) {
    throw new Error("The original file for this record is no longer in the Vault.");
  }
  if (!response.ok) {
    throw new Error(`The record file could not be opened (HTTP ${response.status}).`);
  }
  let bytes: ArrayBuffer;
  try {
    bytes = await response.arrayBuffer();
  } catch {
    throw new Error("The record file could not be read from the engine.");
  }
  if (bytes.byteLength === 0) {
    throw new Error("The original file for this record is empty.");
  }
  return bytes;
}
