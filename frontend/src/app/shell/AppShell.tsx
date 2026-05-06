import type { ComponentChildren, JSX } from "preact";
import { useLocation } from "preact-iso";

import { Box, Button, Card, Divider, Icon, ScrollArea, Stack, Text, ToastHost } from "@/design-system";
import { FirstRunTour, openFirstRunTour } from "@/features/onboarding/FirstRunTour";
import type { PaletteAction } from "@/features/palette/actions";
import { CommandPalette, openPalette } from "@/features/palette/CommandPalette";
import { readerState } from "@/features/reader/state";
import { JobsTray } from "@/features/shell/JobsTray";
import { dispatchMenuCommand } from "@/services/native/menu";

import styles from "./AppShell.module.css";
import { isColdBootMotionEnabled } from "./boot";
import { BrandMark } from "./BrandMark";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { usePanelResize } from "./hooks/usePanelResize";
import { useRouteMotion } from "./hooks/useRouteMotion";
import { useShellBootstrap } from "./hooks/useShellBootstrap";
import { useShellMenuCommands } from "./hooks/useShellMenuCommands";
import { ShortcutsOverlay } from "./ShortcutsOverlay";
import {
  appShell,
  navigateTo,
  pathnameFromRoute,
  setCurrentRoute,
  SHELL_PANEL_WIDTHS,
  toggleTheme
} from "./useAppShell";
import { WorkspaceSidebar, type SidebarNavItem } from "./WorkspaceSidebar";

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

function routeLabel(path: string): string {
  if (path === "/") return "Dashboard";
  if (path.startsWith("/reader")) return "Reader";
  if (path.startsWith("/ask")) return "Ask";
  if (path.startsWith("/study")) return "Study";
  if (path.startsWith("/library")) return "Library";
  if (path.startsWith("/search")) return "Search";
  if (path.startsWith("/concepts")) return "Concepts";
  if (path.startsWith("/plan")) return "Plan";
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

  const { startPanelResize, resizePanelFromKeyboard } = usePanelResize();
  useShellBootstrap({ navigate, path });
  useShellMenuCommands();
  useGlobalShortcuts();

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
                onNavigate={(nextPath) => navigateTo(nextPath)}
              />
            </Card>
          </div>
        </aside>
        {/*
          The resize handle is a `role="separator"` per ARIA practices for
          panel resizers; jsx-a11y treats separator as non-interactive,
          but this one IS interactive (pointer + keyboard via the handlers
          below). Hence the disable.
        */}
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
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
        {/* See note on the left resize handle for why this rule is disabled. */}
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
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
