import { Skeleton, SkeletonGroup } from "@/design-system";

import styles from "../ReaderView.module.css";

interface ReaderLoadingStateProps {
  /** Optional filename, shown in the skeleton's sr-only label. Lets the
   *  announcement read "Loading mitosis.pdf" instead of a generic
   *  "Loading…". */
  filename?: string;
}

/**
 * Reader loading state — persistent layout.
 *
 * The prior implementation was a centered card with a spinner. The
 * critique called that out: a "lonely right rail with a void in the
 * middle" makes the app feel unfinished during async. This replacement
 * keeps the three-column shell intact and renders skeletons in each
 * zone so the layout never collapses.
 *
 * Structure mirrors the final shell:
 *   LEFT    outline-shaped skeleton rows
 *   CENTER  toolbar skeleton + page-card skeleton
 *   RIGHT   delegated to the app shell's right panel (handled by the
 *           SourcePanel loading state in a later ship)
 */
export function ReaderLoadingState({ filename }: ReaderLoadingStateProps) {
  return (
    <div className={styles.reader}>
      <div className={styles.readerRoot}>
        {/* --- Outline skeleton (left rail) ----------------------------- */}
        <aside aria-hidden className={styles.outlineSkeleton}>
          <div className={styles.outlineSkeletonHeader}>
            <Skeleton shape="text-sm" width={72} />
          </div>
          <div className={styles.outlineSkeletonList}>
            {[64, 48, 72, 56, 40, 68, 44, 60].map((w, i) => (
              <Skeleton key={i} shape="text-sm" width={`${w}%`} height={18} />
            ))}
          </div>
        </aside>

        {/* --- Main canvas skeleton (center) ----------------------------- */}
        <div className={styles.readerMain}>
          <SkeletonGroup label={filename ? `Loading ${filename}` : "Loading document"}>
            {/* Toolbar skeleton — matches the real 44px bar */}
            <div className={styles.toolbarSkeleton}>
              <div className={styles.toolbarSkeletonLeft}>
                <Skeleton shape="custom" width={42} height={22} />
                <Skeleton shape="text" width={220} height={16} />
              </div>
              <div className={styles.toolbarSkeletonCenter}>
                <Skeleton shape="custom" width={28} height={28} />
                <Skeleton shape="custom" width={72} height={28} />
                <Skeleton shape="custom" width={28} height={28} />
              </div>
              <div className={styles.toolbarSkeletonRight}>
                <Skeleton shape="custom" width={72} height={28} />
              </div>
            </div>

            {/* Page card skeleton — mimics the PDF canvas rectangle so the
             * transition to the loaded state reads as "the page is arriving,"
             * not "different UI just mounted." */}
            <div className={styles.pageSkeletonWrap}>
              <div className={styles.pageSkeleton}>
                <Skeleton shape="text-lg" width="70%" />
                <Skeleton shape="text" width="96%" />
                <Skeleton shape="text" width="92%" />
                <Skeleton shape="text" width="88%" />
                <Skeleton shape="text" width="40%" />
                <div style={{ height: 16 }} />
                <Skeleton shape="text" width="94%" />
                <Skeleton shape="text" width="90%" />
                <Skeleton shape="text" width="72%" />
              </div>
            </div>
          </SkeletonGroup>
        </div>
      </div>
    </div>
  );
}
