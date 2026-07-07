import { navigateTo } from "@/app/shell/useAppShell";
import type { MenuCommand } from "@/services/native/menu";

export interface PaletteAction {
  id: string;
  label: string;
  hint?: string;
  group: "Context" | "Navigate" | "View" | "Sources" | "System" | "Help";
  keywords?: string[];
  /** If present, dispatch this command through the native menu bus. */
  command?: MenuCommand;
  /** Direct action override — runs instead of the command. */
  run?: () => void;
}

const STATIC_ACTIONS: PaletteAction[] = [
  { id: "nav.library", label: "Go to Library", hint: "⌘1", group: "Navigate", command: "nav.library", keywords: ["sources", "docs", "vault"] },
  { id: "nav.reader", label: "Go to Reader", hint: "⌘2", group: "Navigate", command: "nav.reader", keywords: ["pdf", "document"] },
  { id: "nav.verify", label: "Go to Verify", hint: "⌘3", group: "Navigate", keywords: ["draft", "check", "citations"], run: () => navigateTo("/verify") },
  { id: "nav.shelf", label: "Go to Shelf", hint: "⌘4", group: "Navigate", keywords: ["briefs", "saved", "sealed"], run: () => navigateTo("/shelf") },
  { id: "view.toggleLeftSidebar", label: "Toggle Left Sidebar", hint: "⌘B", group: "View", command: "view.toggleLeftSidebar", keywords: ["nav"] },
  { id: "view.toggleRightPanel", label: "Toggle Right Panel", hint: "⌘⌥B", group: "View", command: "view.toggleRightPanel", keywords: ["inspector", "source"] },
  { id: "view.toggleTheme", label: "Toggle Theme", hint: "⌘⇧T", group: "View", command: "view.toggleTheme", keywords: ["dark", "light"] },
  { id: "reader.find", label: "Find in Reader", hint: "⌘F", group: "View", command: "reader.find", keywords: ["reader", "pdf", "search", "find"] },
  { id: "reader.toggleFocusMode", label: "Toggle Reader Focus Mode", hint: "⌘⇧F", group: "View", command: "reader.toggleFocusMode", keywords: ["reader", "focus", "fullscreen", "distraction"] },
  { id: "file.import", label: "Import Source…", hint: "⌘I", group: "Sources", command: "file.import", keywords: ["upload", "pdf", "new"] },
  { id: "help.shortcuts", label: "Keyboard Shortcuts", hint: "?", group: "Help", command: "help.shortcuts", keywords: ["keys", "hotkeys", "cheat sheet", "help"] }
];

/** Build the full action list. Context-sensitive actions were removed with
 *  the Carrel extraction; the registry is static for now. */
export function buildActions(): PaletteAction[] {
  return [...STATIC_ACTIONS];
}

/** Backwards-compat default export used by existing tests that import
 *  the static list directly. */
export const paletteActions: PaletteAction[] = STATIC_ACTIONS;

/**
 * Score a single action against a query. Returns 0 if it should not be shown.
 * Higher is better. Matching is simple substring (case-insensitive) across
 * label + keywords + group; full-label prefix match scores higher than
 * mid-word match, and exact label match scores highest.
 *
 * Context actions always score HIGH so they sort to the top when relevant.
 */
export function scoreAction(action: PaletteAction, query: string): number {
  const q = query.trim().toLowerCase();
  const contextBoost = action.group === "Context" ? 200 : 0;
  if (q === "") return 1 + contextBoost;
  const label = action.label.toLowerCase();
  if (label === q) return 100 + contextBoost;
  if (label.startsWith(q)) return 50 + contextBoost;
  if (label.includes(q)) return 25 + contextBoost;
  const keywordHit = (action.keywords ?? []).some((kw) => kw.toLowerCase().includes(q));
  if (keywordHit) return 15 + contextBoost;
  if (action.group.toLowerCase().includes(q)) return 10 + contextBoost;
  return 0;
}

export function filterActions(query: string): PaletteAction[] {
  return buildActions()
    .map((action) => ({ action, score: scoreAction(action, query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.action);
}
