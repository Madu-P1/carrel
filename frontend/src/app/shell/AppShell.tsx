import { useEffect } from "preact/hooks";
import { useLocation } from "preact-iso";
import type { ComponentChildren } from "preact";

import { Box, Button, Card, Divider, Icon, ScrollArea, Stack, Text, ToastHost } from "@/design-system";
import { WorkspaceSidebar, type SidebarNavItem } from "./WorkspaceSidebar";
import { CommandPalette, openPalette } from "@/features/palette/CommandPalette";
import type { PaletteAction } from "@/features/palette/actions";
import {
  requestReaderPage,
  readerState,
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
  setCurrentRoute,
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
  { key: "session", label: "Session", commandHint: "⌘2", icon: "sparkle", path: "/session" },
  { key: "library", label: "Library", commandHint: "⌘3", icon: "library", path: "/library" },
  { key: "reader", label: "Reader", commandHint: "⌘4", icon: "doc", path: "/reader" },
  { key: "ask", label: "Ask", commandHint: "⌘5", icon: "ask", path: "/ask" },
  { key: "study", label: "Study", commandHint: "⌘6", icon: "study", path: "/study" }
];

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

  return "Workspace";
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
  const theme = appShell.theme.value;
  const pathname = pathnameFromRoute(path);
  const activeLabel = routeLabel(pathname);
  const panelContent = appShell.rightPanelContent.value;
  const playBootMotion = isColdBootMotionEnabled();

  useEffect(() => {
    initializeTheme();
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
        case "app.preferences":
        case "file.new":
        case "help.open":
          console.info("Menu command not wired yet", cmd);
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
          // The Input primitive renders the actual field as a plain <input>
          // inside a labeled wrapper. We find it via the label text.
          const field = document.querySelector(
            "input[placeholder*='source say' i]"
          ) as HTMLInputElement | null;
          field?.focus();
        }, 60);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className={styles.shell}>
      <header
        className={[styles.topbar, playBootMotion ? styles.bootTopbar : ""]
          .filter(Boolean)
          .join(" ")}
      >
        <div className={styles.topbarTitle}>
          <BrandMark />
          <Stack gap={1}>
            <Text as="h1" variant="h2" weight="semibold">
              Einstein Workspace
            </Text>
            <Text tone="secondary">{activeLabel}</Text>
          </Stack>
        </div>
        <div className={styles.topbarActions}>
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

      <div className={styles.body}>
        <aside
          aria-hidden={!isLeftOpen}
          className={[
            styles.leftRail,
            !isLeftOpen ? styles.leftRailCollapsed : "",
            playBootMotion ? styles.bootLeftRail : ""
          ]
            .filter(Boolean)
            .join(" ")}
          data-testid="left-sidebar"
        >
          <div className={styles.leftRailInner}>
            <Card className={styles.navCard} padding="md">
              <WorkspaceSidebar
                pathname={pathname}
                items={navLinks}
                onNavigate={(path) => navigateTo(path)}
              />
            </Card>
          </div>
        </aside>

        <main
          className={[styles.main, playBootMotion ? styles.bootMain : ""]
            .filter(Boolean)
            .join(" ")}
          data-testid="main-content"
        >
          <ScrollArea className={styles.mainInner}>{children}</ScrollArea>
        </main>

        <aside
          aria-hidden={!isRightOpen}
          className={[
            styles.rightPanel,
            !isRightOpen ? styles.rightPanelCollapsed : "",
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
      <ToastHost />
    </div>
  );
}

export function AppShell({ children }: AppShellProps) {
  const { path, route } = useLocation();
  return (
    <ShellFrame navigate={route} path={path}>
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
