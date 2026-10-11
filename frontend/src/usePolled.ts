import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";
import { onChanged } from "./changes";
import { usePolling } from "./usePolling";

const never = () => false;

/**
 * Loads something and keeps it fresh, polling while `busyWhen` says it is still changing. A failed refresh keeps the last good data and
 * retries (offline); a 404, or a first load the server refuses, becomes an error.
 */
export function usePolled<T>(load: () => Promise<T>, busyWhen: (t: T) => boolean = never) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const loader = useRef(load);
  const loaded = useRef(false);

  const latest = useRef(0);
  const reload = useCallback(() => {
    const mine = ++latest.current;
    loader.current().then((d) => {
      if (mine !== latest.current) return;
      loaded.current = true; setData(d); setError(null); setOffline(false);
    }).catch((e: Error) => {
      if (mine !== latest.current) return;
      if (e instanceof ApiError && (e.status === 404 || !loaded.current)) setError(e.message);
      else setOffline(true);
    });
  }, []);
  useEffect(() => {                     // load again whenever what we load changes
    loader.current = load;
    reload();
  }, [load, reload]);
  useEffect(() => onChanged(reload), [reload]);
  usePolling(reload, offline || (data !== null && busyWhen(data)));
  return { data, error, offline, reload };
}
