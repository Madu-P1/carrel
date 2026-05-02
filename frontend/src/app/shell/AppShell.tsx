import { useEffect, useRef } from "preact/hooks";
import { useLocation } from "preact-iso";
import type { ComponentChildren, JSX } from "preact";

import { Box, Button, Card, Divider, Icon, ScrollArea, Stack, Text, ToastHost } from "@/design-system";
import { WorkspaceSidebar, type SidebarNavItem } from "./WorkspaceSidebar";
import { CommandPalette, openPalette } from "@/features/palette/CommandPalette";
import { JobsTray } from "@/features/shell/JobsTray";
import { FirstRunTour, openFirstRunTour } from "@/features/onboarding/FirstRunTour";
import { focusAskInput } from "@/features/ask/focusRegistry";
import type { PaletteAction } from "@/features/palette/actions";
import { events } from "@/services/metrics/events";
import {
  requestReaderPage,
  requestReaderFind,
  readerState,
  setReaderFocusMode,
  setReaderScale,
  zoomReaderBy
} from "@/features/reader/state";
import { dispatchMenuCommand, onMenuCommand } from "@/services/native/menu";

import { BrandMark } from "./BrandMark";
import {
  ShortcutsOverlay,
  openShortcutsOverlay,
  closeShortcutsOverlay,
  shortcutsOverlayOpen
} from "./ShortcutsOverlay";
import { isColdBootMotionEnabled } from "./boot";
import {
  appShell,
  initializeTheme,
  navigateTo,
  pathnameFromRoute,
  registerNavigator,
  setLeftRailWidth,
  setCurrentRoute,
  setRightPanelWidth,
  SHELL_PANEL_WIDTHS,
  toggleLeft,
  toggleRight,
  toggleTheme
} from "./useAppShell";
import styles from "./AppShell.module.css";

interface AppShellProps {
  children?: ComponentChildren;
}

interface ShellFrameProps extends AppShellProps {
  navigate: (path: string) => void;
  path: string;
}

const navLinks: SidebarNavItem[] = [
  { key: "dashboard", label: "Dashboard", commandHint: "⌘1", icon: "dashboard", path: "/" },
  { key: "session", label: "Sessions", commandHint: "⌘2", icon: "sparkle", path: "/session" },
  { key: "library", label: "Library", commandHint: "⌘3", icon: "library", path: "/library" },
  { key: "reader", label: "Reader", commandHint: "⌘4", icon: "doc", path: "/reader" },
  { key: "ask", label: "Ask Library", commandHint: "⌘5", icon: "ask", path: "/ask" },
  { key: "study", label: "Review Queue", commandHint: "⌘6", icon: "study", path: "/study" },
  { key: "search", label: "Search", commandHint: "⌘7", icon: "search", path: "/search" },
  { key: "concepts", label: "Concepts", commandHint: "⌘8", icon: "graph", path: "/concepts" },
  { key: "plan", label: "Plan", commandHint: "⌘9", icon: "command", path: "/plan" }
];

const FIRST_LAUNCH_EVENT_KEY = "carrel.metrics.first-launch-recorded";

function routeLabel(path: string): string {
  if (path === "/") {
    return "Dashboard";
  }

  if (path.startsWith("/reader")) {
    return "Reader";
  }

  if (path.startsWith("/ask")) {
    return "Ask";
  }

  if (path.startsWith("/study")) {
    return "Study";
  }

  if (path.startsWith("/library")) {
    return "Library";
  }

  if (path.startsWith("/search")) {
    return "Search";
  }

  if (path.startsWith("/concepts")) {
    return "Concepts";
  }

  if (path.startsWith("/plan")) {
    return "Plan";
  }

  return "Workspace";
}

function routeMotionIndex(path: string): number {
  if (path === "/") return 0;
  if (path.startsWith("/session")) return 1;
  if (path.startsWith("/library")) return 2;
  if (path.startsWith("/reader")) return 3;
  if (path.startsWith("/ask")) return 4;
  if (path.startsWith("/study")) return 5;
  if (path.startsWith("/search")) return 6;
  if (path.startsWith("/concepts")) return 7;
  if (path.startsWith("/plan")) return 8;
  return 9;
}

