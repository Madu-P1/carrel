/**
 * SM-V7 The Command Spine: the verb set behind ⌘K.
 *
 * Navigation verbs only: each runs directly off the shell's navigateTo. The
 * verify verbs (Verify / Seal / Export) were removed from the palette because
 * nothing listened for the CustomEvent they dispatched, so they silently did
 * nothing; ⌘↵ still verifies via the Lectern's own key handler. Restore them
 * only together with a listener on the verify surface.
 */
import { navigateTo } from "@/app/shell/useAppShell";

export interface Command {
  id: string;
  title: string;
  /** Right-aligned quiet hint: a keyboard shortcut or a one-word context. */
  hint?: string;
  /** Extra search terms beyond the title. */
  keywords?: string;
  run: () => void;
}

/**
 * Build the command list for the current route. `close` is called after a verb
 * runs so the palette dismisses itself.
 */
export function buildCommands(_path: string, close: () => void): Command[] {
  const go = (to: string) => () => {
    navigateTo(to);
    close();
  };

  const commands: Command[] = [];

  commands.push(
    { id: "new", title: "New verification", hint: "Lectern", keywords: "paste draft start home", run: go("/") },
    { id: "go-verify", title: "Go to Verify", keywords: "draft examine", run: go("/verify") },
    { id: "go-shelf", title: "Open the Shelf", hint: "Sealed briefs", keywords: "saved record history", run: go("/shelf") },
    { id: "go-vault", title: "Open the Vault", keywords: "record material vault folder sources", run: go("/vault") },
    { id: "go-settings", title: "Open Settings", keywords: "key preferences", run: go("/settings") }
  );

  return commands;
}

/**
 * Case-insensitive token filter: every whitespace-separated query token must
 * appear somewhere in the command's title or keywords. Empty query matches all.
 */
export function filterCommands(commands: Command[], query: string): Command[] {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return commands;
  return commands.filter((c) => {
    const hay = `${c.title} ${c.keywords ?? ""}`.toLowerCase();
    return tokens.every((t) => hay.includes(t));
  });
}
