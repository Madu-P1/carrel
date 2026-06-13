import { useEffect, useRef } from "preact/hooks";

interface PriorState {
  el: Element;
  hadInert: boolean;
  ariaHidden: string | null;
}

/** Make one element inert (and aria-hidden), returning its prior state so the
 *  exact attributes can be restored. `inert` alone suffices in modern WebKit
 *  (the WKWebView target); aria-hidden is belt-and-suspenders for AT that lag. */
export function applyInert(el: Element): PriorState {
  const prior: PriorState = {
    el,
    hadInert: el.hasAttribute("inert"),
    ariaHidden: el.getAttribute("aria-hidden")
  };
  el.setAttribute("inert", "");
  el.setAttribute("aria-hidden", "true");
  return prior;
}

/** Restore an element to the state captured by applyInert. */
export function restoreInert(prior: PriorState): void {
  if (!prior.hadInert) {
    prior.el.removeAttribute("inert");
  }
  if (prior.ariaHidden === null) {
    prior.el.removeAttribute("aria-hidden");
  } else {
    prior.el.setAttribute("aria-hidden", prior.ariaHidden);
  }
}

/**
 * Make every SIBLING of `node` inert and return an un-inert cleanup. This is the
 * background-inert half of the aria-modal contract: an overlay rendered as a
 * sibling of the app's rail and main (the Cachet shell layout) promises AT users
 * the background is inert. Scoping to the overlay's own siblings keeps it from
 * coupling to specific class names. Used by useModalDialog, which sequences it
 * against focus capture/restore so the inert background never strands focus.
 */
export function inertSiblings(node: Element): () => void {
  const parent = node.parentElement;
  if (!parent) {
    return () => {};
  }
  const touched = Array.from(parent.children)
    .filter((sibling) => sibling !== node)
    .map(applyInert);
  return () => touched.forEach(restoreInert);
}

/**
 * Mark the referenced node inert (and aria-hidden) while `active`, restoring its
 * prior attributes on deactivate. Use for a persistently-mounted panel that must
 * stay out of the tab order and the a11y tree while it is closed: a focusable
 * control left inside an aria-hidden-but-tabbable subtree can strand focus, which
 * `inert` prevents because it also removes the subtree from sequential focus
 * (WCAG 4.1.2). Returns the ref to attach to the node.
 */
export function useInert<T extends HTMLElement>(active: boolean) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || !active) {
      return undefined;
    }
    const prior = applyInert(node);
    return () => restoreInert(prior);
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  return ref;
}
