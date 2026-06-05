/**
 * The live draft text, shared by the lectern and the verify station.
 *
 * The Cachet shell swaps views by route (no router is registered, so navigation
 * just sets `appShell.currentRoute`), which UNMOUNTS the current view on every
 * move. A draft kept in a component's own `useState` is therefore destroyed the
 * moment the user clicks off to the Shelf, Sources, etc. — paste on the lectern,
 * glance at the Shelf, come back, and the paste is gone.
 *
 * Holding the draft in this module-scope signal makes it survive navigation: every
 * surface that edits the draft writes here, every surface that shows it seeds from
 * here, so the lectern and the verify station share one durable draft. Cleared only
 * on a fresh app launch.
 *
 * Distinct from `pendingDraft` (the consume-once lectern -> /verify hand-off that
 * ALSO triggers the one-shot auto-run): this signal is the durable text; that one
 * is the one-shot "run the check now" lever.
 */
import { signal } from "@preact/signals";

export const liveDraft = signal<string>("");
