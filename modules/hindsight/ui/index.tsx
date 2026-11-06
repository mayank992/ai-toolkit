import { defineModule, type ViewProps } from "@toolkit/ui";
import type { Snapshot } from "./types";
import { keysOf } from "./keys";
import Kpis from "./components/Kpis";
import Pipeline from "./components/Pipeline";
import QueueView from "./components/QueueView";
import ContextView from "./components/ContextView";
import LessonsView from "./components/LessonsView";
import EventsView from "./components/EventsView";
import ReportView from "./components/ReportView";
import LogView from "./components/LogView";
import "./styles.css";

const TABS = {
  queue: { label: "Queue", count: (s: Snapshot) => s.queue.length },
  context: { label: "In Claude's context", count: (s: Snapshot) => s.in_context.reduce((n, r) => n + r.lessons.length, 0) },
  lessons: { label: "Lessons", count: (s: Snapshot) => s.stores.reduce((n, st) => n + st.lessons.length, 0) },
  report: { label: "Report", count: (s: Snapshot) => s.report.lessons.length },
  events: { label: "Events", count: (s: Snapshot) => s.events.length },
  log: { label: "Log", count: (s: Snapshot) => s.log.length },
} as const;
type Tab = keyof typeof TABS;

const hookOn = (s: Snapshot, event: string) => s.hooks.some((h) => h.event === event && h.registered);

function Hindsight({ snap, fresh, route, navigate }: ViewProps<Snapshot>) {
  const [head, sub] = route.split(":");
  const tab: Tab = head in TABS ? (head as Tab) : "queue";
  return (
    <>
      <Kpis snap={snap} />
      <Pipeline stages={snap.stages} hooks={snap.hooks} />
      <nav className="tabs">
        {(Object.keys(TABS) as Tab[]).map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => navigate(t)}>
            {TABS[t].label} <span className="count">{TABS[t].count(snap)}</span>
          </button>
        ))}
      </nav>
      <main>
        {tab === "queue" && (
          <QueueView
            queue={snap.queue}
            processed={snap.processed}
            fresh={fresh}
            distillOn={hookOn(snap, "SessionEnd")}
            view={sub === "processed" ? "processed" : "inbox"}
            onView={(v) => navigate(v === "inbox" ? "queue" : "queue:processed")}
          />
        )}
        {tab === "context" && <ContextView repos={snap.in_context} injectOn={hookOn(snap, "SessionStart")} />}
        {tab === "lessons" && <LessonsView stores={snap.stores} efficacy={snap.report.lessons} fresh={fresh} />}
        {tab === "report" && <ReportView report={snap.report} />}
        {tab === "events" && <EventsView events={snap.events} fresh={fresh} />}
        {tab === "log" && <LogView lines={snap.log} />}
      </main>
    </>
  );
}

export default defineModule<Snapshot>({ View: Hindsight, freshKeys: keysOf });
