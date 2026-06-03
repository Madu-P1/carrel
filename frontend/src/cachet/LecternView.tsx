import { useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";

import { CachetMark } from "./CachetMark";
import { stashPendingDraft } from "./pendingDraft";
import styles from "./cachet.module.css";

/**
 * The lectern: a composed title page. The mark, one line of what Cachet
 * verifies and refuses, and a paste affordance that reads as a sheet of paper,
 * not an input box. The paste is the lever (Loop 1): on Verify we stash the
 * draft and hand off to the verify view, which runs the check on mount.
 *
 * SM-V1 in spirit: the writing area IS the sheet. We do not promise an outcome
 * here; we set up the honest gap the verdict will land in.
 */
export function LecternView() {
  const [draft, setDraft] = useState("");
  const areaRef = useRef<HTMLTextAreaElement | null>(null);
  const ready = draft.trim().length > 0;

  function verify() {
    if (!ready) {
      areaRef.current?.focus();
      return;
    }
    stashPendingDraft(draft);
    navigateTo("/verify");
  }

  function onKeyDown(event: preact.JSX.TargetedKeyboardEvent<HTMLTextAreaElement>) {
    // Keyboard-first: Cmd/Ctrl + Enter verifies from the sheet.
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      verify();
    }
  }

  return (
    <section className={styles.lectern}>
      <CachetMark size={62} className={styles.lecternMark} />
      <h1 className={styles.wordmark}>Cachet</h1>
      <p className={styles.tagline}>
        Independent verification for high-stakes drafts. Cachet certifies only what
        it can trace to the record, and says so plainly when it cannot.
      </p>

      <div className={styles.sheet}>
        <textarea
          ref={areaRef}
          className={styles.sheetArea}
          value={draft}
          placeholder="Paste a draft to verify"
          aria-label="Draft to verify"
          spellcheck={false}
          onInput={(e) => setDraft((e.target as HTMLTextAreaElement).value)}
          onKeyDown={onKeyDown}
        />
        <div className={styles.sheetFoot}>
          <span className={styles.sheetHint}>
            Reads the citations and quotes against the sources you provide
          </span>
          <button
            type="button"
            className={styles.sheetGo}
            onClick={verify}
            disabled={!ready}
          >
            Verify
          </button>
        </div>
      </div>

      <p className={styles.lecternMeta}>Nothing leaves this machine without your say</p>
    </section>
  );
}
