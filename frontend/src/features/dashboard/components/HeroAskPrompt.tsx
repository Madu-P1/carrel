import { useState } from "preact/hooks";
import type { JSX } from "preact";

import { Icon } from "@/design-system";
import { navigateTo } from "@/app/shell/useAppShell";

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
 */
export function HeroAskPrompt() {
  const [value, setValue] = useState("");

  const submit = (event: JSX.TargetedEvent<HTMLFormElement, Event>) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    // `auto=1` tells the Ask view to skip the usual manual-submit gate and
    // kick off the question immediately. Keeping this contract explicit so
    // a future change to Ask doesn't silently break the Dashboard entry.
    const url = `/ask?q=${encodeURIComponent(trimmed)}&auto=1`;
    navigateTo(url);
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
    </form>
  );
}
