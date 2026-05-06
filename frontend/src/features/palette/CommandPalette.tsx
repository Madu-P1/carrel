import { signal } from "@preact/signals";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { Icon, Text } from "@/design-system";

import {
  buildActions,
  filterActions,
  type PaletteAction,
  type PaletteContext
} from "./actions";
import styles from "./CommandPalette.module.css";

/** Global open state — anything can open the palette via openPalette(). */
export const paletteOpen = signal(false);

export function openPalette(): void {
  paletteOpen.value = true;
}

export function closePalette(): void {
  paletteOpen.value = false;
}

interface CommandPaletteProps {
  /** Called with the chosen action. If the action has a `command`, the caller
   *  should dispatch it through the menu bus so the action routing stays in
   *  one place (AppShell). */
  onSelect: (action: PaletteAction) => void;
  /** Context used to surface power-user shortcuts ("End current session",
   *  etc.) alongside the static nav/view/help actions. */
  context?: PaletteContext;
}

export function CommandPalette({ onSelect, context }: CommandPaletteProps) {
  const open = paletteOpen.value;
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const results = useMemo(() => filterActions(query, context), [query, context]);

  // Reset state when the palette opens.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    // Focus the input on the next frame so the Dialog has laid out.
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // Clamp active index when results change.
  useEffect(() => {
    if (activeIndex >= results.length) {
      setActiveIndex(Math.max(0, results.length - 1));
    }
  }, [results.length, activeIndex]);

  // Keep the active item in view.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const active = list.querySelector<HTMLElement>(`[data-palette-index="${activeIndex}"]`);
    active?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (!open) return null;

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closePalette();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((i) => Math.min(results.length - 1, i + 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const selected = results[activeIndex];
      if (selected) {
        closePalette();
        onSelect(selected);
      }
    }
  };

  const handleBackdropClick = (event: MouseEvent) => {
    if (event.target === event.currentTarget) {
      closePalette();
    }
  };

  return (
    // role="dialog" plus onKeyDown for Escape; the click handler dismisses
    // when the user clicks the backdrop. Lint sees `dialog` as non-interactive.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <div
      aria-label="Command palette"
      aria-modal="true"
      className={styles.backdrop}
      onClick={handleBackdropClick}
      onKeyDown={handleKeyDown}
      role="dialog"
    >
      <div className={styles.palette}>
        <div className={styles.inputRow}>
          <Icon name="command" size={16} />
          <input
            aria-label="Command palette input"
            className={styles.input}
            onInput={(event) => setQuery((event.target as HTMLInputElement).value)}
            placeholder="Type a command, jump to a view, or search"
            ref={inputRef}
            type="text"
            value={query}
          />
          <Text tone="tertiary" variant="caption">
            Esc
          </Text>
        </div>
        <div className={styles.list} ref={listRef} role="listbox">
          {results.length === 0 ? (
            <div className={styles.empty}>
              <Text tone="secondary">No matching commands.</Text>
            </div>
          ) : (
            (() => {
              let lastGroup: string | null = null;
              const rendered: preact.ComponentChildren[] = [];
              results.forEach((action, index) => {
                if (action.group !== lastGroup) {
                  rendered.push(
                    <div className={styles.groupLabel} key={`g-${action.group}`}>
                      <Text tone="tertiary" variant="caption">
                        {action.group}
                      </Text>
                    </div>
                  );
                  lastGroup = action.group;
                }
                const isActive = index === activeIndex;
                rendered.push(
                  <button
                    aria-selected={isActive}
                    className={[styles.row, isActive ? styles.rowActive : ""].filter(Boolean).join(" ")}
                    data-palette-index={index}
                    key={action.id}
                    onClick={() => {
                      closePalette();
                      onSelect(action);
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                    role="option"
                    type="button"
                  >
                    <Text>{action.label}</Text>
                    {action.hint ? (
                      <Text tone="tertiary" variant="caption">
                        {action.hint}
                      </Text>
                    ) : null}
                  </button>
                );
              });
              return rendered;
            })()
          )}
        </div>
        <div className={styles.footer}>
          <Text tone="tertiary" variant="caption">
            ↑↓ navigate · ⏎ run · esc close · {buildActions(context).length} commands
          </Text>
        </div>
      </div>
    </div>
  );
}
