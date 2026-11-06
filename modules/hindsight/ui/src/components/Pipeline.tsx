import type { Health, Hook, Stage } from "../types";
import Icon, { type IconName } from "../Icon";
import { ago } from "../time";

const HEALTH: Record<Health, { label: string; icon: IconName }> = {
  ok: { label: "Healthy", icon: "check" },
  waiting: { label: "Waiting", icon: "clock" },
  stalled: { label: "Stalled", icon: "alert" },
  off: { label: "Off", icon: "off" },
};

export default function Pipeline({ stages, hooks }: { stages: Stage[]; hooks: Hook[] }) {
  return (
    <section className="card pipeline">
      <div className="section-title">
        <h2>Pipeline</h2>
      </div>
      <p className="section-sub">How a pushback becomes something Claude knows. Each stage feeds the next.</p>
      <div className="steps">
        {stages.map((s) => (
          <div key={s.id} className={`step h-${s.health}`}>
            <div className="step-dot" title={HEALTH[s.health].label}>
              <Icon name={s.id as IconName} />
            </div>
            <div className="step-name">{s.label}</div>
            <div className="step-health">
              <Icon name={HEALTH[s.health].icon} /> {HEALTH[s.health].label}
            </div>
            <div className="step-metric">{s.metric}</div>
            <div className="step-last">last {ago(s.last_at)}</div>
            {s.note && <div className="step-note">{s.note}</div>}
          </div>
        ))}
      </div>
      <div className="hooks">
        <span className="small muted">Hooks</span>
        {hooks.map((h) => (
          <span key={h.script} className={`chip ${h.registered ? "good" : "bad"}`}
            title={`${h.script}, installed at step ${h.step}`}>
            <Icon name={h.registered ? "check" : "off"} /> {h.event}
          </span>
        ))}
      </div>
    </section>
  );
}
