import { signal, type Signal } from "@preact/signals";
import type { ComponentType, FunctionComponent } from "preact";

/**
 * Signal-backed code-splitting for route components.
 *
 * Why not preact/compat's `lazy()` + `Suspense`? Under the bundled
 * file:// macOS shell, Suspense's re-render-after-resolution path fails
 * silently (see the long-form note in App.tsx). With signals, we don't
 * need Suspense at all — the loaded component lives in a signal, and
 * Preact re-renders whichever subtree reads it the moment the value
 * changes. No render-time fall-through, no protocol-specific edge case.
 *
 * Each call returns a `FunctionComponent` that:
 *   - On its first render, kicks off the dynamic `import()` and stores
 *     the resolved component in a module-scoped signal.
 *   - Reads that signal on every render. While loading, it returns the
 *     `Fallback` (defaults to null — the page-transition wrapper provides
 *     enough motion that a flash of empty for one frame reads as polish,
 *     not a loading state).
 *   - Once loaded, renders the real component with whatever props the
 *     route was called with.
 *
 * The signal is keyed by the loader identity, so:
 *   - Multiple instances of the same lazy route share one signal (the
 *     second instance gets the cached component on first render).
 *   - The import promise is started only once, even if the component
 *     mounts and unmounts during the load (e.g., user clicks Library,
 *     then clicks Reader before Library's chunk arrives).
 */
type Loader<P> = () => Promise<{ default: ComponentType<P> } | ComponentType<P>>;

interface LazyRouteOptions {
  /** Component shown while the chunk is loading. Defaults to null —
   *  the page-transition CSS already animates between routes, and the
   *  chunks are small enough that a one-frame flash is invisible in
   *  the bundled file:// path (no network round-trip). For browser
   *  mode you may want to pass a skeleton. */
  Fallback?: FunctionComponent;
  /** Display name for devtools + chunk-name anchoring. */
  displayName?: string;
}

interface LoaderState<P> {
  signal: Signal<ComponentType<P> | null>;
  promise: Promise<void> | null;
}

const stateByLoader = new WeakMap<Loader<unknown>, LoaderState<unknown>>();

function getOrCreateState<P>(loader: Loader<P>): LoaderState<P> {
  const cached = stateByLoader.get(loader as Loader<unknown>);
  if (cached) return cached as unknown as LoaderState<P>;

  const created: LoaderState<P> = {
    signal: signal<ComponentType<P> | null>(null),
    promise: null
  };
  stateByLoader.set(loader as Loader<unknown>, created as unknown as LoaderState<unknown>);
  return created;
}

function ensureLoading<P>(loader: Loader<P>, state: LoaderState<P>): void {
  if (state.signal.value !== null) return;
  if (state.promise !== null) return;

  state.promise = loader()
    .then((mod) => {
      // Loader may resolve to either a default-exported component or
      // the component directly (some Vite chunk shapes do the latter).
      const Component =
        typeof mod === "function"
          ? (mod as ComponentType<P>)
          : (mod as { default: ComponentType<P> }).default;
      state.signal.value = Component;
    })
    .catch((error) => {
      // Reset the promise so a retry (e.g., user navigating back into
      // the route) can re-trigger the import. Otherwise we'd be stuck
      // showing the fallback forever after a single network blip.
      state.promise = null;
      // eslint-disable-next-line no-console
      console.error("Failed to load route chunk", error);
    });
}

export function lazyRoute<P>(
  loader: Loader<P>,
  options: LazyRouteOptions = {}
): FunctionComponent<P> {
  const { Fallback, displayName } = options;

  const Lazy: FunctionComponent<P> = (props) => {
    const state = getOrCreateState(loader);
    ensureLoading(loader, state);
    const Component = state.signal.value;
    if (!Component) {
      return Fallback ? <Fallback /> : null;
    }
    return <Component {...props} />;
  };

  if (displayName) {
    Lazy.displayName = `LazyRoute(${displayName})`;
  }

  return Lazy;
}
