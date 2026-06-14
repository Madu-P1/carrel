import { useEffect, useRef } from "preact/hooks";

/**
 * The canonical focusable-element query, shared so the modal surfaces all agree
 * on what "focusable" means. Extracted from the Dialog primitive (which still
 * owns its own Escape + outside-press lifecycle) so the bespoke Cachet overlays
 * trap the same set the primitive does instead of each re-deriving a selector.
 */
export function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
  ).filter((element) => !element.hasAttribute("disabled"));
}

/**
 * Keep Tab inside `panel`: wrap in both directions, and either direction also
 * pulls focus back in when `document.activeElement` has drifted outside the
 * panel (a stray scrim click, a control the background has not yet been made
 * inert). Pure so both useFocusTrap and useModalDialog share one trap.
 */
export function trapTabWithin(panel: HTMLElement, event: KeyboardEvent): void {
  if (event.key !== "Tab") {
    return;
  }
  const focusable = getFocusable(panel);
  if (focusable.length === 0) {
    event.preventDefault();
    panel.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const current = document.activeElement as HTMLElement | null;
  const outside = !panel.contains(current);
  if (event.shiftKey) {
    if (current === first || outside) {
      event.preventDefault();
      last.focus();
    }
  } else if (current === last || outside) {
    event.preventDefault();
    first.focus();
  }
}

/**
 * Focus lifecycle for a modal panel that does NOT inert a background (the cited-
 * passage overlay, whose background is the drawer stack it does not own): while
 * `active`, capture the element that had focus, move focus into the panel, and
 * trap Tab so it wraps inside. On deactivate (or unmount) restore focus to the
 * captured opener. Keeps focus only; the caller keeps its own Escape handling
 * (capture phase + stopImmediatePropagation, so a stack of overlays peels one
 * layer per keypress). For a modal that ALSO inerts its background, use
 * useModalDialog instead — the capture/inert/restore ordering is load-bearing
 * there and must live in one hook. Returns the ref to attach to the panel
 * (WCAG 2.4.3 / 4.1.2).
 */
export function useFocusTrap<T extends HTMLElement>(active: boolean) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    if (!active) {
      return undefined;
    }

    const restoreTo = document.activeElement as HTMLElement | null;
    const panel = ref.current;
    if (panel) {
      const [first] = getFocusable(panel);
      (first ?? panel).focus();
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (ref.current) {
        trapTabWithin(ref.current, event);
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      restoreTo?.focus?.();
    };
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  return ref;
}
