import { useState } from "preact/hooks";
import type { JSX } from "preact";

import { Icon } from "@/design-system";
import { navigateTo } from "@/app/shell/useAppShell";
import { buildAskUrl } from "@/features/ask/askRoute";

import styles from "./HeroAskPrompt.module.css";

/**
 * Top-of-dashboard "ask anything" entry. Not a duplicate of the Ask view —
 * this is the prompt surface that routes into it with the question pre-filled
 * and an auto-submit flag set. The Ask view reads the query params and kicks
 * off retrieval immediately.
 *
 * Design rules:
 *   - Serif voice on the input (questions are a serif moment per the brief).
 *   - Submit-on-enter, no visible submit button at rest — an amber spark icon
 *     appears on focus/hover to signal the action is live.
 *   - Reduced-motion friendly: no focus animation, just color swap.
 *
 * Suggestion chips below the input act as a "what can I ask" ladder for
 * users staring at an empty input. Per the Carrel design package: generic
 * but credible prompts that showcase explain / analyze / cite — Carrel's
 * three core strengths. Click → pre-fill + auto-submit via the same
 * `q + auto=1` query contract the form uses.
 */

const SUGGESTION_PROMPTS: readonly string[] = [
  "Explain this simply",
  "What's the main argument?",
  "Summarise the cited evidence",
];

function askWith(prompt: string): void {
  const trimmed = prompt.trim();
  if (!trimmed) return;
  navigateTo(buildAskUrl({ q: trimmed, auto: true, scope_kind: "library" }));
}

export function HeroAskPrompt() {
  const [value, setValue] = useState("");

  const submit = (event: JSX.TargetedEvent<HTMLFormElement, Event>) => {
    event.preventDefault();
    askWith(value);
  };

  return (
    <form
      className={styles.wrap}
      onSubmit={submit}
      role="search"
      aria-label="Ask from your sources"
    >
      <span className={styles.eyebrow}>Ask your library</span>
      <div className={styles.inputRow}>
        <input
          className={styles.input}
          type="text"
          value={value}
          onInput={(event) =>
            setValue((event.currentTarget as HTMLInputElement).value)
          }
          placeholder="What do you want to understand right now?"
          autoComplete="off"
          autoCapitalize="off"
          spellcheck={true}
          aria-label="Question for the tutor"
        />
        <button
          type="submit"
          className={styles.submit}
          disabled={value.trim().length === 0}
          aria-label="Ask from your sources"
        >
          <Icon name="arrow-right" size={16} />
        </button>
      </div>
      <div
        className={styles.suggestions}
        aria-label="Suggested prompts"
        role="group"
      >
        {SUGGESTION_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className={styles.suggestionChip}
            onClick={() => askWith(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </form>
  );
}
