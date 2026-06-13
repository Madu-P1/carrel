import { useEffect, useRef } from "preact/hooks";

import { getFocusable, trapTabWithin } from "./useFocusTrap";
import { inertSiblings } from "./useInert";

/**
 * The full aria-modal lifecycle for a true modal whose background it inerts, in
 * the one order that does not strand focus. Attach the ref to the overlay ROOT
 * (the scrim): everything inside is the dialog, everything beside it is the
 * background to inert.
 *
 * The ordering is load-bearing and is exactly why this lives in ONE hook rather
 * than composing useFocusTrap + a sibling-inert hook. Two independent effects
 * cannot satisfy both constraints at once:
 *   - capture the opener BEFORE inerting the background, because inerting a
 *     subtree blurs the focused element inside it, so capturing after inert
 *     records <body> instead of the opener;
 *   - restore focus AFTER un-inerting, because .focus() on an element still
 *     inside an inert subtree is a no-op in WebKit (the WKWebView target), so
 *     restoring before un-inert drops focus to <body>.
 * On open: capture opener -> inert siblings -> focus first focusable -> trap Tab.
 * On close: un-inert siblings -> restore opener.
 *
 * Escape is intentionally NOT handled here: the examination overlays consume it
 * in the capture phase to peel a stack one layer per keypress, and the command
 * palette closes on its own Escape. Returns the ref for the scrim. (WCAG 2.4.3.)
 */
export function useModalDialog<T extends HTMLElement>(active: boolean) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    if (!active) {
      return undefined;
    }
    const scrim = ref.current;
    if (!scrim) {
      return undefined;
    }

    // 1) capture the opener BEFORE inert can blur it.
    const restoreTo = document.activeElement as HTMLElement | null;
    // 2) inert the background (the scrim's siblings).
    const unInert = inertSiblings(scrim);
    // 3) move focus into the dialog.
    const [first] = getFocusable(scrim);
    (first ?? scrim).focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (ref.current) {
        trapTabWithin(ref.current, event);
      }
    };
    document.addEventListener("keydown", onKeyDown, true);

    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      // un-inert FIRST so the opener is focusable again, THEN restore.
      unInert();
      restoreTo?.focus?.();
    };
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  return ref;
}
