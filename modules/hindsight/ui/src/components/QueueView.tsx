import { useMemo, useState } from "react";
import type { Moment, MomentKind } from "../types";
import { ago, stamp } from "../time";

const KIND_LABEL: Record<MomentKind, string> = {
  prompt: "prompt",
  rejected_tool: "rejected tool",
  explicit: "/lesson",
};

export default function QueueView({ queue, fresh }: { queue: Moment[]; fresh: Set<string> }) {
  const [kind, setKind] = useState<MomentKind | "all">("all");
  const [open, setOpen] = useState<string | null>(null);
  const rows = useMemo(() => queue.filter((m) => kind === "all" || m.kind === kind), [queue, kind]);

  if (!queue.length) return <p className="muted">Queue is empty. Distill has processed everything captured so far.</p>;

  return (
    <>
      <div className="toolbar">
        {(["all", "prompt", "rejected_tool", "explicit"] as const).map((k) => (
          <button key={k} className={k === kind ? "active" : ""} onClick={() => setKind(k)}>
            {k === "all" ? "all" : KIND_LABEL[k]}
          </button>
        ))}
        <span className="muted small">Local only, redacted. Deleted after distill.</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Kind</th>
            <th>Clause</th>
            <th>Signals / tool</th>
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
  const ctx = m.context;
  return (
    <>
      <tr className={`clickable ${fresh ? "fresh" : ""}`} onClick={toggle}>
        <td title={stamp(m.ts)}>{ago(m.ts)}</td>
        <td><span className={`chip kind-${m.kind}`}>{KIND_LABEL[m.kind]}</span></td>
        <td className="clause">{m.clause || <span className="muted">(no typed reason)</span>}</td>
        <td className="small">
          {m.signals?.join(", ")}
          {m.tool && <> {m.tool}{m.file_ext ? ` .${m.file_ext}` : ""}</>}
          {m.after_edit && <span className="chip">after edit</span>}
        </td>
        <td className="small">
          {m.repo || <span className="muted">no remote</span>} → <b>{m.store}</b>
        </td>
      </tr>
      {open && (
        <tr className="detail">
          <td colSpan={5}>
            {ctx ? (
              <dl>
                <dt>Agent was asked</dt>
                <dd>{ctx.request || "unknown"}</dd>
                <dt>It did</dt>
                <dd>{ctx.actions?.length ? <code>{ctx.actions.join(" · ")}</code> : "no tool calls"}</dd>
                <dt>It replied</dt>
                <dd>{ctx.reply || "no reply"}</dd>
              </dl>
            ) : (
              <span className="muted">No agent-turn context captured.</span>
            )}
            <div className="muted small">id {m.id} · session {m.session_id} · {stamp(m.ts)}</div>
          </td>
        </tr>
      )}
    </>
  );
}
