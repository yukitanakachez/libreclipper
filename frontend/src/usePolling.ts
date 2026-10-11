import { useEffect, useRef } from "react";

/** Calls `callback` every `intervalMs` while `active`; stops when nothing is in progress. */
export function usePolling(callback: () => void, active: boolean, intervalMs = 1500): void {
  const saved = useRef(callback);
  useEffect(() => { saved.current = callback; }, [callback]);
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => saved.current(), intervalMs);
    return () => window.clearInterval(id);
  }, [active, intervalMs]);
}
