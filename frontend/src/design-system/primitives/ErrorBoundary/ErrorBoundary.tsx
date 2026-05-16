import { Component, ComponentChildren, VNode } from "preact";

import styles from "./ErrorBoundary.module.css";

type FallbackRender = (error: Error, reset: () => void) => ComponentChildren;

export interface ErrorBoundaryProps {
  children: ComponentChildren;
  /**
   * Fallback to render when a child throws. Either a static node, or a
   * `(error, reset) => node` render function for context-aware fallbacks.
   * If omitted, a minimal "Something went wrong" panel with a Retry button
   * is shown.
   */
  fallback?: ComponentChildren | FallbackRender;
  /**
   * Optional reporter fired once per caught error. Use for telemetry.
   * Reporter errors are swallowed; don't rely on throwing here.
   */
  onError?: (error: Error, info: { componentStack?: string }) => void;
  /**
   * When this value changes between renders, the boundary auto-resets.
   * Handy for "reset after the user navigates to a new route".
   */
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

/**
 * Scope render-time failures so a single broken panel can't blank the
 * whole app. Pattern imported from Next.js App Router `error.tsx`
 * convention: every meaningful subtree gets its own bounded fallback.
 *
 * Implemented as a class component using `componentDidCatch`, which
 * Preact 10 supports natively. We deliberately avoid `Suspense` and
 * `lazy()` from `preact/compat`. That combination is broken under
 * `file://` (see CLAUDE.md "Open debts").
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  state: State = { error: null };

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    this.setState({ error });
    if (this.props.onError) {
      try {
        this.props.onError(error, info ?? {});
      } catch {
        // Reporter must never cascade into the boundary.
      }
    } else if (import.meta.env.DEV && typeof console !== "undefined") {
      // eslint-disable-next-line no-console
      console.error("[ErrorBoundary]", error, info?.componentStack);
    }
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.reset();
    }
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) {
      return this.props.children as VNode;
    }
    const { fallback } = this.props;
    if (typeof fallback === "function") {
      return (fallback as FallbackRender)(error, this.reset);
    }
    if (fallback !== undefined) {
      return fallback as VNode;
    }
    return (
      <div className={styles.pane} role="alert">
        <p className={styles.title}>Something went wrong.</p>
        <p className={styles.body}>{error.message || "Unknown error."}</p>
        <button type="button" className={styles.retry} onClick={this.reset}>
          Try again
        </button>
      </div>
    );
  }
}