function useRouteMotion(pathname: string): "backward" | "forward" | "none" {
  const previousPathRef = useRef(pathname);
  const previousIndexRef = useRef(routeMotionIndex(pathname));
  const motionRef = useRef<"backward" | "forward" | "none">("none");

  if (previousPathRef.current !== pathname) {
    const nextIndex = routeMotionIndex(pathname);
    if (nextIndex > previousIndexRef.current) {
      motionRef.current = "forward";
    } else if (nextIndex < previousIndexRef.current) {
      motionRef.current = "backward";
    } else {
      motionRef.current = "none";
    }
    previousPathRef.current = pathname;
    previousIndexRef.current = nextIndex;
  }

  return motionRef.current;
}

type ResizablePanel = "left" | "right";

function panelWidthFor(panel: ResizablePanel): number {
  return panel === "left"
    ? appShell.leftRailWidth.value
    : appShell.rightPanelWidth.value;
}

function setPanelWidth(panel: ResizablePanel, width: number): void {
  if (panel === "left") {
    setLeftRailWidth(width);
  } else {
    setRightPanelWidth(width);
  }
}

function resizeLimits(panel: ResizablePanel) {
  return panel === "left" ? SHELL_PANEL_WIDTHS.left : SHELL_PANEL_WIDTHS.right;
}

function DefaultRightPanelEmpty({ path }: { path: string }) {
  const isReader = path.startsWith("/reader");

  return (
    <Box border padding={4} radius={4} surface="elevated">
      <Stack gap={3}>
        <Stack gap={1}>
          <Text variant="h3" weight="semibold">
            {isReader ? "Source panel" : "Inspector"}
          </Text>
          <Text tone="secondary">
            {isReader
              ? "Document chunks, concepts, and deep links appear here once a source loads."
              : "Open a reader view to inspect chunk-level source detail."}
          </Text>
        </Stack>
        <Divider />
        <Stack gap={2}>
          <Text tone="secondary">Use ⌘B for the left sidebar.</Text>
          <Text tone="secondary">Use ⌘⌥B for the right panel.</Text>
          <Text tone="secondary">Use the Navigate menu to move between views.</Text>
        </Stack>
      </Stack>
    </Box>
  );
}

