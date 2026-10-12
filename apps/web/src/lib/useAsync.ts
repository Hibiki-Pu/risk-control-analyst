/**
 * Minimal async-data hook.
 *
 * Deliberately not a data-fetching library: each page needs exactly four states
 * (loading / error / empty / loaded), an abort on unmount, and a retry. Keeping it here means the
 * pages contain no fetch bookkeeping.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  /** True while a manual refresh runs but cached data is still on screen. */
  reloading: boolean;
  error: unknown;
  reload: () => void;
}

export function useAsync<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: ReadonlyArray<unknown> = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const hasDataRef = useRef(false);
  const depsKey = deps.map((value) => String(value)).join("|");

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setError(null);
    // A brand-new request shows the skeleton; a refresh keeps the stale-but-labelled data visible.
    if (!hasDataRef.current) setLoading(true);
    setReloading(true);

    fetcherRef
      .current(controller.signal)
      .then((result) => {
        if (cancelled) return;
        hasDataRef.current = true;
        setData(result);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(caught);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        setReloading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depsKey, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return { data, loading, reloading, error, reload };
}

export default useAsync;
