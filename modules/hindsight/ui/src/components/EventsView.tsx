import { useMemo, useState } from "react";
import type { HsEvent } from "../types";
import { eventKey } from "../useSnapshot";
import { ago, stamp } from "../time";
import Icon from "../Icon";

const SHOWN = new Set(["t", "ts", "_store"]);
const TONE: Record<string, string> = { promote: "good", create: "good", retire: "warn", dismiss: "warn", delete: "bad" };

function summary(e: HsEvent): string {
  return Object.entries(e)
    .filter(([k, v]) => !SHOWN.has(k) && v !== "" && v !== null && v !== undefined && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : String(v)}`)
    .join("  ");
}

export default function EventsView({ events, fresh }: { events: HsEvent[]; fresh: Set<string> }) {
  const [type, setType] = useState("all");
  const types = useMemo(() => ["all", ...new Set(events.map((e) => e.t))], [events]);
  const rows = events.filter((e) => type === "all" || e.t === type);

  if (!events.length) {
    return <div className="card empty"><Icon name="clock" /><b>No events yet</b>Sessions, injections and distill results land here.</div>;
  }

  return (
    <>
      <div className="toolbar">
        <div className="segmented">
          {types.map((t) => (
            <button key={t} className={t === type ? "active" : ""} onClick={() => setType(t)}>{t}</button>
          ))}
        </div>
        <span className="small muted">Newest first · last 300 across all stores</span>
      </div>
      <div className="card">
        {rows.map((e) => (
          <div key={eventKey(e)} className={`event ${fresh.has(eventKey(e)) ? "fresh" : ""}`}>
            <span className="muted small" title={stamp(e.ts)}>{ago(e.ts)}</span>
            <span><span className={`chip ${TONE[e.t] ?? ""}`}>{e.t}</span></span>
            <span className="fields"><span className="chip" style={{ marginRight: 8 }}>{e._store}</span>{summary(e)}</span>
          </div>
        ))}
      </div>
    </>
  );
}
