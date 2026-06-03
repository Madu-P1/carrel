import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { filterCommands, type Command } from "./commands";
import styles from "./cachet.module.css";

/**
 * SM-V7 The Command Spine: the ⌘K palette. The keyboard-first ritual entry.
 *
 * Combobox pattern (cmdk/Raycast): the input holds focus the whole time and the
 * options are navigated by aria-activedescendant, so there is exactly one tab
 * stop and the focus trap is trivial. Esc closes and restores focus to whatever
 * was focused when it opened. Near-zero motion; a 120ms opacity fade only.
 */
export function CommandPalette({
  commands,
  onClose
}: {
  commands: Command[];
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<Element | null>(null);

  const results = useMemo(() => filterCommands(commands, query), [commands, query]);
  // Keep the active index in range as the result set shrinks while typing.
  const activeIndex = results.length === 0 ? -1 : Math.min(active, results.length - 1);
  const activeId = activeIndex >= 0 ? `cachet-cmd-${results[activeIndex].id}` : undefined;

  // Focus the input on open; restore focus to the opener on close.
  useEffect(() => {
    openerRef.current = document.activeElement;
    inputRef.current?.focus();
    return () => {
      const opener = openerRef.current as HTMLElement | null;
      opener?.focus?.();
    };
  }, []);

  // Keep the active option scrolled into view. The id is a safe slug, so no
  // CSS.escape; scrollIntoView is optional-chained for jsdom (tests).
  useEffect(() => {
    if (!activeId) return;
    const el = listRef.current?.querySelector(`#${activeId}`) as HTMLElement | null;
    el?.scrollIntoView?.({ block: "nearest" });
  }, [activeId]);

  function run(index: number) {
    const cmd = results[index];
    if (cmd) cmd.run();
  }

  function onKeyDown(event: KeyboardEvent) {
    switch (event.key) {
      case "Escape":
        event.preventDefault();
        onClose();
        break;
      case "ArrowDown":
        event.preventDefault();
        setActive((i) => (results.length === 0 ? 0 : (Math.min(i, results.length - 1) + 1) % results.length));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActive((i) => (results.length === 0 ? 0 : (Math.min(i, results.length - 1) - 1 + results.length) % results.length));
        break;
      case "Enter":
        event.preventDefault();
        if (activeIndex >= 0) run(activeIndex);
        break;
      case "Tab":
        // One tab stop: never let focus escape the palette.
        event.preventDefault();
        break;
      default:
        break;
    }
  }

  return (
    <div
      className={styles.paletteScrim}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={styles.palettePanel}
        role="dialog"
        aria-modal="true"
        aria-label="Commands"
        onKeyDown={onKeyDown}
      >
        <input
          ref={inputRef}
          className={styles.paletteInput}
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls="cachet-cmd-list"
          aria-activedescendant={activeId}
          aria-label="Type a command"
          placeholder="Type a command"
          spellcheck={false}
          value={query}
          onInput={(e) => {
            setQuery((e.target as HTMLInputElement).value);
            setActive(0);
          }}
        />
        <div className={styles.paletteList} role="listbox" id="cachet-cmd-list" ref={listRef}>
          {results.length === 0 ? (
            <p className={styles.paletteEmpty}>No command matches.</p>
          ) : (
            results.map((cmd, i) => (
              <div
                key={cmd.id}
                id={`cachet-cmd-${cmd.id}`}
                role="option"
                aria-selected={i === activeIndex}
                className={`${styles.paletteOption} ${i === activeIndex ? styles.paletteOptionActive : ""}`}
                onClick={() => run(i)}
                onMouseMove={() => setActive(i)}
              >
                <span className={styles.paletteOptionTitle}>{cmd.title}</span>
                {cmd.hint ? <span className={styles.paletteHint}>{cmd.hint}</span> : null}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
