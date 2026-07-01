import { useEffect, useRef } from "react";

/**
 * Poll a fetcher on an interval for as long as a component is mounted.
 *
 * Shared by the components that keep server state fresh (queue status, lane
 * badge, in-flight library cards) so each doesn't hand-roll the same
 * setInterval/cleanup/visibility plumbing:
 *
 * - Ticks are skipped while the tab is hidden (no one's looking), and one
 *   fires immediately when the tab becomes visible again.
 * - `enabled: false` tears the interval down entirely (e.g. stop polling once
 *   nothing is in flight).
 * - `immediate: false` waits a full interval before the first call, for pages
 *   that already fetch on mount elsewhere.
 *
 * The latest `fn` is always called — callers don't need to memoize it.
 */
export function usePolling(
  fn: () => void | Promise<unknown>,
  intervalMs: number,
  {
    enabled = true,
    immediate = true,
  }: { enabled?: boolean; immediate?: boolean } = {},
): void {
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });

  useEffect(() => {
    if (!enabled) return;
    const tick = () => {
      if (document.hidden) return;
      void fnRef.current();
    };
    if (immediate) tick();
    const timer = window.setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [enabled, immediate, intervalMs]);
}
