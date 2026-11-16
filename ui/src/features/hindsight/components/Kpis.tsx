import type { Snapshot } from "../types";
import { ago } from "@toolkit/ui";

function Tile({ label, value, foot }: { label: string; value: string; foot: React.ReactNode }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-foot">{foot}</div>
    </div>
  );
}

export default function Kpis({ snap }: { snap: Snapshot }) {
  const counts = snap.report.counts;
  const weeks = snap.report.weekly;
  const cur = weeks[weeks.length - 1];
  const prev = weeks[weeks.length - 2];
  const oldest = snap.queue[snap.queue.length - 1];

  let trend: React.ReactNode = cur ? `${cur.pushbacks} pushbacks in ${cur.sessions} sessions` : "no sessions yet";
  if (cur && prev) {
    const d = cur.rate - prev.rate;
    trend = (
      <>
        <span className={d <= 0 ? "delta-good" : "delta-bad"}>
          {d <= 0 ? "▼" : "▲"} {Math.abs(d).toFixed(2)}
        </span>
        vs {prev.week}
      </>
    );
  }

  return (
    <section className="kpis">
      <Tile label="Active lessons" value={String(counts.active)}
        foot={`${counts.candidate} candidate${counts.candidate === 1 ? "" : "s"} waiting to recur`} />
      <Tile label="Pushbacks per session, this week" value={cur ? cur.rate.toFixed(2) : "none"} foot={trend} />
      <Tile label="Waiting in inbox" value={String(snap.queue.length)}
        foot={oldest ? `oldest captured ${ago(oldest.ts)}` : "everything is distilled"} />
      <Tile label="Sessions with lessons injected" value={String(snap.totals.injected_sessions)}
        foot={snap.totals.last_inject ? `last ${ago(snap.totals.last_inject)}` : "none yet"} />
    </section>
  );
}
