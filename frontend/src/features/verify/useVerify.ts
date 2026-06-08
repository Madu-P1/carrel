import { useEffect, useRef, useState } from "preact/hooks";

import {
  briefs as briefsApi,
  verify as verifyApi,
  type VerifyResponse
} from "@/services/api/endpoints";

import { type CertificationModel } from "./certification";
import { initialStreamState, reduceStreamEvent, type VerifyStreamState } from "./streamProgress";

/**
 * The verification engine: the data lifecycle of a single check, whether freshly
 * run from a draft or re-hydrated from a saved brief. It hides the streaming
 * reduction loop, abort handling, the brief fetch, and the seal-seed lifecycle
 * behind one small interface — `verify(text)` plus read-only state — so both
 * hosts (Carrel's VerifyView and the Cachet lectern) drive the same machine
 * without duplicating any of it.
 *
 * What lives HERE is the data: response, stream, loading, error, and the seal
 * SEEDS a reopened brief carries (cleared on every fresh verify). What does NOT
 * live here is the verdict-render interaction state (selection, the open
 * certification exhibit, the human's session seal) — that is tightly coupled to
 * the render and lives in `VerifyResults`.
 */
export interface VerifyEngine {
  response: VerifyResponse | null;
  stream: VerifyStreamState;
  loading: boolean;
  hydrating: boolean;
  error: string | null;
  /** Stored seal fingerprint when a reopened brief was sealed; cleared on verify. */
  sealedSeed: string | null;
  /** Stored certification timestamp from a reopened brief; cleared on verify. */
  certAtSeed: string | null;
  /** The draft text of the last hydrated brief, or null on the live flow. The
   *  host seeds its composer (editable in VerifyView, read-only in the reader). */
  hydratedDraft: string | null;
  verify: (text: string) => Promise<void>;
}

export function useVerify(
  { docIds, briefId }: { docIds?: string[]; briefId?: string | null } = {}
): VerifyEngine {
  const [response, setResponse] = useState<VerifyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stream, setStream] = useState<VerifyStreamState>(initialStreamState);
  const [sealedSeed, setSealedSeed] = useState<string | null>(null);
  const [certAtSeed, setCertAtSeed] = useState<string | null>(null);
  const [hydrating, setHydrating] = useState(false);
  const [hydratedDraft, setHydratedDraft] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Open a saved brief: re-hydrate the settled state from the STORED response with
  // NO re-verify. The fetch uses `hydrating` (not `loading`) so the live-verify
  // chrome ("Verifying…") never shows on the no-verify open path. Keyed on briefId.
  useEffect(() => {
    if (!briefId) return;
    let live = true;
    const ctrl = new AbortController();
    setHydrating(true);
    setError(null);
    briefsApi
      .get(briefId, { signal: ctrl.signal })
      .then((detail) => {
        if (!live) return;
        // BriefDetail.response/.cert are loose dicts on the wire (the /api/briefs
        // route stores them verbatim, no response_model tightening). Cast once
        // here, the single hydration seam; the render subtree sits under the
        // per-route ErrorBoundary if a stored blob ever drifts from the shape.
        setResponse(detail.response as unknown as VerifyResponse);
        setHydratedDraft(detail.draft);
        const storedCert = (detail.cert ?? null) as CertificationModel | null;
        setCertAtSeed(storedCert?.generatedAtISO ?? null);
        setSealedSeed(detail.seal_state === "sealed" ? detail.fingerprint : null);
      })
      .catch((e) => {
        if (live) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (live) setHydrating(false);
      });
    return () => {
      live = false;
      ctrl.abort();
    };
  }, [briefId]);

  const verify = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setResponse(null);
    // A fresh check is a NEW verification: drop any reopened brief's stored seal
    // and date so the fresh result can never export the prior brief's seal or
    // timestamp (the seeds survive only an untouched re-export of that brief).
    setSealedSeed(null);
    setCertAtSeed(null);
    let live = initialStreamState();
    setStream(live);
    try {
      for await (const event of verifyApi.draftStream(
        { draft: trimmed, doc_ids: docIds && docIds.length > 0 ? docIds : undefined },
        { signal: controller.signal }
      )) {
        live = reduceStreamEvent(live, event);
        setStream(live);
        if (event.type === "result") {
          setResponse(event.verify);
        } else if (event.type === "error") {
          // Surfaced engine/transport error: show it, never a partial pass.
          setError(event.error);
        }
      }
      // Stream ended without a result event (dropped/truncated). The settled
      // view stays empty rather than reading any un-checked claim as a pass.
      if (live.phase !== "done" && !controller.signal.aborted && !live.error) {
        setError(
          "Verification did not finish. No verdict was produced; nothing was marked supported. Verify the draft again."
        );
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : String(e));
        setResponse(null);
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setLoading(false);
    }
  };

  return {
    response,
    stream,
    loading,
    hydrating,
    error,
    sealedSeed,
    certAtSeed,
    hydratedDraft,
    verify
  };
}
