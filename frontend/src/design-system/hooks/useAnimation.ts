import { useEffect, useRef } from "preact/hooks";

export interface AnimationSpec {
  keyframes: Keyframe[] | PropertyIndexedKeyframes;
  options?: KeyframeAnimationOptions;
  when?: () => boolean;
}

export function useAnimation<T extends HTMLElement>(
  spec: AnimationSpec,
  deps: unknown[] = []
) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return undefined;
    }

    if (spec.when && !spec.when()) {
      return undefined;
    }

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const options = reduce ? { ...spec.options, duration: 0 } : spec.options ?? {};
    const animation = element.animate(spec.keyframes, options);

    return () => {
      try {
        animation.cancel();
      } catch {
        // Ignore cleanup errors from detached nodes.
      }
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps

  return ref;
}
