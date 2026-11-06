import { useEffect, useRef, useState } from "react";
import type { HsEvent, Snapshot } from "./types";

export type Feed =
  | { state: "loading" }
  | { state: "error"; message: string; last?: Snapshot }
  | { state: "ready"; snap: Snapshot; fresh: Set<string> };

export const eventKey = (e: HsEvent) => `${e._store}|${e.ts}|${e.t}|${e.lesson ?? e.session_id ?? ""}`;

function keysOf(s: Snapshot): Set<string> {
  const keys = new Set<string>();
  s.queue.forEach((m) => keys.add(m.id));
  s.events.forEach((e) => keys.add(eventKey(e)));
  s.stores.forEach((st) => st.lessons.forEach((l) => keys.add(`${l.id}:${l.status}`)));
  return keys;
}

export function useSnapshot(intervalMs: number, paused: boolean): Feed {
  const [feed, setFeed] = useState<Feed>({ state: "loading" });
  const seen = useRef<Set<string> | null>(null);
  const last = useRef<Snapshot | undefined>(undefined);

  useEffect(() => {
    if (paused) return;
    let alive = true;
    const tick = async () => {
      try {
        const res = await fetch("/api/snapshot");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const snap: Snapshot = await res.json();
        const keys = keysOf(snap);
        const prev = seen.current;
        const fresh = prev ? new Set([...keys].filter((k) => !prev.has(k))) : new Set<string>();
        seen.current = keys;
        last.current = snap;
        if (alive) setFeed({ state: "ready", snap, fresh });
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
  }, [intervalMs, paused]);

  return feed;
}
