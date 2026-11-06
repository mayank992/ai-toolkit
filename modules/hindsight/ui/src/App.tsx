import { useState } from "react";
import { useSnapshot } from "./useSnapshot";
import { ago } from "./time";
import type { Snapshot } from "./types";
import Pipeline from "./components/Pipeline";
import QueueView from "./components/QueueView";
import LessonsView from "./components/LessonsView";
import EventsView from "./components/EventsView";
import ReportView from "./components/ReportView";
import LogView from "./components/LogView";

const TABS = {
  queue: { label: "Queue", count: (s: Snapshot) => s.queue.length },
  lessons: { label: "Lessons", count: (s: Snapshot) => s.stores.reduce((n, st) => n + st.lessons.length, 0) },
  events: { label: "Events", count: (s: Snapshot) => s.events.length },
  report: { label: "Report", count: (s: Snapshot) => s.report.totals.sessions },
  log: { label: "Log", count: (s: Snapshot) => s.log.length },
} as const;
type Tab = keyof typeof TABS;

export default function App() {
  const [paused, setPaused] = useState(false);
  const [tab, setTab] = useState<Tab>("queue");
  const feed = useSnapshot(3000, paused);

  const snap = feed.state === "ready" ? feed.snap : feed.state === "error" ? feed.last : undefined;
  const fresh = feed.state === "ready" ? feed.fresh : new Set<string>();

  return (
    <div className="app">
      <header>
        <h1>hindsight</h1>
        <span className="sub">self-improving memory · live pipeline</span>
        <div className="spacer" />
        {feed.state === "error" && <span className="pill bad">server unreachable: {feed.message}</span>}
        {snap && <span className="muted">updated {ago(snap.generated_at)}</span>}
        <button onClick={() => setPaused((p) => !p)}>{paused ? "Resume" : "Pause"}</button>
      </header>

      {!snap ? (
        <p className="muted">Loading snapshot…</p>
      ) : (
        <>
          <Pipeline stages={snap.stages} hooks={snap.hooks} />
          <nav className="tabs">
            {(Object.keys(TABS) as Tab[]).map((t) => (
              <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>
                {TABS[t].label} <span className="count">{TABS[t].count(snap)}</span>
              </button>
            ))}
          </nav>
          <main>
            {tab === "queue" && <QueueView queue={snap.queue} fresh={fresh} />}
            {tab === "lessons" && <LessonsView stores={snap.stores} efficacy={snap.report.lessons} fresh={fresh} />}
            {tab === "events" && <EventsView events={snap.events} fresh={fresh} />}
            {tab === "report" && <ReportView report={snap.report} />}
            {tab === "log" && <LogView lines={snap.log} />}
          </main>
        </>
      )}
    </div>
  );
}