function ShellFrame({ children, navigate, path }: ShellFrameProps) {
  const isLeftOpen = appShell.leftOpen.value;
  const isRightOpen = appShell.rightOpen.value;
  const leftRailWidth = appShell.leftRailWidth.value;
  const rightPanelWidth = appShell.rightPanelWidth.value;
  const theme = appShell.theme.value;
  const pathname = pathnameFromRoute(path);
  const isReaderFocusMode = pathname.startsWith("/reader") && readerState.focusMode.value;
  const activeLabel = routeLabel(pathname);
  const routeMotion = useRouteMotion(pathname);
  const panelContent = appShell.rightPanelContent.value;
  const playBootMotion = isColdBootMotionEnabled();
  const shellSizingStyle = {
    "--left-rail-width": `${leftRailWidth}px`,
    "--right-panel-width": `${rightPanelWidth}px`
  } as JSX.CSSProperties;

  const startPanelResize = (
    panel: ResizablePanel,
    event: JSX.TargetedPointerEvent<HTMLDivElement>
  ) => {
    if (event.button !== 0) return;
    event.preventDefault();

    const startX = event.clientX;
    const startWidth = panelWidthFor(panel);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onPointerMove = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      const nextWidth = panel === "left"
        ? startWidth + delta
        : startWidth - delta;
      setPanelWidth(panel, nextWidth);
    };

    const stopResize = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  };

  const resizePanelFromKeyboard = (
    panel: ResizablePanel,
    event: JSX.TargetedKeyboardEvent<HTMLDivElement>
  ) => {
    const limits = resizeLimits(panel);
    const step = event.shiftKey ? 32 : 16;
    let nextWidth: number | null = null;

    switch (event.key) {
      case "ArrowLeft":
        nextWidth = panel === "left"
          ? panelWidthFor(panel) - step
          : panelWidthFor(panel) + step;
        break;
      case "ArrowRight":
        nextWidth = panel === "left"
          ? panelWidthFor(panel) + step
          : panelWidthFor(panel) - step;
        break;
      case "Home":
        nextWidth = limits.min;
        break;
      case "End":
        nextWidth = limits.max;
        break;
      default:
        return;
    }

    event.preventDefault();
    setPanelWidth(panel, nextWidth);
  };

  useEffect(() => {
    initializeTheme();
    try {
      if (window.localStorage.getItem(FIRST_LAUNCH_EVENT_KEY) !== "1") {
        window.localStorage.setItem(FIRST_LAUNCH_EVENT_KEY, "1");
        void events.track("app.first_launch", { theme: appShell.theme.value }, "app");
      }
    } catch {
      void events.track("app.first_launch", { theme: appShell.theme.value }, "app");
    }
  }, []);

  useEffect(() => {
    // Preserve "/" so it resolves to the Dashboard. The old rewrite here
    // silently redirected to /library and was the cause of "Dashboard click
    // does nothing."
    setCurrentRoute(path);
  }, [path]);

  useEffect(() => registerNavigator(navigate), [navigate]);

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

  // Global keyboard shortcuts — discoverability is via the `?` overlay.
  // Three rules:
  //   1. Never intercept when the user is typing in an input, textarea,
  //      or contenteditable. We don't want `/` or `?` to swallow keystrokes
  //      inside the Ask box.
  //   2. Never intercept when a modifier is held (⌘/ctrl/alt) — those are
  //      either a different shortcut or OS-level.
  //   3. Esc is the universal "close overlay" — preferred over per-component
  //      listeners so overlay stacking can never trap the user.
  useEffect(() => {
    const isEditableTarget = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) return false;
      if (target.isContentEditable) return true;
      const tag = target.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    };

    const handler = (event: KeyboardEvent) => {
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

      // `?` — show the shortcuts overlay. Toggle if already open.
      if (event.key === "?") {
        event.preventDefault();
        if (shortcutsOverlayOpen.value) {
          closeShortcutsOverlay();
        } else {
          openShortcutsOverlay();
        }
        return;
      }

      // `/` — focus the Ask input. Navigate to /ask if not already there,
      // then focus the field. Matches the cross-app "/ to search" idiom
      // from Linear, GitHub, Raycast.
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

  return (
    <div className={[styles.shell, isReaderFocusMode ? styles.readerFocusShell : ""].filter(Boolean).join(" ")}>
      <header
        className={[styles.topbar, playBootMotion ? styles.bootTopbar : ""]
          .filter(Boolean)
          .join(" ")}
      >
        <div className={styles.topbarTitle}>
          <BrandMark />
          <Stack gap={1}>
            <Text as="h1" variant="h2" weight="semibold">
              Carrel
            </Text>
            <Text tone="secondary">{activeLabel}</Text>
          </Stack>
        </div>
        <div className={styles.topbarActions}>
          <JobsTray />
          <Button
            aria-label="Replay first-run tour"
            leadingIcon={<Icon name="sparkle" />}
            onClick={() => openFirstRunTour()}
            variant="ghost"
          >
            Tour
          </Button>
          <Button
            aria-label="Toggle theme"
            leadingIcon={<Icon name="sparkle" />}
            onClick={() => toggleTheme()}
            variant="ghost"
          >
            Theme: {theme}
          </Button>
          <Button
            aria-label="Open command palette"
            keyHint="⌘K"
            leadingIcon={<Icon name="command" />}
            onClick={() => openPalette()}
            variant="secondary"
          >
            Commands
          </Button>
        </div>
      </header>

      <div className={styles.body} style={shellSizingStyle}>
        <aside
          // NOTE: the rail is NOT aria-hidden when collapsed, because the
          // BrandMark inside it is still a live control the user can
          // tab to / click to re-expand. Hiding the whole aside would
          // strip that control from the accessibility tree. Tests read
          // the `data-collapsed` attribute instead.
          className={[
            styles.leftRail,
            !isLeftOpen ? styles.leftRailCollapsed : "",
            isReaderFocusMode ? styles.leftRailFocusHidden : "",
            playBootMotion ? styles.bootLeftRail : ""
          ]
            .filter(Boolean)
            .join(" ")}
          data-collapsed={!isLeftOpen ? "true" : "false"}
          data-testid="left-sidebar"
        >
          <div className={styles.leftRailInner}>
            <Card
              className={styles.navCard}
              padding={isLeftOpen ? "md" : "sm"}
            >
              <WorkspaceSidebar
                collapsed={!isLeftOpen}
                pathname={pathname}
                items={navLinks}
                onNavigate={(path) => navigateTo(path)}
              />
            </Card>
          </div>
        </aside>
        <div
          aria-hidden={!isLeftOpen || isReaderFocusMode}
          aria-label="Resize navigation sidebar"
          aria-orientation="vertical"
          aria-valuemax={SHELL_PANEL_WIDTHS.left.max}
          aria-valuemin={SHELL_PANEL_WIDTHS.left.min}
          aria-valuenow={leftRailWidth}
          className={[
            styles.resizeHandle,
            styles.leftResizeHandle,
            !isLeftOpen || isReaderFocusMode ? styles.resizeHandleHidden : ""
          ]
            .filter(Boolean)
            .join(" ")}
          data-testid="left-resize-handle"
          onKeyDown={(event) => resizePanelFromKeyboard("left", event)}
          onPointerDown={(event) => startPanelResize("left", event)}
          role="separator"
          tabIndex={isLeftOpen && !isReaderFocusMode ? 0 : -1}
        />

        <main
          className={[styles.main, playBootMotion ? styles.bootMain : ""]
            .filter(Boolean)
            .join(" ")}
          data-testid="main-content"
        >
          <ScrollArea className={styles.mainInner}>
            <div
              className={[
                styles.pageTransition,
                routeMotion === "forward" ? styles.pageTransitionForward : "",
                routeMotion === "backward" ? styles.pageTransitionBackward : ""
              ]
                .filter(Boolean)
                .join(" ")}
              data-route-motion={routeMotion}
              data-testid="page-transition"
              key={pathname}
            >
              {children}
            </div>
          </ScrollArea>
        </main>
        <div
          aria-hidden={!isRightOpen || isReaderFocusMode}
          aria-label="Resize source panel"
          aria-orientation="vertical"
          aria-valuemax={SHELL_PANEL_WIDTHS.right.max}
          aria-valuemin={SHELL_PANEL_WIDTHS.right.min}
          aria-valuenow={rightPanelWidth}
          className={[
            styles.resizeHandle,
            styles.rightResizeHandle,
            !isRightOpen || isReaderFocusMode ? styles.resizeHandleHidden : ""
          ]
            .filter(Boolean)
            .join(" ")}
          data-testid="right-resize-handle"
          onKeyDown={(event) => resizePanelFromKeyboard("right", event)}
          onPointerDown={(event) => startPanelResize("right", event)}
          role="separator"
          tabIndex={isRightOpen && !isReaderFocusMode ? 0 : -1}
        />

        <aside
          aria-hidden={!isRightOpen}
          className={[
            styles.rightPanel,
            !isRightOpen ? styles.rightPanelCollapsed : "",
            isReaderFocusMode ? styles.rightPanelFocusHidden : "",
            playBootMotion ? styles.bootRightPanel : ""
          ]
            .filter(Boolean)
            .join(" ")}
          data-testid="right-panel"
        >
          <div className={styles.rightPanelInner}>
            {panelContent ?? <DefaultRightPanelEmpty path={pathname} />}
          </div>
        </aside>
      </div>
      <CommandPalette
        context={
          appShell.activeSession.value
            ? {
                activeSessionId: appShell.activeSession.value.id,
                activeSessionObjective: appShell.activeSession.value.objective
              }
            : undefined
        }
        onSelect={(action: PaletteAction) => {
          if (action.run) {
            action.run();
            return;
          }
          if (action.command) {
            dispatchMenuCommand(action.command);
          }
        }}
      />
      <ShortcutsOverlay />
      <FirstRunTour />
      <ToastHost />
    </div>
  );
}

export function AppShell({ children }: AppShellProps) {
  const { route, url } = useLocation();
  return (
    <ShellFrame navigate={route} path={url}>
      {children}
    </ShellFrame>
  );
}

export function BundledAppShell({ children }: AppShellProps) {
  const path = appShell.currentRoute.value;
  return (
    <ShellFrame
      navigate={(nextPath) => setCurrentRoute(nextPath)}
      path={path}
    >
      {children}
    </ShellFrame>
  );
}
