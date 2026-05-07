import { useEffect } from "preact/hooks";

import { focusAskInput } from "@/features/ask/focusRegistry";
import { readerState, setReaderFocusMode } from "@/features/reader/state";
import { events } from "@/services/metrics/events";

import {
  closeShortcutsOverlay,
  openShortcutsOverlay,
  shortcutsOverlayOpen
} from "../ShortcutsOverlay";
import { navigateTo } from "../useAppShell";

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

/**
 * Global keyboard shortcuts. Three rules:
 *   1. Never intercept when the user is typing in an input, textarea,
 *      or contenteditable. We don't want `/` or `?` to swallow keystrokes
 *      inside the Ask box.
 *   2. Never intercept when a modifier is held (⌘/ctrl/alt) — those are
 *      either a different shortcut or OS-level.
 *   3. Esc is the universal "close overlay" — preferred over per-component
 *      listeners so overlay stacking can never trap the user.
 *
 * Active bindings:
 *   - Esc → close shortcuts overlay if open, else exit reader focus mode
 *   - `?` → toggle the shortcuts overlay
 *   - `/` → navigate to /ask and focus the question input (Linear/GitHub idiom)
 */
interface NativeCompanionBridge {
  setState?: (state: string) => void;
}

/**
 * Cycle the floating companion through four states for marketing
 * recordings. Triggered by Cmd+Shift+Option+R from anywhere in the
 * app. Hidden from the shortcut overlay because it is a dev/asset-
 * capture affordance, not a user-facing feature. Sequence: idle 3s,
 * thinking 3s, encouraging 3s, sleeping 2.5s. Total 11.5s — fits the
 * landing-page section spec.
 */
function cycleCompanionForRecording(): void {
  const bridge = (window as unknown as { nativeCompanion?: NativeCompanionBridge })
    .nativeCompanion;
  if (!bridge?.setState) {
    return;
  }
  const setState = bridge.setState.bind(bridge);
  const sequence: Array<{ state: string; holdMs: number }> = [
    { state: "idle", holdMs: 3000 },
    { state: "thinking", holdMs: 3000 },
    { state: "encouraging", holdMs: 3000 },
    { state: "sleeping", holdMs: 2500 }
  ];
  let cumulative = 0;
  for (const step of sequence) {
    window.setTimeout(() => setState(step.state), cumulative);
    cumulative += step.holdMs;
  }
}

export function useGlobalShortcuts(): void {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      // Hidden recording shortcut — Cmd+Shift+Option+R fires the
      // companion-states cycle. Checked before the modifier-bail
      // because it deliberately requires three modifiers held.
      if (
        (event.metaKey || event.ctrlKey) &&
        event.shiftKey &&
        event.altKey &&
        (event.key === "r" || event.key === "R")
      ) {
        event.preventDefault();
        cycleCompanionForRecording();
        return;
      }

      if (event.metaKey || event.ctrlKey || event.altKey) return;

      // Esc always closes the shortcuts overlay if it's open. Guard is
      // here rather than inside the overlay so we win over any other
      // keydown listener that might `stopPropagation()`.
      if (event.key === "Escape" && shortcutsOverlayOpen.value) {
        event.preventDefault();
        closeShortcutsOverlay();
        return;
      }

      if (event.key === "Escape" && readerState.focusMode.value) {
        event.preventDefault();
        setReaderFocusMode(false);
        void events.track("reader.focus_toggled", { enabled: false }, "reader");
        return;
      }

      if (isEditableTarget(event.target)) return;

      if (event.key === "?") {
        event.preventDefault();
        if (shortcutsOverlayOpen.value) {
          closeShortcutsOverlay();
        } else {
          openShortcutsOverlay();
        }
        return;
      }

      if (event.key === "/") {
        event.preventDefault();
        navigateTo("/ask");
        window.setTimeout(() => {
          focusAskInput();
        }, 60);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
}
