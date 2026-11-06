import { useState } from "react";
import type { Report } from "../types";
import Icon from "../Icon";

const MIN_SESSIONS_FOR_EFFICACY = 5;

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v) ?? v;
}

function WeeklyChart({ weekly }: { weekly: Report["weekly"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(...weekly.map((w) => w.rate)));
  const ticks = [0, max / 2, max];
  return (
    <div className="chart-wrap">
      <div className="chart" role="img" aria-label="Pushbacks per session by week">
        {ticks.map((t) => (
          <div key={t} className="gridline" style={{ bottom: `${(t / max) * 100}%` }}>
            <span>{t.toFixed(max < 2 ? 1 : 0)}</span>
          </div>
        ))}
        {weekly.map((w, i) => (
          <div key={w.week} className="bar-col" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <div className="bar" style={{ height: `${(w.rate / max) * 100}%` }} />
            {hover === i && (
              <div className="tooltip" style={{ bottom: `calc(${(w.rate / max) * 100}% + 8px)` }}>
                <b>{w.week}</b>
                {w.rate.toFixed(2)} per session · {w.pushbacks} pushbacks / {w.sessions} sessions
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="bar-labels">
        {weekly.map((w) => <span key={w.week}>{w.week.replace(/^\d{4}-/, "")}</span>)}
      </div>
    </div>
  );
}

export default function ReportView({ report }: { report: Report }) {
  const precision = Object.entries(report.precision).sort((a, b) => b[1].n - a[1].n);
  const maxHits = Math.max(1, ...report.lessons.map((l) => l.hits));
  const lessons = [...report.lessons].sort((a, b) => b.hits - a.hits);

  return (
    <div className="report">
      <section className="card card-pad">
        <div className="section-title"><h2>Pushbacks per session</h2></div>
        <p className="section-sub">
          The honest headline. If lessons work, this falls over the weeks. {report.totals.pushbacks} pushbacks over{" "}
          {report.totals.sessions} sessions so far.
        </p>
        {report.weekly.length ? <WeeklyChart weekly={report.weekly} /> : <p className="muted">No sessions recorded yet.</p>}
        {report.weekly.length === 1 && (
          <p className="small muted" style={{ marginBottom: 0 }}>One week of data so far. The trend shows from week 2.</p>
        )}
      </section>

      <section className="card card-pad">
        <div className="section-title"><h2>Lesson efficacy</h2></div>
        <p className="section-sub">
          A lesson needs {MIN_SESSIONS_FOR_EFFICACY} injected sessions before its before/after rate means anything. Before rates
          run high, because lessons exist only where pushbacks happened.
        </p>
        {!lessons.length ? (
          <p className="muted">No live lessons yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Lesson</th>
                <th className="num">Seen in sessions</th>
                <th className="num">Injected</th>
                <th className="num">Repeats while injected</th>
                <th className="num">Rate before → after</th>
              </tr>
            </thead>
            <tbody>
              {lessons.map((l) => (
                <tr key={`${l.store}/${l.id}`}>
                  <td>
                    <span className={`chip status-${l.status}`}>{l.status}</span> {l.text}
                    {l.flagged_ineffective && <> <span className="chip bad"><Icon name="alert" /> ineffective</span></>}
                  </td>
                  <td className="num">
                    <div className="hits">
                      <div className="hits-bar" style={{ width: `${(l.hits / maxHits) * 60}px` }} />
                      {l.hits}
                    </div>
                  </td>
                  <td className="num">{l.sessions_injected}</td>
                  <td className="num">{l.sessions_injected ? l.repeats_while_injected : <span className="muted">n/a</span>}</td>
                  <td className="num">
                    {l.status !== "active" ? (
                      <span className="muted">not active</span>
                    ) : l.sessions_injected < MIN_SESSIONS_FOR_EFFICACY ? (
                      <span className="muted">measuring ({l.sessions_injected}/{MIN_SESSIONS_FOR_EFFICACY})</span>
                    ) : (
                      `${l.before.rate} → ${l.after.rate}`
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card card-pad">
        <div className="section-title"><h2>Detector precision</h2></div>
        <p className="section-sub">Of the prompts each signal captured, the share distill judged a real correction.</p>
        {!precision.length ? (
          <p className="muted">Fills in once distill has judged captured prompts.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Signal</th><th className="num">Captured</th><th className="num">Real corrections</th></tr>
            </thead>
            <tbody>
              {precision.map(([sig, p]) => (
                <tr key={sig}>
                  <td><code>{sig}</code></td>
                  <td className="num">{p.n}</td>
                  <td className="num">
                    <div className="hits">
                      <div className="hits-bar" style={{ width: `${p.precision * 60}px` }} />
                      {Math.round(p.precision * 100)}%
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
