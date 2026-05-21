import { navigateTo } from "@/app/shell/useAppShell";
import { sessions } from "@/services/api/endpoints";
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

/**
 * Context the palette uses to decide which actions are relevant.
 * Extend by adding more state — e.g., `hasDueCards`, `lastReaderDocId`,
 * `lastQuestionId`. The palette then surfaces power-user-workflow
 * shortcuts that reflect THIS user's current state, not a static menu.
 */
export interface PaletteContext {
  /** Id of the currently-active session, if any. Powers "End session". */
  activeSessionId?: string;
  /** Objective label, for the action's user-facing copy. */
  activeSessionObjective?: string;
}

const STATIC_ACTIONS: PaletteAction[] = [
  { id: "nav.dashboard", label: "Go to Dashboard", hint: "⌘1", group: "Navigate", command: "nav.dashboard", keywords: ["home", "overview", "today"] },
  { id: "nav.session", label: "Go to Session", hint: "⌘2", group: "Navigate", command: "nav.session", keywords: ["focus", "deep work", "pomodoro", "timer"] },
  { id: "nav.library", label: "Go to Library", hint: "⌘3", group: "Navigate", command: "nav.library", keywords: ["sources", "docs"] },
  { id: "nav.reader", label: "Go to Reader", hint: "⌘4", group: "Navigate", command: "nav.reader", keywords: ["pdf", "document"] },
  { id: "nav.ask", label: "Go to Ask", hint: "⌘5", group: "Navigate", command: "nav.ask", keywords: ["tutor", "chat", "question"] },
  { id: "nav.study", label: "Go to Study", hint: "⌘6", group: "Navigate", command: "nav.study", keywords: ["srs", "flashcards", "review"] },
  { id: "nav.plan", label: "Go to Plan", hint: "⌘7", group: "Navigate", command: "nav.plan", keywords: ["calendar", "schedule", "coach", "week"] },
  // Settings has no native MenuCommand wired, so it uses a direct `run`
  // override (same mechanism as the contextual "End session" action).
  { id: "nav.settings", label: "Go to Settings", hint: "⌘,", group: "Navigate", keywords: ["preferences", "provider", "ai", "claude", "ollama", "apple intelligence", "api key"], run: () => navigateTo("/settings") },
  { id: "view.toggleLeftSidebar", label: "Toggle Left Sidebar", hint: "⌘B", group: "View", command: "view.toggleLeftSidebar", keywords: ["nav"] },
  { id: "view.toggleRightPanel", label: "Toggle Right Panel", hint: "⌘⌥B", group: "View", command: "view.toggleRightPanel", keywords: ["inspector", "source"] },
  { id: "view.toggleTheme", label: "Toggle Theme", hint: "⌘⇧T", group: "View", command: "view.toggleTheme", keywords: ["dark", "light"] },
  { id: "reader.find", label: "Find in Reader", hint: "⌘F", group: "View", command: "reader.find", keywords: ["reader", "pdf", "search", "find"] },
  { id: "reader.toggleFocusMode", label: "Toggle Reader Focus Mode", hint: "⌘⇧F", group: "View", command: "reader.toggleFocusMode", keywords: ["reader", "focus", "fullscreen", "distraction"] },
  { id: "file.import", label: "Import Source…", hint: "⌘I", group: "Sources", command: "file.import", keywords: ["upload", "pdf", "new"] },
  { id: "help.shortcuts", label: "Keyboard Shortcuts", hint: "?", group: "Help", command: "help.shortcuts", keywords: ["keys", "hotkeys", "cheat sheet", "help"] }
];

/**
 * Build the full action list given current app context. Context-sensitive
 * actions (e.g., "End current session") appear at the top of the palette
 * under the Context group so they're the first thing a user sees.
 */
export function buildActions(context: PaletteContext = {}): PaletteAction[] {
  const contextual: PaletteAction[] = [];
  if (context.activeSessionId) {
    contextual.push({
      id: "context.end-session",
      label: context.activeSessionObjective
        ? `End session: ${context.activeSessionObjective}`
        : "End current session",
      group: "Context",
      keywords: ["stop", "finish", "complete", "done"],
      run: async () => {
        // endpoints + useAppShell already ship in the main chunk via other
        // feature modules, so dynamic import here was dead optimization.
        try {
          await sessions.complete(context.activeSessionId!);
          window.location.hash = "";
          navigateTo("/session");
        } catch (err) {
          console.error("end-session from palette failed", err);
        }
      }
    });
  }
  return [...contextual, ...STATIC_ACTIONS];
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

export function filterActions(
  query: string,
  context: PaletteContext = {}
): PaletteAction[] {
  return buildActions(context)
    .map((action) => ({ action, score: scoreAction(action, query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.action);
}
