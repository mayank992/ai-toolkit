import { useEffect, useState } from "react";
import { useSnapshot } from "./useSnapshot";
import { ago } from "./time";
import type { Snapshot } from "./types";
import Icon from "./Icon";
import Kpis from "./components/Kpis";
import Pipeline from "./components/Pipeline";
import QueueView from "./components/QueueView";
import ContextView from "./components/ContextView";
import LessonsView from "./components/LessonsView";
import EventsView from "./components/EventsView";
import ReportView from "./components/ReportView";
import LogView from "./components/LogView";

const TABS = {
  queue: { label: "Queue", count: (s: Snapshot) => s.queue.length },
  context: { label: "In Claude's context", count: (s: Snapshot) => s.in_context.reduce((n, r) => n + r.lessons.length, 0) },
  lessons: { label: "Lessons", count: (s: Snapshot) => s.stores.reduce((n, st) => n + st.lessons.length, 0) },
  report: { label: "Report", count: (s: Snapshot) => s.report.lessons.length },
  events: { label: "Events", count: (s: Snapshot) => s.events.length },
  log: { label: "Log", count: (s: Snapshot) => s.log.length },
} as const;
type Tab = keyof typeof TABS;
type Theme = "light" | "dark";

const hookOn = (s: Snapshot, event: string) => s.hooks.some((h) => h.event === event && h.registered);

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("hs-theme") as Theme | null) ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    localStorage.setItem("hs-theme", next);
    setTheme(next);
  };
  return [theme, toggle];
}

export default function App() {
  const [paused, setPaused] = useState(false);
  const [theme, toggleTheme] = useTheme();
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
  const liveClass = feed.state === "error" ? "error" : paused ? "paused" : "";
  const liveText =
    feed.state === "error" ? "Server unreachable" : paused ? "Paused" : snap ? `Live · updated ${ago(snap.generated_at)}` : "Connecting";

  return (
    <div className="app">
      <header className="top">
        <div className="brand-mark"><Icon name="distill" /></div>
        <div className="brand">
          <h1>hindsight</h1>
          <p>Learns from your pushback so Claude doesn't repeat mistakes</p>
        </div>
        <div className="spacer" />
        <span className={`live ${liveClass}`} title={feed.state === "error" ? feed.message : undefined}>
          <span className="live-dot" /> {liveText}
        </span>
        <button onClick={() => setPaused((p) => !p)}>
          <Icon name={paused ? "play" : "pause"} /> {paused ? "Resume" : "Pause"}
        </button>
        <button className="icon-btn" onClick={toggleTheme} title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          <Icon name={theme === "dark" ? "sun" : "moon"} />
        </button>
      </header>

      {!snap ? (
        <div className="card empty"><b>Loading snapshot…</b>Waiting for <code>hs ui</code> to answer.</div>
      ) : (
        <>
          <Kpis snap={snap} />
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
            {tab === "report" && <ReportView report={snap.report} />}
            {tab === "events" && <EventsView events={snap.events} fresh={fresh} />}
            {tab === "log" && <LogView lines={snap.log} />}
          </main>
        </>
      )}
    </div>
  );
}
