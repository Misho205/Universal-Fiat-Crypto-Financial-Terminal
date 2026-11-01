"use client";
import * as React from "react";

/** Safe status polling: exponential backoff, abort on unmount, stops on terminal states. */
export function usePolling<T>(fn: () => Promise<T>, opts: {
  intervalMs?: number; maxIntervalMs?: number; enabled?: boolean;
  isTerminal?: (value: T | null) => boolean; onUpdate?: (v: T) => void;
} = {}) {
  const { intervalMs = 3000, maxIntervalMs = 15000, enabled = true, isTerminal, onUpdate } = opts;
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [tick, setTick] = React.useState(0);
  const delayRef = React.useRef(intervalMs);
  const fnRef = React.useRef(fn);
  fnRef.current = fn;

  React.useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const ctrl = new AbortController();
    const id = window.setTimeout(async () => {
      try {
        const v = await fnRef.current();
        if (!alive || ctrl.signal.aborted) return;
        setData(v); setError(null);
        onUpdate?.(v);
        if (isTerminal?.(v)) return; // terminal: stop polling
        delayRef.current = Math.min(delayRef.current * 1.5, maxIntervalMs);
      } catch (e) {
        if (!alive || ctrl.signal.aborted) return;
        setError(e instanceof Error ? e.message.slice(0, 200) : String(e).slice(0, 200));
        delayRef.current = Math.min(delayRef.current * 1.5, maxIntervalMs);
      }
      if (alive) setTick((t) => t + 1);
    }, delayRef.current);
    return () => { alive = false; ctrl.abort(); window.clearTimeout(id); };
  }, [enabled, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  const reset = React.useCallback(() => { delayRef.current = intervalMs; setError(null); setTick((t) => t + 1); }, [intervalMs]);
  return { data, error, reset };
}

/** Terminal states per kind: polling stops when reached (no pointless traffic). */
export const TERMINAL_STATES: Record<string, Set<string>> = {
  fiat: new Set(["succeeded", "failed", "canceled", "refunded"]),
  evm: new Set(["confirmed", "failed", "expired"]),
  agreement: new Set(["completed", "canceled", "expired"]),
};
