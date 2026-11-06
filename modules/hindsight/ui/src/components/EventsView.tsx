import { useMemo, useState } from "react";
import type { HsEvent } from "../types";
import { eventKey } from "../useSnapshot";
import { ago, stamp } from "../time";

const SHOWN = new Set(["t", "ts", "_store"]);

function summary(e: HsEvent): string {
  return Object.entries(e)
    .filter(([k, v]) => !SHOWN.has(k) && v !== "" && v !== null && v !== undefined)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : String(v)}`)
    .join("  ");
}

export default function EventsView({ events, fresh }: { events: HsEvent[]; fresh: Set<string> }) {
  const [type, setType] = useState("all");
  const types = useMemo(() => ["all", ...new Set(events.map((e) => e.t))], [events]);
  const rows = events.filter((e) => type === "all" || e.t === type);

  if (!events.length) return <p className="muted">No events yet. Sessions, injects and distill results land here.</p>;

  return (
    <>
      <div className="toolbar">
        {types.map((t) => (
          <button key={t} className={t === type ? "active" : ""} onClick={() => setType(t)}>
            {t}
          </button>
        ))}
        <span className="muted small">newest first · last 300 across all stores</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Type</th>
            <th>Store</th>
            <th>Fields</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={eventKey(e)} className={fresh.has(eventKey(e)) ? "fresh" : ""}>
              <td title={stamp(e.ts)}>{ago(e.ts)}</td>
              <td><span className={`chip ev-${e.t}`}>{e.t}</span></td>
              <td>{e._store}</td>
              <td className="small mono">{summary(e)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
