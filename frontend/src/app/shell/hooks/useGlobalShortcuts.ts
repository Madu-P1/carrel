import { useEffect } from "preact/hooks";

import { toast } from "@/design-system";
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
 * recordings. Triggered by Cmd+Shift+0 (numeric zero) from anywhere
 * in the app. Hidden from the shortcut overlay because it is a dev/
 * asset-capture affordance. Sequence: idle 3s, thinking 3s,
 * encouraging 3s, sleeping 2.5s. Total 11.5s.
 *
 * Loud diagnostics: every step toasts so the founder can tell from
 * inside the running app whether the keypress fired, the bridge was
 * present, and each state landed. Quiet failure here makes recording
 * untestable, so we trade signal for noise during the asset capture.
 */
function cycleCompanionForRecording(): void {
  toast.info("Companion cycle started", "idle → thinking → encouraging → sleeping");
  const bridge = (window as unknown as { nativeCompanion?: NativeCompanionBridge })
    .nativeCompanion;
  if (!bridge?.setState) {
    toast.error(
      "Companion bridge missing",
      "window.nativeCompanion is undefined. Floating cube panel may not be running."
    );
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
    window.setTimeout(() => {
      setState(step.state);
      toast.info(`Companion → ${step.state}`, "");
    }, cumulative);
    cumulative += step.holdMs;
  }
}

export function useGlobalShortcuts(): void {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      // Hidden recording shortcut — Cmd+Shift+0 fires the
      // companion-states cycle. Checked before the modifier-bail
      // because it deliberately requires Cmd+Shift held. Numeric zero
      // chosen because Option doesn't remap it (Option+R produces ®
      // on US keyboards which can confuse event.key on some layouts);
      // also no conflict with any common macOS shortcut.
      if (
        (event.metaKey || event.ctrlKey) &&
        event.shiftKey &&
        (event.key === "0" || event.code === "Digit0")
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
