import { signal, type Signal } from "@preact/signals";
import { useEffect, useRef } from "preact/hooks";

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
 *
 * STATE STORAGE: the data lives in a `VerifyStore` of signals, not useState.
 * By default each useVerify call gets its own fresh store (per-instance, the
 * original behavior — Carrel's VerifyView and the BriefReader are unchanged).
 * A host may pass a module-scope store instead so the engine state survives
 * the Cachet shell's unmount-on-nav: the lectern does this (liveVerify.ts), so
 * a verdict — settled or still streaming — is not destroyed by one rail click.
 * Signals also make a mid-verify unmount safe: the stream loop writes to the
 * external store, not to an unmounted component's state.
 */
export interface VerifyEngine {
  response: VerifyResponse | null;
  stream: VerifyStreamState;
  loading: boolean;
  hydrating: boolean;
  error: string | null;
  /** Seal fingerprint: seeded from a reopened sealed brief, or recorded by
   *  markSealed when the human seals live. Cleared on every fresh verify. */
  sealedSeed: string | null;
  /** Certification timestamp: seeded from a reopened brief's stored cert, or
   *  recorded by markSealed at live-seal time so a reopened exhibit re-renders
   *  the ORIGINAL date, never a fresh one. Cleared on every fresh verify. */
  certAtSeed: string | null;
  /** The draft text of the last hydrated brief, or null on the live flow. The
   *  host seeds its composer (editable in VerifyView, read-only in the reader). */
  hydratedDraft: string | null;
  verify: (text: string) => Promise<void>;
  /** Record a LIVE seal (the human clicked Set the seal) on the engine, so a
   *  persistent-store host still hides the quiet unsealed Save after a remount.
   *  Without this, seal -> navigate away -> return would re-show Save to Shelf,
   *  whose backend upsert silently downgrades the seal (the exact path the
   *  hide-on-sealed guard exists to forbid). Records the PAIR the hydration
   *  path seeds together: the fingerprint AND the certification timestamp, so
   *  a reopened exhibit re-renders the original seal date rather than minting
   *  a fresh one onto a filing-grade artifact. */
  markSealed: (fingerprint: string, generatedAtISO: string) => void;
  /** Abort the in-flight check, if any. The honest escape hatch: with a
   *  persistent store a hung stream would otherwise leave loading=true across
   *  every navigation (the remount no longer resets it), permanently disabling
   *  Verify. Cancelling settles to the idle state: no verdict, no error. */
  cancel: () => void;
}

/** The engine's state, as signals so it can outlive any one component. */
export interface VerifyStore {
  response: Signal<VerifyResponse | null>;
  stream: Signal<VerifyStreamState>;
  loading: Signal<boolean>;
  hydrating: Signal<boolean>;
  error: Signal<string | null>;
  sealedSeed: Signal<string | null>;
  certAtSeed: Signal<string | null>;
  hydratedDraft: Signal<string | null>;
  /** The in-flight check's controller. A plain mutable slot, not a signal:
   *  nothing renders from it. Lives in the store so an in-flight check stays
   *  supersedable across a host remount. */
  abort: { current: AbortController | null };
}

export function createVerifyStore(): VerifyStore {
  return {
    response: signal<VerifyResponse | null>(null),
    stream: signal<VerifyStreamState>(initialStreamState()),
    loading: signal(false),
    hydrating: signal(false),
    error: signal<string | null>(null),
    sealedSeed: signal<string | null>(null),
    certAtSeed: signal<string | null>(null),
    hydratedDraft: signal<string | null>(null),
    abort: { current: null }
  };
}

/** Return a persistent store to its boot state (aborting any in-flight check).
 *  For "start a new verification" affordances and test isolation. */
export function resetVerifyStore(store: VerifyStore): void {
  store.abort.current?.abort();
  store.abort.current = null;
  store.response.value = null;
  store.stream.value = initialStreamState();
  store.loading.value = false;
  store.hydrating.value = false;
  store.error.value = null;
  store.sealedSeed.value = null;
  store.certAtSeed.value = null;
  store.hydratedDraft.value = null;
}

export function useVerify(
  {
    docIds,
    briefId,
    store: externalStore
  }: { docIds?: string[]; briefId?: string | null; store?: VerifyStore } = {}
): VerifyEngine {
  // One store per hook instance unless the host supplies a persistent one.
  // Reading the signals below during render subscribes the host component, so
  // updates re-render it exactly as useState did.
  const storeRef = useRef<VerifyStore | null>(null);
  if (storeRef.current === null) storeRef.current = externalStore ?? createVerifyStore();
  const store = storeRef.current;

  // Open a saved brief: re-hydrate the settled state from the STORED response with
  // NO re-verify. The fetch uses `hydrating` (not `loading`) so the live-verify
  // chrome ("Verifying…") never shows on the no-verify open path. Keyed on briefId.
  useEffect(() => {
    if (!briefId) return;
    let live = true;
    const ctrl = new AbortController();
    store.hydrating.value = true;
    store.error.value = null;
    briefsApi
      .get(briefId, { signal: ctrl.signal })
      .then((detail) => {
        if (!live) return;
        // BriefDetail.response/.cert are loose dicts on the wire (the /api/briefs
        // route stores them verbatim, no response_model tightening). Cast once
        // here, the single hydration seam; the render subtree sits under the
        // per-route ErrorBoundary if a stored blob ever drifts from the shape.
        store.response.value = detail.response as unknown as VerifyResponse;
        store.hydratedDraft.value = detail.draft;
        const storedCert = (detail.cert ?? null) as CertificationModel | null;
        store.certAtSeed.value = storedCert?.generatedAtISO ?? null;
        store.sealedSeed.value = detail.seal_state === "sealed" ? detail.fingerprint : null;
      })
      .catch((e) => {
        if (live) store.error.value = e instanceof Error ? e.message : String(e);
      })
      .finally(() => {
        if (live) store.hydrating.value = false;
      });
    return () => {
      live = false;
      ctrl.abort();
    };
  }, [briefId, store]);

  const verify = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || store.loading.value) return;
    store.abort.current?.abort();
    const controller = new AbortController();
    store.abort.current = controller;
    store.loading.value = true;
    store.error.value = null;
    store.response.value = null;
    // A fresh check is a NEW verification: drop any reopened brief's stored seal
    // and date so the fresh result can never export the prior brief's seal or
    // timestamp (the seeds survive only an untouched re-export of that brief).
    store.sealedSeed.value = null;
    store.certAtSeed.value = null;
    let live = initialStreamState();
    store.stream.value = live;
    try {
      for await (const event of verifyApi.draftStream(
        { draft: trimmed, doc_ids: docIds && docIds.length > 0 ? docIds : undefined },
        { signal: controller.signal }
      )) {
        live = reduceStreamEvent(live, event);
        store.stream.value = live;
        if (event.type === "result") {
          store.response.value = event.verify;
        } else if (event.type === "error") {
          // Surfaced engine/transport error: show it, never a partial pass.
          store.error.value = event.error;
        }
      }
      // Stream ended without a result event (dropped/truncated). The settled
      // view stays empty rather than reading any un-checked claim as a pass.
      if (live.phase !== "done" && !controller.signal.aborted && !live.error) {
        store.error.value =
          "Verification did not finish. No verdict was produced; nothing was marked supported. Verify the draft again.";
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        store.error.value = e instanceof Error ? e.message : String(e);
        store.response.value = null;
      }
    } finally {
      // Ownership-guarded, BOTH writes: a superseded check (cancelled via
      // resetVerifyStore, with a successor already streaming) must not clear
      // the successor's loading flag as its own loop unwinds — that would drop
      // the "Verifying…" chrome mid-check and reopen the loading guard to a
      // third concurrent check writing the same store.
      if (store.abort.current === controller) {
        store.abort.current = null;
        store.loading.value = false;
      }
    }
  };

  return {
    response: store.response.value,
    stream: store.stream.value,
    loading: store.loading.value,
    hydrating: store.hydrating.value,
    error: store.error.value,
    sealedSeed: store.sealedSeed.value,
    certAtSeed: store.certAtSeed.value,
    hydratedDraft: store.hydratedDraft.value,
    verify,
    markSealed: (fingerprint: string, generatedAtISO: string) => {
      store.sealedSeed.value = fingerprint;
      store.certAtSeed.value = generatedAtISO;
    },
    cancel: () => {
      // The finally above owns the cleanup: abort unwinds the loop, the catch
      // swallows the AbortError, and the ownership-guarded finally clears the
      // slot and loading. Cancelling when idle is a no-op.
      store.abort.current?.abort();
    }
  };
}
