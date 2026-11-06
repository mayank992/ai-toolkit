import { useMemo, useState } from "react";
import type { Lesson, LessonEfficacy, LessonStatus, Store } from "../types";

const STATUSES: LessonStatus[] = ["active", "candidate", "retired", "dismissed"];

interface Props {
  stores: Store[];
  efficacy: LessonEfficacy[];
  fresh: Set<string>;
}

export default function LessonsView({ stores, efficacy, fresh }: Props) {
  const [status, setStatus] = useState<LessonStatus | "all">("all");
  const [store, setStore] = useState<string>("all");
  const stats = useMemo(() => new Map(efficacy.map((e) => [`${e.store}/${e.id}`, e])), [efficacy]);
  const lessons = useMemo(
    () =>
      stores
        .flatMap((s) => s.lessons)
        .filter((l) => (status === "all" || l.status === status) && (store === "all" || l.store === store))
        .sort((a, b) => STATUSES.indexOf(a.status) - STATUSES.indexOf(b.status) || b.created.localeCompare(a.created)),
    [stores, status, store],
  );

  return (
    <>
      <div className="store-cards">
        {stores.map((s) => (
          <div key={s.name} className={`card ${store === s.name ? "selected" : ""}`}
            onClick={() => setStore(store === s.name ? "all" : s.name)}>
            <b>{s.name}</b> {s.default && <span className="chip">default</span>}
            {!s.initialized && <span className="chip bad">not initialized</span>}
            <div className="muted small">{s.path}</div>
            <div className="small">match {s.match.join(", ") || "none"} · remote {s.remote || "none"}</div>
            <div className="small">
              {STATUSES.map((st) => `${s.lessons.filter((l) => l.status === st).length} ${st}`).join(" · ")}
            </div>
          </div>
        ))}
      </div>
      <div className="toolbar">
        {(["all", ...STATUSES] as const).map((s) => (
          <button key={s} className={s === status ? "active" : ""} onClick={() => setStatus(s)}>
            {s}
          </button>
        ))}
      </div>
      {!lessons.length ? (
        <p className="muted">No lessons here yet. Lessons appear after distill turns queued moments into candidates.</p>
      ) : (
        <div className="lessons">
          {lessons.map((l) => (
            <LessonCard key={`${l.store}/${l.id}`} l={l} e={stats.get(`${l.store}/${l.id}`)}
              fresh={fresh.has(`${l.id}:${l.status}`)} />
          ))}
        </div>
      )}
    </>
  );
}

function LessonCard({ l, e, fresh }: { l: Lesson; e?: LessonEfficacy; fresh: boolean }) {
  return (
    <div className={`card lesson status-${l.status} ${fresh ? "fresh" : ""}`}>
      <div className="lesson-head">
        <code>{l.id}</code>
        <span className={`pill status-${l.status}`}>{l.status}</span>
        {l.pinned && <span className="chip">pinned</span>}
        {e?.flagged_ineffective && <span className="chip bad">ineffective</span>}
        <span className="muted small">{l.scope} · {l.store}/{l.file} · {l.created}</span>
      </div>
      <div className="lesson-text">{l.text}</div>
      {l.issue && <div className="small"><b>issue</b> {l.issue}</div>}
      {l.why && <div className="small"><b>why</b> {l.why}</div>}
      {(l.keywords.length > 0 || l.files.length > 0) && (
        <div className="small muted">trigger {[...l.keywords, ...l.files].join(", ")}</div>
      )}
      {l.reason && <div className="small muted">reason {l.reason}</div>}
      {e && (
        <div className="small stats">
          {e.hits} hit sessions · injected in {e.sessions_injected} · repeats while injected {e.repeats_while_injected}
          {e.activated && <> · rate {e.before.rate} → {e.after.rate} · prevented {e.prevented}</>}
        </div>
      )}
    </div>
  );
}
