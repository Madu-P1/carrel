import { useEffect } from "preact/hooks";

import { openFirstRunTour } from "@/features/onboarding/FirstRunTour";
import { openPalette } from "@/features/palette/CommandPalette";
import {
  readerState,
  requestReaderFind,
  requestReaderPage,
  setReaderFocusMode,
  setReaderScale,
  zoomReaderBy
} from "@/features/reader/state";
import { events } from "@/services/metrics/events";
import { onMenuCommand } from "@/services/native/menu";

import { openShortcutsOverlay } from "../ShortcutsOverlay";
import {
  appShell,
  navigateTo,
  pathnameFromRoute,
  toggleLeft,
  toggleRight,
  toggleTheme
} from "../useAppShell";

/**
 * Translate native macOS menu commands into in-app actions.
 *
 * The Swift side (NativeMenuBridge) emits string commands like
 * "nav.dashboard" or "view.zoomIn" through a window event; this hook
 * subscribes once on mount and returns the unsubscriber from
 * `onMenuCommand`. New menu items only need a case here — no extra
 * plumbing in AppShell itself.
 *
 * Reader-specific commands (focus mode, find, page navigation) gate on
 * the current route + readerState so they no-op outside the Reader.
 * That's safer than disabling the menu items: the Swift menu doesn't
 * know which route is active, so the no-op-when-not-applicable contract
 * stays here.
 */
export function useShellMenuCommands(): void {
  useEffect(() => {
    return onMenuCommand((cmd) => {
      switch (cmd) {
        case "nav.dashboard":
          navigateTo("/");
          break;
        case "nav.session":
          navigateTo("/session");
          break;
        case "nav.library":
          navigateTo("/library");
          break;
        case "nav.reader":
          navigateTo("/reader");
          break;
        case "nav.ask":
          navigateTo("/ask");
          break;
        case "nav.study":
          navigateTo("/study");
          break;
        case "nav.plan":
          navigateTo("/plan");
          break;
        case "view.toggleLeftSidebar":
          toggleLeft();
          break;
        case "view.toggleRightPanel":
          toggleRight();
          break;
        case "view.toggleTheme":
          toggleTheme();
          break;
        case "view.zoomIn":
          zoomReaderBy(0.1);
          break;
        case "view.zoomOut":
          zoomReaderBy(-0.1);
          break;
        case "view.zoomReset":
          setReaderScale(1);
          break;
        case "reader.toggleFocusMode": {
          const currentPath = pathnameFromRoute(appShell.currentRoute.value);
          if (currentPath.startsWith("/reader") && readerState.focusAvailable.value) {
            const enabled = !readerState.focusMode.value;
            setReaderFocusMode(enabled);
            void events.track("reader.focus_toggled", { enabled }, "reader");
          }
          break;
        }
        case "reader.find": {
          const currentPath = pathnameFromRoute(appShell.currentRoute.value);
          if (currentPath.startsWith("/reader") && readerState.focusAvailable.value) {
            requestReaderFind();
          }
          break;
        }
        case "reader.nextPage":
          requestReaderPage(readerState.currentPage.value + 1);
          break;
        case "reader.prevPage":
          requestReaderPage(readerState.currentPage.value - 1);
          break;
        case "palette.open":
          openPalette();
          break;
        case "help.shortcuts":
          openShortcutsOverlay();
          break;
        case "help.open":
          openFirstRunTour();
          break;
        case "app.preferences":
          openPalette();
          break;
        case "file.new":
          navigateTo("/session");
          break;
        case "file.import":
          navigateTo("/library");
          window.setTimeout(() => {
            document.getElementById("library-import-input")?.click();
          }, 50);
          break;
      }
    });
  }, []);
}
