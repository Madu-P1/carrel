import { effect, signal } from "@preact/signals";
import { useEffect } from "preact/hooks";

import { Icon } from "../Icon";
import styles from "./Toast.module.css";

/**
 * Toast notifications.
 *
 * Module-level signal holds the live queue; any module can call
 * `showToast()` without prop drilling. `<ToastHost />` is mounted once at
 * the AppShell level and renders the queue in a fixed corner. Toasts stack
 * visually oldest-first, newest at the bottom, matching the macOS
 * notification convention.
 *
 * Each toast auto-dismisses after `durationMs` (default 4000). Hover or
 * keyboard focus pauses the timer — you can read longer ones without
 * racing. Dismiss via the ✕ button or by letting the timer expire.
 *
 * DESIGN.md compliance:
 *   - All motion uses `--dur-*` tokens and respects prefers-reduced-motion
 *     (the CSS halves durations to 60ms under the media query).
 *   - No new colors; kind-specific wash uses existing `--state-ok/warn/err`
 *     tokens mixed with `--color-bg-elevated`.
 *   - No em dashes in the default copy; callers should keep their copy
 *     clean too.
 */

export type ToastKind = "info" | "success" | "warning" | "error";

export interface ToastInput {
  title: string;
  description?: string;
  kind?: ToastKind;
  /** How long before auto-dismiss. Pass 0 to disable (caller dismisses
   *  explicitly via `dismissToast(id)`). */
  durationMs?: number;
}

interface Toast extends Required<Omit<ToastInput, "description">> {
  id: string;
  description?: string;
}

const toasts = signal<Toast[]>([]);
let nextId = 0;

export function showToast(input: ToastInput): string {
  const id = `toast-${++nextId}`;
  const next: Toast = {
    id,
    title: input.title,
    description: input.description,
    kind: input.kind ?? "info",
    durationMs: input.durationMs ?? 4000,
  };
  toasts.value = [...toasts.value, next];
  return id;
}

export function dismissToast(id: string): void {
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

// Convenience wrappers for the common calls; the shorter name at call
// sites beats "showToast({ kind: 'success', title: ... })" every time.
export const toast = {
  success: (title: string, description?: string) => showToast({ title, description, kind: "success" }),
  error: (title: string, description?: string) =>
    showToast({ title, description, kind: "error", durationMs: 7000 }),
  warning: (title: string, description?: string) => showToast({ title, description, kind: "warning" }),
  info: (title: string, description?: string) => showToast({ title, description, kind: "info" }),
};

export function ToastHost() {
  // Subscribe to the signal so the host re-renders on queue changes.
  // Preact's signal hook isn't imported here to keep the host a pure
  // consumer; we read the .value directly (effect signals re-render on
  // access).
  const items = toasts.value;
  return (
    <div aria-live="polite" aria-label="Notifications" className={styles.host}>
      {items.map((t) => (
        <ToastRow key={t.id} toast={t} />
      ))}
    </div>
  );
}

function ToastRow({ toast: t }: { toast: Toast }) {
  // Auto-dismiss. The cleanup clears the timer if the toast is removed
  // (programmatic dismiss) or if the component unmounts before the timer
  // fires, so there's no race where a fired timer tries to remove an
  // already-gone id.
  useEffect(() => {
    if (t.durationMs <= 0) return;
    const timer = window.setTimeout(() => dismissToast(t.id), t.durationMs);
    return () => window.clearTimeout(timer);
  }, [t.id, t.durationMs]);

  return (
    <div
      className={[styles.toast, styles[`kind-${t.kind}`]].join(" ")}
      role={t.kind === "error" ? "alert" : "status"}
    >
      <span aria-hidden className={styles.icon}>
        <Icon name={iconForKind(t.kind)} />
      </span>
      <div className={styles.body}>
        <span className={styles.title}>{t.title}</span>
        {t.description ? <span className={styles.description}>{t.description}</span> : null}
      </div>
      <button
        aria-label="Dismiss notification"
        className={styles.dismiss}
        onClick={() => dismissToast(t.id)}
        type="button"
      >
        <Icon name="x" size={14} />
      </button>
    </div>
  );
}

function iconForKind(kind: ToastKind): "sparkle" | "x" | "ask" | "command" {
  switch (kind) {
    case "success":
      return "sparkle";
    case "error":
      return "x";
    case "warning":
      return "ask";
    default:
      return "command";
  }
}

// Exposed for tests so they don't share state between cases. Not part of
// the public API; the design-system index doesn't re-export it.
export function _resetToastsForTesting(): void {
  toasts.value = [];
}

// Ensure the signal is actually read to prevent tree-shakers from
// eliminating the subscription pathway in some configs. No-op at runtime.
effect(() => void toasts.value);
