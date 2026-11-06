import { useMemo, useState } from "react";
import type { Lesson, LessonEfficacy, LessonStatus, Store } from "../types";
import { shortScope } from "../repo";
import Icon from "../Icon";

const STATUSES: LessonStatus[] = ["active", "candidate", "retired", "dismissed"];
const STATUS_COLOR: Record<LessonStatus, string> = {
  active: "var(--good)",
  candidate: "var(--warning)",
  retired: "var(--off)",
  dismissed: "var(--line-strong)",
};

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
      <div className="store-filter">
        {stores.map((s) => {
          const n = (st: LessonStatus) => s.lessons.filter((l) => l.status === st).length;
          const total = Math.max(1, s.lessons.length);
          return (
            <button key={s.name} className={`card store-card ${store === s.name ? "selected" : ""}`}
              onClick={() => setStore(store === s.name ? "all" : s.name)} title={s.path}>
              <div className="row">
                <Icon name="store" /> <b>{s.name}</b>
                {s.default && <span className="chip">default</span>}
                {!s.initialized && <span className="chip bad">not initialized</span>}
                <span className="spacer" />
                <span className="muted small">{s.lessons.length} lessons</span>
              </div>
              <div className="store-bar">
                {STATUSES.map((st) => n(st) > 0 && (
                  <span key={st} style={{ width: `${(n(st) / total) * 100}%`, background: STATUS_COLOR[st] }} />
                ))}
              </div>
              <div className="legend">
                {STATUSES.filter((st) => n(st) > 0).map((st) => (
                  <span key={st}><i style={{ background: STATUS_COLOR[st] }} />{n(st)} {st}</span>
                ))}
                {!s.lessons.length && <span className="muted">no lessons yet</span>}
              </div>
              <div className="small muted" style={{ marginTop: 6 }}>
                routes {s.match.join(", ") || "nothing"} · {s.remote ? "synced" : "local only"}
              </div>
            </button>
          );
        })}
      </div>
      <div className="toolbar">
        <div className="segmented">
          {(["all", ...STATUSES] as const).map((s) => (
            <button key={s} className={s === status ? "active" : ""} onClick={() => setStatus(s)}>
              {s === "all" ? "All" : s[0].toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
        <span className="small muted">Active lessons are injected. Candidates become active once they recur in a second session.</span>
      </div>
      {!lessons.length ? (
        <div className="card empty">
          <Icon name="bookmark" />
          <b>No lessons here</b>
          Lessons appear after distill turns pushbacks into rules.
        </div>
      ) : (
        <div className="card">
          {lessons.map((l) => (
            <LessonRow key={`${l.store}/${l.id}`} l={l} e={stats.get(`${l.store}/${l.id}`)}
              fresh={fresh.has(`${l.id}:${l.status}`)} />
          ))}
        </div>
      )}
    </>
  );
}

function LessonRow({ l, e, fresh }: { l: Lesson; e?: LessonEfficacy; fresh: boolean }) {
  const triggers = [...l.keywords, ...l.files];
  return (
    <div className={`lesson ${fresh ? "fresh" : ""}`}>
      <div className="lesson-head">
        <span className={`chip status-${l.status}`}>{l.status}</span>
        {l.pinned && <span className="chip">pinned</span>}
        {e?.flagged_ineffective && <span className="chip bad"><Icon name="alert" /> ineffective</span>}
        <span className="small muted" title={l.scope}>applies in <b>{shortScope(l.scope)}</b></span>
        <span className="spacer" />
        <span className="id" title={`${l.store}/${l.file}`}>{l.id}</span>
      </div>
      <div className="lesson-text">{l.text}</div>
      {(l.issue || l.why) && (
        <div className="why-issue">
          {l.issue && <div><b>What went wrong</b>{l.issue}</div>}
          {l.why && <div><b>Why it matters</b>{l.why}</div>}
        </div>
      )}
      <div className="lesson-foot">
        {e && (
          <span className="stat">
            seen in <b>{e.hits}</b> session{e.hits === 1 ? "" : "s"} · injected in <b>{e.sessions_injected}</b>
            {e.sessions_injected > 0 && <> · repeated while injected <b>{e.repeats_while_injected}</b></>}
          </span>
        )}
        {triggers.length > 0 && <span className="spacer" />}
        {triggers.slice(0, 6).map((t) => <span key={t} className="chip">{t}</span>)}
      </div>
      {l.reason && <div className="small muted" style={{ marginTop: 6 }}>Reason: {l.reason}</div>}
    </div>
  );
}
