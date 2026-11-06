import { Fragment } from "react";
import type { Health, Hook, Stage } from "../types";
import { ago } from "../time";

const HEALTH: Record<Health, { label: string; cls: string }> = {
  ok: { label: "ok", cls: "good" },
  waiting: { label: "waiting", cls: "warn" },
  stalled: { label: "stalled", cls: "bad" },
  off: { label: "off", cls: "off" },
};

export default function Pipeline({ stages, hooks }: { stages: Stage[]; hooks: Hook[] }) {
  return (
    <section className="pipeline">
      <div className="stages">
        {stages.map((s, i) => (
          <Fragment key={s.id}>
            {i > 0 && <div className="arrow">→</div>}
            <div className={`stage ${HEALTH[s.health].cls}`} title={s.note}>
              <div className="stage-head">
                <span className="stage-label">{s.label}</span>
                <span className={`pill ${HEALTH[s.health].cls}`}>{HEALTH[s.health].label}</span>
              </div>
              <div className="stage-metric">{s.metric}</div>
              <div className="muted small">last: {ago(s.last_at)}</div>
              {s.note && <div className="stage-note small">{s.note}</div>}
            </div>
          </Fragment>
        ))}
      </div>
      <div className="hooks small">
        {hooks.map((h) => (
          <span key={h.script} className={`chip ${h.registered ? "good" : "bad"}`}>
            {h.registered ? "✓" : "✗"} {h.event} <span className="muted">step {h.step}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
