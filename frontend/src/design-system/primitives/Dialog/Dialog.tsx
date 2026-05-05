import { useEffect, useId, useRef } from "preact/hooks";
import type { ComponentChildren } from "preact";

import styles from "./Dialog.module.css";

function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
  ).filter((element) => !element.hasAttribute("disabled"));
}

export interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children?: ComponentChildren;
  actions?: ComponentChildren;
}

export function Dialog({
  open,
  title,
  description,
  onClose,
  children,
  actions
}: DialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    restoreFocusRef.current = document.activeElement as HTMLElement | null;

    const node = dialogRef.current;
    if (node) {
      const [firstFocusable] = getFocusable(node);
      // preventScroll: focusing inside the dialog must not scroll the
      // page behind it. Without this, opening the dialog while
      // scrolled (e.g., picking a calendar event from the time grid)
      // jumps the page to wherever the dialog or its first focusable
      // sits in the document.
      (firstFocusable ?? node).focus({ preventScroll: true });
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }

      const focusable = getFocusable(dialogRef.current);
      if (focusable.length === 0) {
        event.preventDefault();
        dialogRef.current.focus();
        return;
      }

      const currentIndex = focusable.indexOf(document.activeElement as HTMLElement);
      let nextIndex = currentIndex;

      if (event.shiftKey) {
        nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
      } else {
        nextIndex = currentIndex === focusable.length - 1 ? 0 : currentIndex + 1;
      }

      event.preventDefault();
      focusable[nextIndex].focus();
    };

    const onOutsidePress = (event: MouseEvent | PointerEvent) => {
      const target = event.target;
      if (!node || !(target instanceof Node)) {
        return;
      }
      if (!node.contains(target)) {
        onClose();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onOutsidePress, true);
    document.addEventListener("mousedown", onOutsidePress, true);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onOutsidePress, true);
      document.removeEventListener("mousedown", onOutsidePress, true);
      restoreFocusRef.current?.focus({ preventScroll: true });
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div
        aria-describedby={description ? descriptionId : undefined}
        aria-labelledby={titleId}
        aria-modal="true"
        className={styles.dialog}
        onClick={(event) => event.stopPropagation()}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className={styles.header}>
          <h2 className={styles.title} id={titleId}>
            {title}
          </h2>
          {description ? (
            <p className={styles.description} id={descriptionId}>
              {description}
            </p>
          ) : null}
        </header>
        <div className={styles.body}>{children}</div>
        {actions ? <footer className={styles.footer}>{actions}</footer> : null}
      </div>
    </div>
  );
}
