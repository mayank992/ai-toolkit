import { useMemo, useState } from "react";
import type { Moment, MomentKind, ProcessedMoment } from "../types";
import { describe, KIND_LABEL } from "../describe";
import { ago, stamp } from "../time";

interface Props {
  queue: Moment[];
  processed: ProcessedMoment[];
  fresh: Set<string>;
  distillOn: boolean;
}

export default function QueueView({ queue, processed, fresh, distillOn }: Props) {
  const [view, setView] = useState<"inbox" | "processed">(() =>
    location.hash === "#queue:processed" ? "processed" : "inbox",
  );
  return (
    <>
      <p className="explain small">
        The <b>inbox</b> holds raw pushbacks exactly as captured. Distill reads them after each session, merges
        repeats across sessions, drops noise, and writes one general lesson per rule. <b>Processed</b> shows what
        each pushback became.
        {!distillOn && <span className="warn-text"> Distill isn't registered, so nothing leaves the inbox. Run ./install.sh.</span>}
      </p>
      <div className="toolbar">
        <button className={view === "inbox" ? "active" : ""} onClick={() => setView("inbox")}>
          Inbox <span className="count">{queue.length}</span>
        </button>
        <button className={view === "processed" ? "active" : ""} onClick={() => setView("processed")}>
          Processed <span className="count">{processed.length}</span>
        </button>
      </div>
      {view === "inbox" ? <Inbox queue={queue} fresh={fresh} /> : <Processed rows={processed} />}
    </>
  );
}

function Inbox({ queue, fresh }: { queue: Moment[]; fresh: Set<string> }) {
  const [kind, setKind] = useState<MomentKind | "all">("all");
  const [open, setOpen] = useState<string | null>(null);
  const rows = useMemo(() => queue.filter((m) => kind === "all" || m.kind === kind), [queue, kind]);

  if (!queue.length) return <p className="muted">Inbox is empty. Everything captured has been distilled.</p>;

  return (
    <>
      <div className="toolbar">
        {(["all", "prompt", "rejected_tool", "explicit"] as const).map((k) => (
          <button key={k} className={k === kind ? "active" : ""} onClick={() => setKind(k)}>
            {k === "all" ? "all" : KIND_LABEL[k]}
          </button>
        ))}
        <span className="muted small">Local only and redacted. Deleted after distill. Click a row for the agent turn.</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Kind</th>
            <th>What was captured</th>
            <th>Repo → store</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <MomentRow key={m.id} m={m} fresh={fresh.has(m.id)} open={open === m.id}
              toggle={() => setOpen(open === m.id ? null : m.id)} />
          ))}
        </tbody>
      </table>
    </>
  );
}

function MomentRow({ m, fresh, open, toggle }: { m: Moment; fresh: boolean; open: boolean; toggle: () => void }) {
  const d = describe(m);
  const ctx = m.context;
  return (
    <>
      <tr className={`clickable ${fresh ? "fresh" : ""}`} onClick={toggle}>
        <td title={stamp(m.ts)}>{ago(m.ts)}</td>
        <td><span className={`chip kind-${m.kind}`}>{KIND_LABEL[m.kind]}</span></td>
        <td className="clause">
          <div className={m.kind === "rejected_tool" ? "mono" : ""}>{d.title}</div>
          {d.reason && <div className="small muted">{d.reason}</div>}
          {d.reactingTo && (
            <div className="small muted" title={m.context?.request}>while working on: “{d.reactingTo}”</div>
          )}
        </td>
        <td className="small">
          {m.repo || <span className="muted">no remote</span>} → <b>{m.store}</b>
        </td>
      </tr>
      {open && (
        <tr className="detail">
          <td colSpan={4}>
            {ctx ? (
              <dl>
                <dt>Claude was asked</dt>
                <dd>{ctx.request || "unknown"}</dd>
                <dt>It did</dt>
                <dd>{ctx.actions?.length ? <code>{ctx.actions.join(" · ")}</code> : "no tool calls"}</dd>
                <dt>It replied</dt>
                <dd>{ctx.reply || "no reply"}</dd>
              </dl>
            ) : (
              <span className="muted">No agent-turn context captured.</span>
            )}
            <div className="muted small">
              signals {m.signals?.join(", ") || "none"} · id {m.id} · session {m.session_id} · {stamp(m.ts)}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function Processed({ rows }: { rows: ProcessedMoment[] }) {
  if (!rows.length) return <p className="muted">Nothing distilled yet.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>When</th>
          <th>Kind</th>
          <th>Became</th>
          <th>Repo → store</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p, i) => (
          <tr key={`${p.ts}-${i}`}>
            <td title={stamp(p.ts)}>{ago(p.ts)}</td>
            <td><span className={`chip kind-${p.kind}`}>{KIND_LABEL[p.kind] ?? p.kind}</span></td>
            <td>
              {p.noise ? (
                <span className="muted">noise, not a correction</span>
              ) : p.lesson ? (
                <>
                  <code>{p.lesson}</code> {p.lesson_text || <span className="muted">(lesson since deleted)</span>}{" "}
                  {p.lesson_status && <span className={`pill status-${p.lesson_status}`}>{p.lesson_status}</span>}
                </>
              ) : (
                <span className="muted">kept as evidence, no rule ({p.tool || p.signals.join(", ")})</span>
              )}
            </td>
            <td className="small">{p.repo || "no remote"} → <b>{p.store}</b></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
