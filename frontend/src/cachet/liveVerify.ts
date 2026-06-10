/**
 * The live verification on the lectern (the verify surface).
 *
 * Same survival story as liveDraft: the Cachet shell swaps views by route,
 * UNMOUNTING the current view on every move, so engine state held per-instance
 * is destroyed the moment the user clicks off to the Shelf or the Vault. For
 * the draft that lost a paste; for the engine it lost the whole VERDICT — a
 * lawyer mid-review was one rail click from re-running the entire check.
 *
 * This module-scope store backs the lectern's useVerify, so the verdict
 * (settled or still streaming — the stream loop writes to these signals, not
 * to component state) survives navigation. Cleared on a fresh app launch, or
 * explicitly via resetVerifyStore. Only the lectern uses it: the BriefReader
 * and Carrel's VerifyView keep their own per-instance stores.
 */
import { createVerifyStore } from "@/features/verify/useVerify";

export const lecternVerify = createVerifyStore();
