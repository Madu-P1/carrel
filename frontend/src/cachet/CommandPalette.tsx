import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { useModalDialog } from "@/design-system";

import { filterCommands, type Command } from "./commands";
import { enterPanel } from "./roomMotion";
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
  const listRef = useRef<HTMLDivElement | null>(null);
  // aria-modal=true: one hook captures the opener, inerts the sibling background
  // (rail + main, so browse mode does not keep reading behind the scrim), focuses
  // the input (the single tab stop), traps Tab, and on close un-inerts before
  // restoring focus to the opener. The combobox navigates by aria-activedescendant,
  // so the trap with one focusable simply keeps focus on the input.
  const scrimRef = useModalDialog<HTMLDivElement>(true);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // The arrival settle (Raycast cadence): WAAPI so reduced-motion is consulted
  // at open time; the combobox is interactive from the first frame either way.
  useEffect(() => {
    enterPanel(panelRef.current);
  }, []);

  const results = useMemo(() => filterCommands(commands, query), [commands, query]);
  // Keep the active index in range as the result set shrinks while typing.
  const activeIndex = results.length === 0 ? -1 : Math.min(active, results.length - 1);
  const activeId = activeIndex >= 0 ? `cachet-cmd-${results[activeIndex].id}` : undefined;

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
      // Tab is trapped by useModalDialog (one focusable, so focus stays on the
      // input); no per-key handling needed here.
      default:
        break;
    }
  }

  return (
    <div
      ref={scrimRef}
      className={styles.paletteScrim}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className={styles.palettePanel}
        role="dialog"
        aria-modal="true"
        aria-label="Commands"
        onKeyDown={onKeyDown}
      >
        <input
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
            query ? (
              <p className={styles.paletteEmpty}>No commands match "{query}"</p>
            ) : (
              <p className={styles.paletteEmpty}>No command matches.</p>
            )
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
