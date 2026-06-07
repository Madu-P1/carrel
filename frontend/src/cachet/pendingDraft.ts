/**
 * Lectern hand-off (Cachet standalone shell).
 *
 * The lectern's sheet is the first paste, the "pull of the lever" in Loop 1.
 * When the user verifies from the lectern we stash the pasted draft here and
 * navigate to /verify; the verify view consumes it once on mount and runs the
 * check, so the user's paste IS the verify (never a second box).
 *
 * A plain module variable, not a signal, on purpose: CachetApp must NOT
 * subscribe to it (a subscribe-then-clear would remount the verify view and
 * drop the in-flight check). takePendingDraft() is consume-once.
 */
let pending: string | null = null;

export function stashPendingDraft(text: string): void {
  pending = text;
}

export function takePendingDraft(): string | null {
  const value = pending;
  pending = null;
  return value;
}
