/**
 * SM-V7 The Command Spine: the verb set behind ⌘K.
 *
 * Navigation verbs run directly (they only need the shell's navigateTo). The
 * verify verbs (Verify / Seal / Export) are decoupled by a CustomEvent the
 * verify surface listens for, so the palette never reaches into VerifyView's
 * internals and Carrel is unaffected (it never dispatches the event).
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

/** The id carried on a `cachet:command` event when a verify verb is chosen. */
export type VerifyCommandId = "verify-draft" | "load-specimen" | "verify-document" | "seal" | "export";

export function emitVerifyCommand(id: VerifyCommandId): void {
  window.dispatchEvent(new CustomEvent("cachet:command", { detail: { id } }));
}

/**
 * Build the command list for the current route. `close` is called after a verb
 * runs so the palette dismisses itself.
 */
export function buildCommands(path: string, close: () => void): Command[] {
  const go = (to: string) => () => {
    navigateTo(to);
    close();
  };

  const commands: Command[] = [];

  // Verify verbs first, but only where they can act (a draft under examination).
  if (path === "/" || path.startsWith("/verify")) {
    const verb = (id: VerifyCommandId) => () => {
      emitVerifyCommand(id);
      close();
    };
    // Seal and export OPEN the certification exhibit (the ellipsis is the
    // dialog convention); setting the seal stays the human's click inside it.
    // No ⌘S hint: nothing binds that shortcut, and a filing-grade tool must
    // not advertise a key it does not implement.
    commands.push(
      { id: "verify-draft", title: "Verify the draft", hint: "⌘↵", keywords: "check run", run: verb("verify-draft") },
      { id: "load-specimen", title: "Load the specimen draft", hint: "Planted defects", keywords: "demo sample example specimen record", run: verb("load-specimen") },
      { id: "verify-document", title: "Verify a document…", hint: "Upload a file", keywords: "upload pdf docx file document draft", run: verb("verify-document") },
      { id: "seal", title: "Seal and save…", keywords: "record certify shelf", run: verb("seal") },
      { id: "export", title: "Open exhibit…", keywords: "exhibit pdf", run: verb("export") }
    );
  }

  commands.push(
    { id: "new", title: "New verification", hint: "Lectern", keywords: "paste draft start home", run: go("/") },
    { id: "go-verify", title: "Go to Verify", keywords: "draft examine", run: go("/verify") },
    { id: "go-bench", title: "Open the Seal Bench", hint: "Check a record", keywords: "certificate seal verify offline companion", run: go("/bench") },
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
