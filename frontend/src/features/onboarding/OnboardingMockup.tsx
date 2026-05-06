import styles from "./FirstRunTour.module.css";

export type TourStepIndex = 1 | 2 | 3 | 4;

type MockupState = "active" | "inactive" | "target";
type MockupElement = "source" | "excerpt" | "jobs" | "answer" | "citation" | "anchor" | "draft";

const captions: Record<TourStepIndex, string> = {
  1: "This is a Source - a PDF you've imported.",
  2: "Read the highlighted passage before you trust the claim.",
  3: "Citation -> Anchor in Evidence Inspector.",
  4: "Draft three cards from the saved anchor."
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function stateClassName(state: MockupState): string {
  // CSS-module class names exist at build time; `!` is safe here.
  if (state === "target") {
    return styles.stateTarget!;
  }
  if (state === "active") {
    return styles.stateActive!;
  }
  return styles.stateInactive!;
}

function stateFor(currentStep: TourStepIndex, element: MockupElement): MockupState {
  if (currentStep === 1) {
    return element === "source" ? "target" : "inactive";
  }

  if (currentStep === 2) {
    if (element === "excerpt") {
      return "target";
    }
    if (element === "source" || element === "jobs" || element === "answer") {
      return "active";
    }
    return "inactive";
  }

  if (currentStep === 3) {
    if (element === "citation") {
      return "target";
    }
    if (element === "source" || element === "answer" || element === "anchor") {
      return "active";
    }
    return "inactive";
  }

  if (element === "draft") {
    return "target";
  }
  if (element === "source" || element === "answer" || element === "anchor" || element === "citation") {
    return "active";
  }
  return "inactive";
}

export function OnboardingMockup({ currentStep }: { currentStep: TourStepIndex }) {
  return (
    <figure className={styles.stage} aria-hidden="true">
      <div className={styles.productFrame}>
        <div className={styles.frameTop}>
          <span />
          <span />
          <span />
          <strong>Carrel</strong>
        </div>
        <div className={styles.frameBody}>
          <div className={styles.stepRail}>
            {[1, 2, 3, 4].map((dot) => (
              <span
                className={cx(
                  styles.stepDot,
                  dot < currentStep ? styles.stepDotComplete : "",
                  dot === currentStep ? styles.stepDotCurrent : ""
                )}
                key={dot}
              />
            ))}
          </div>
          <div className={styles.canvas}>
            <section
              className={cx(
                styles.mockCard,
                styles.sourceCard,
                stateClassName(stateFor(currentStep, "source"))
              )}
            >
              <span className={styles.tileLabel}>Source</span>
              <strong>Memory Science.pdf</strong>
              <small>3 pages, indexed</small>
              <div
                className={cx(
                  styles.sourceExcerpt,
                  stateClassName(stateFor(currentStep, "excerpt"))
                )}
              >
                <span />
                <span />
                <mark>Retrieval practice strengthens recall more reliably than rereading.</mark>
                <span />
              </div>
            </section>

            <div
              className={cx(styles.mockCard, styles.jobsPill, stateClassName(stateFor(currentStep, "jobs")))}
            >
              <span className={styles.pulseDot} />
              Jobs Tray
              <small>extracting text</small>
            </div>

            <section
              className={cx(
                styles.mockCard,
                styles.answerCard,
                stateClassName(stateFor(currentStep, "answer"))
              )}
            >
              <span>What improves recall?</span>
              <strong>Practice pulling the answer from memory before rereading.</strong>
              <em className={stateClassName(stateFor(currentStep, "citation"))}>[1] p.2</em>
            </section>

            <section
              className={cx(
                styles.mockCard,
                styles.anchorCard,
                stateClassName(stateFor(currentStep, "anchor"))
              )}
            >
              <span>Evidence Inspector</span>
              <strong>Anchor</strong>
              <small>Page 2, high confidence</small>
              <p>"Retrieval practice strengthens recall..."</p>
            </section>

            <section
              className={cx(
                styles.mockCard,
                styles.draftCard,
                stateClassName(stateFor(currentStep, "draft"))
              )}
            >
              <span>Card Draft Drawer</span>
              <strong>Draft 3 cards</strong>
              <div className={styles.cardSilhouettes}>
                <span />
                <span />
                <span />
              </div>
            </section>

            <svg
              className={cx(styles.inspectorArrow, currentStep === 3 && styles.inspectorArrowVisible)}
              focusable="false"
              preserveAspectRatio="none"
              viewBox="0 0 100 100"
            >
              <path
                className={styles.inspectorArrowGlow}
                d="M50 47 C58 47 63 39.5 70.2 37.2"
                pathLength={1}
              />
              <path
                className={styles.inspectorArrowPath}
                d="M50 47 C58 47 63 39.5 70.2 37.2"
                pathLength={1}
              />
              <path className={styles.inspectorArrowTip} d="M70.2 37.2 L67.7 39.87 L66.62 36.45 Z" />
              <circle className={styles.inspectorArrowOrigin} cx="50" cy="47" r="1.55" />
            </svg>
            <div className={cx(styles.cursor, currentStep === 3 && styles.cursorActive)} />
          </div>
        </div>
      </div>
      <figcaption className={styles.mockCaption}>{captions[currentStep]}</figcaption>
    </figure>
  );
}
