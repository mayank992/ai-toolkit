import type { HsEvent, Snapshot } from "./types";

export const eventKey = (e: HsEvent) => `${e._store}|${e.ts}|${e.t}|${e.lesson ?? e.session_id ?? ""}`;

/** Item ids the dashboard diffs between polls to highlight what just arrived. */
export function keysOf(s: Snapshot): string[] {
  return [
    ...s.queue.map((m) => m.id),
    ...s.events.map(eventKey),
    ...s.stores.flatMap((st) => st.lessons.map((l) => `${l.id}:${l.status}`)),
  ];
}
