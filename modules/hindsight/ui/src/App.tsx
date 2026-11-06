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
import ContextView from "./components/ContextView";

const TABS = {
  queue: { label: "Queue", count: (s: Snapshot) => s.queue.length },
  context: { label: "In Claude's context", count: (s: Snapshot) => s.in_context.reduce((n, r) => n + r.lessons.length, 0) },
  lessons: { label: "Lessons", count: (s: Snapshot) => s.stores.reduce((n, st) => n + st.lessons.length, 0) },
  events: { label: "Events", count: (s: Snapshot) => s.events.length },
  report: { label: "Report", count: (s: Snapshot) => s.report.totals.sessions },
  log: { label: "Log", count: (s: Snapshot) => s.log.length },
} as const;
type Tab = keyof typeof TABS;

const hookOn = (s: Snapshot, event: string) => s.hooks.some((h) => h.event === event && h.registered);

export default function App() {
  const [paused, setPaused] = useState(false);
  const [tab, setTabState] = useState<Tab>(() => {
    const h = location.hash.slice(1).split(":")[0];
    return h in TABS ? (h as Tab) : "queue";
  });
  const setTab = (t: Tab) => {
    setTabState(t);
    history.replaceState(null, "", `#${t}`);
  };
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
            {tab === "queue" && (
              <QueueView queue={snap.queue} processed={snap.processed} fresh={fresh} distillOn={hookOn(snap, "SessionEnd")} />
            )}
            {tab === "context" && <ContextView repos={snap.in_context} injectOn={hookOn(snap, "SessionStart")} />}
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
