/**
 * The live draft text on the lectern (the verify surface).
 *
 * The Cachet shell swaps views by route (no router is registered, so navigation
 * just sets `appShell.currentRoute`), which UNMOUNTS the current view on every
 * move. A draft kept in a component's own `useState` is therefore destroyed the
 * moment the user clicks off to the Shelf, Sources, etc. — paste on the lectern,
 * glance at the Shelf, come back, and the paste is gone.
 *
 * Holding the draft in this module-scope signal makes it survive navigation: the
 * lectern writes every edit here and seeds from here, so the draft is one durable
 * value across unmounts. Cleared only on a fresh app launch.
 */
import { signal } from "@preact/signals";

export const liveDraft = signal<string>("");
