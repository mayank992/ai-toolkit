import { useEffect, useRef, useState } from "react";

export type Feed<S> =
  | { state: "loading" }
  | { state: "error"; message: string; last?: S }
  | { state: "ready"; snap: S; fresh: Set<string> };

/** Polls one module's snapshot; `fresh` holds keys that appeared since the previous poll. */
export function useSnapshot<S>(
  url: string | null,
  intervalMs: number,
  paused: boolean,
  keysOf?: (snap: S) => Iterable<string>,
): Feed<S> {
  // Each feed value remembers the URL it came from, so a module never renders another module's snapshot
  // during the render right after switching (before the reset effect below has run).
  const [tagged, setTagged] = useState<{ url: string | null; feed: Feed<S> }>({ url, feed: { state: "loading" } });
  const setFeed = (f: Feed<S>) => setTagged({ url, feed: f });
  const seen = useRef<Set<string> | null>(null);
  const last = useRef<S | undefined>(undefined);
  const keysRef = useRef(keysOf);
  keysRef.current = keysOf;

  // A different module is a different feed: forget what the previous one had.
  useEffect(() => {
    seen.current = null;
    last.current = undefined;
    setFeed({ state: "loading" });
  }, [url]);

  useEffect(() => {
    if (paused || !url) return;
    let alive = true;
    const tick = async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
        const snap: S = await res.json();
        if (!alive) return;
        const keys = new Set(keysRef.current?.(snap) ?? []);
        const prev = seen.current;
        const fresh = prev ? new Set([...keys].filter((k) => !prev.has(k))) : new Set<string>();
        seen.current = keys;
        last.current = snap;
        setFeed({ state: "ready", snap, fresh });
      } catch (err) {
        if (alive) setFeed({ state: "error", message: String(err), last: last.current });
      }
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [url, intervalMs, paused]);

  return tagged.url === url ? tagged.feed : { state: "loading" };
}
