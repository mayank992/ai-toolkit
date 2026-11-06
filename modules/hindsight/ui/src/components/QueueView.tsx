import { useMemo, useState } from "react";
import type { Moment, MomentKind, ProcessedMoment } from "../types";
import { describe, KIND_LABEL } from "../describe";
import { ago, stamp } from "../time";
import { shortRepo } from "../repo";
import Icon, { type IconName } from "../Icon";

const KIND_ICON: Record<MomentKind, IconName> = { prompt: "message", rejected_tool: "ban", explicit: "bookmark" };

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
      {!distillOn && (
        <div className="callout warn">
          <Icon name="alert" />
          <div>Distill isn't registered, so nothing leaves the inbox. Run <code>./install.sh</code> to turn the loop on.</div>
        </div>
      )}
      <div className="toolbar">
        <div className="segmented">
          <button className={view === "inbox" ? "active" : ""} onClick={() => setView("inbox")}>
            Inbox <span className="count">{queue.length}</span>
          </button>
          <button className={view === "processed" ? "active" : ""} onClick={() => setView("processed")}>
            Processed <span className="count">{processed.length}</span>
          </button>
        </div>
        <span className="small muted">
          {view === "inbox"
            ? "Raw pushbacks, redacted and local only. Distill turns them into lessons after each session."
            : "What each pushback became. Repeats across sessions fold into one lesson."}
        </span>
      </div>
      {view === "inbox" ? <Inbox queue={queue} fresh={fresh} /> : <Processed rows={processed} />}
    </>
  );
}

function Inbox({ queue, fresh }: { queue: Moment[]; fresh: Set<string> }) {
  const [kind, setKind] = useState<MomentKind | "all">("all");
  const [open, setOpen] = useState<string | null>(null);
  const rows = useMemo(() => queue.filter((m) => kind === "all" || m.kind === kind), [queue, kind]);

  if (!queue.length) {
    return (
      <div className="card empty">
        <Icon name="inbox" />
        <b>Inbox is empty</b>
        Everything captured has been distilled. Check Processed to see what it became.
      </div>
    );
  }

  return (
    <>
      <div className="toolbar">
        <div className="segmented">
          {(["all", "prompt", "rejected_tool", "explicit"] as const).map((k) => (
            <button key={k} className={k === kind ? "active" : ""} onClick={() => setKind(k)}>
              {k === "all" ? "All" : KIND_LABEL[k]}
            </button>
          ))}
        </div>
      </div>
      <div className="card">
        {rows.map((m) => (
          <MomentItem key={m.id} m={m} fresh={fresh.has(m.id)} open={open === m.id}
            toggle={() => setOpen(open === m.id ? null : m.id)} />
        ))}
      </div>
    </>
  );
}

function MomentItem({ m, fresh, open, toggle }: { m: Moment; fresh: boolean; open: boolean; toggle: () => void }) {
  const d = describe(m);
  const ctx = m.context;
  return (
    <div className={`item clickable ${fresh ? "fresh" : ""}`} onClick={toggle}>
      <div className={`item-icon kind-${m.kind}`}><Icon name={KIND_ICON[m.kind]} /></div>
      <div className="item-body">
        <div className={`item-title ${m.kind === "rejected_tool" ? "code" : ""}`}>{d.title}</div>
        {d.reason && <div className="item-sub">{d.reason}</div>}
        {d.reactingTo && <div className="item-sub muted" title={ctx?.request}>While working on “{d.reactingTo}”</div>}
        <div className="item-meta">
          <span className={`chip kind-${m.kind}`}>{KIND_LABEL[m.kind]}</span>
          <span title={m.repo}>{shortRepo(m.repo)}</span>
          <span className="chip">{m.store}</span>
        </div>
        {open && (
          <dl className="detail" onClick={(e) => e.stopPropagation()}>
            <dt>Claude was asked</dt>
            <dd>{ctx?.request || "unknown"}</dd>
            <dt>It did</dt>
            <dd>
              {ctx?.actions?.length ? (
                <div className="actions">{ctx.actions.map((a, i) => <code key={i}>{a}</code>)}</div>
              ) : "no tool calls"}
            </dd>
            <dt>It replied</dt>
            <dd>{ctx?.reply || "no reply"}</dd>
            <dt>Signals</dt>
            <dd>{m.signals?.join(", ") || "none"}</dd>
            <dt>Repo</dt>
            <dd>{m.repo || "none"}</dd>
            <dt>Session</dt>
            <dd className="id">{m.session_id} · {m.id}</dd>
          </dl>
        )}
      </div>
      <div className="item-side" title={stamp(m.ts)}>{ago(m.ts)}</div>
    </div>
  );
}

function Processed({ rows }: { rows: ProcessedMoment[] }) {
  if (!rows.length) {
    return (
      <div className="card empty">
        <Icon name="distill" />
        <b>Nothing distilled yet</b>
        Distill runs when a session ends.
      </div>
    );
  }
  return (
    <div className="card">
      {rows.map((p, i) => (
        <div key={`${p.ts}-${i}`} className="item">
          <div className={`item-icon kind-${p.kind}`}><Icon name={KIND_ICON[p.kind] ?? "message"} /></div>
          <div className="item-body">
            <div className="became">
              <Icon name="arrow" />
              {p.noise ? (
                <span className="item-title muted">Noise. Not a correction of Claude's behavior.</span>
              ) : p.lesson ? (
                <span className="item-title">{p.lesson_text || "(lesson since deleted)"}</span>
              ) : (
                <span className="item-title muted">Kept as evidence. No reusable rule in it.</span>
              )}
            </div>
            <div className="item-meta">
              <span className={`chip kind-${p.kind}`}>{KIND_LABEL[p.kind] ?? p.kind}</span>
              {p.lesson && <span className="id">{p.lesson}</span>}
              {p.lesson_status && <span className={`chip status-${p.lesson_status}`}>{p.lesson_status}</span>}
              <span title={p.repo}>{shortRepo(p.repo)}</span>
              <span className="chip">{p.store}</span>
            </div>
          </div>
          <div className="item-side" title={stamp(p.ts)}>{ago(p.ts)}</div>
        </div>
      ))}
    </div>
  );
}
