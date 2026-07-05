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

/**
 * Draft-file provenance when the current draft came from an uploaded DOCUMENT
 * (via /api/verify/extract-draft), else null. Holds the original filename, the
 * raw-file sha256, and the extraction identity so the certificate can name
 * BOTH artifacts (honesty law: verify exactly the extracted text, name the
 * file it came from and how it was read).
 *
 * Module-scope like liveDraft so it survives the shell's unmount-on-nav. The
 * ONE rule that keeps it honest: any manual edit to the draft text drops it,
 * because once the visible text no longer matches the extracted bytes, the
 * file hash would be a lie. The Lectern clears it on every textarea edit.
 */
export interface LiveDraftProvenance {
  filename: string;
  fileSha256: string;
  extractor: string;
}

export const liveDraftProvenance = signal<LiveDraftProvenance | null>(null);
