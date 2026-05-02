import type { ComponentChildren } from "preact";
import { useEffect, useId, useRef, useState } from "preact/hooks";

import { Button, Icon, toast } from "@/design-system";
import { navigateTo } from "@/app/shell/useAppShell";
import { onboarding } from "@/services/api/endpoints";

import { OnboardingMockup, type TourStepIndex } from "./OnboardingMockup";
import { ProgressSegments } from "./ProgressSegments";
import styles from "./FirstRunTour.module.css";

const STORAGE_KEY = "carrel.first-run-tour.completed";
const STORAGE_VERSION_KEY = "carrel.first-run-tour.version";
const TOUR_EVENT = "carrel:first-run-tour:open";
const TOUR_VERSION = "5";

interface TourStep {
  key: "import" | "read" | "inspect" | "draft";
  eyebrow: string;
  title: string;
  body: ComponentChildren;
  action: string;
}

const termDefinitions = {
  reader: "The panel that opens when you click a citation.",
  inspector: "Shows the original passage behind any citation.",
  jobs: "Live status of imports and extraction.",
  anchor: "A passage tied to a specific page in a source.",
  card: "A flashcard generated from an anchor."
} as const;

const STEPS: TourStep[] = [
  {
    key: "import",
    eyebrow: "IMPORT",
    title: "Bring in a source you trust.",
    body: (
      <>
        Load the demo library or import your own PDF. The{" "}
        <TermDefinition label="Jobs Tray" definition={termDefinitions.jobs} /> keeps every
        import stage visible, so extraction never feels invisible.
      </>
    ),
    action: "Load samples"
  },
  {
    key: "read",
    eyebrow: "READ",
    title: "Read the passage that grounds the claim.",
    body: (
      <>
        Ask one question, then move into the{" "}
        <TermDefinition label="Reader" definition={termDefinitions.reader} /> to see the
        paragraph Carrel used before you trust the answer.
      </>
    ),
    action: "Open Ask"
  },
  {
    key: "inspect",
    eyebrow: "INSPECT",
    title: "Trace any answer back to the page.",
    body: (
      <>
        Click a citation to open the{" "}
        <TermDefinition label="Evidence Inspector" definition={termDefinitions.inspector} />,
        then save the passage as an{" "}
        <TermDefinition label="Anchor" definition={termDefinitions.anchor} /> when it matters.
      </>
    ),
    action: "Open Reader"
  },
  {
    key: "draft",
    eyebrow: "DRAFT",
    title: "Turn what you read into recall.",
    body: (
      <>
        Use the saved anchor to draft a{" "}
        <TermDefinition label="Card" definition={termDefinitions.card} />, edit the best one,
        and keep it for review.
      </>
    ),
    action: "Finish"
  }
];

export function openFirstRunTour() {
  window.dispatchEvent(new CustomEvent(TOUR_EVENT));
}

function shouldOpenAutomatically(): boolean {
  try {
    return (
      window.localStorage.getItem(STORAGE_KEY) !== "1" ||
      window.localStorage.getItem(STORAGE_VERSION_KEY) !== TOUR_VERSION
    );
  } catch {
    return true;
  }
}

function markComplete() {
  try {
    window.localStorage.setItem(STORAGE_KEY, "1");
    window.localStorage.setItem(STORAGE_VERSION_KEY, TOUR_VERSION);
  } catch {
    // Native storage can fail in locked-down WebViews; closing still works.
  }
}

function focusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) {
    return [];
  }

  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  );
}

function TermDefinition({ label, definition }: { label: string; definition: string }) {
  const tooltipId = useId();

  return (
    <span className={styles.term}>
      <span>{label}</span>
      <span className={styles.termHelpShell}>
        <button
          aria-describedby={tooltipId}
          aria-label={`Define ${label}`}
          className={styles.termHelp}
          type="button"
        >
          ?
        </button>
        <span className={styles.termPopover} id={tooltipId} role="tooltip">
          {definition}
        </span>
      </span>
    </span>
  );
}

export function FirstRunTour() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const panelRef = useRef<HTMLElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const current = STEPS[step] ?? STEPS[0];
  const currentStep = (step + 1) as TourStepIndex;

  useEffect(() => {
    if (shouldOpenAutomatically()) {
      setOpen(true);
    }
  }, []);

  useEffect(() => {
    const handler = () => {
      setStep(0);
      setOpen(true);
    };
    window.addEventListener(TOUR_EVENT, handler);
    return () => window.removeEventListener(TOUR_EVENT, handler);
  }, []);

  useEffect(() => {
    if (!open) {
      previousFocusRef.current?.focus();
      previousFocusRef.current = null;
      return undefined;
    }

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const frame = window.requestAnimationFrame(() => {
      const [firstFocusable] = focusableElements(panelRef.current);
      const preferredFocus = panelRef.current?.querySelector<HTMLElement>("[data-tour-initial-focus]");
      (preferredFocus ?? firstFocusable ?? panelRef.current)?.focus();
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const focusable = focusableElements(panelRef.current);
      if (focusable.length === 0) {
        event.preventDefault();
        panelRef.current?.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const close = () => {
    markComplete();
    setOpen(false);
  };

  const goNext = () => {
    if (current.key === "import") {
      void onboarding.seedDemoLibrary()
        .then((result) => {
          toast.success(
            result.seeded ? "Sample library ready" : "Sample library already ready",
            "Open Library to inspect the demo sources."
          );
          navigateTo("/library");
          setStep(1);
        })
        .catch(() => toast.error("Demo load failed", "Use Import a source to start with your own files."));
      return;
    }

    if (current.key === "read") {
      navigateTo("/ask");
      setStep(2);
      return;
    }

    if (current.key === "inspect") {
      navigateTo("/reader");
      setStep(3);
      return;
    }

    close();
  };

  if (!open) {
    return null;
  }

  return (
    <div className={styles.overlay} onClick={close}>
      <section
        aria-describedby={descriptionId}
        aria-labelledby={titleId}
        aria-modal="true"
        className={styles.panel}
        data-step={current.key}
        onClick={(event) => event.stopPropagation()}
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className={styles.header}>
          <p className={styles.kicker}>{current.eyebrow}</p>
          <h2 className={styles.title} id={titleId}>
            {current.title}
          </h2>
        </header>

        <div className={styles.copy}>
          <p className={styles.bodyText} id={descriptionId}>
            {current.body}
          </p>
        </div>

        <OnboardingMockup currentStep={currentStep} />

        <ProgressSegments current={currentStep} total={STEPS.length} />

        <footer className={styles.footer}>
          <Button
            className={[styles.tourButton, styles.primaryCta].join(" ")}
            data-tour-initial-focus
            leadingIcon={<Icon name="arrow-right" />}
            onClick={goNext}
            variant="primary"
          >
            {current.action}
          </Button>
          {step > 0 ? (
            <Button
              className={[styles.tourButton, styles.secondaryCta].join(" ")}
              onClick={() => setStep((value) => Math.max(0, value - 1))}
              variant="secondary"
            >
              Back
            </Button>
          ) : null}
          <Button className={[styles.tourButton, styles.ghostCta].join(" ")} onClick={close} variant="ghost">
            Skip
          </Button>
        </footer>

        <button className={styles.closeButton} type="button" aria-label="Close tour" onClick={close}>
          <Icon name="x" size={16} />
        </button>
      </section>
    </div>
  );
}
