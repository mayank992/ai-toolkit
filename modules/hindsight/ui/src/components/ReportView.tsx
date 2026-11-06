import type { Report } from "../types";

export default function ReportView({ report }: { report: Report }) {
  const max = Math.max(0.01, ...report.weekly.map((w) => w.rate));
  const precision = Object.entries(report.precision).sort((a, b) => b[1].n - a[1].n);

  return (
    <div className="report">
      <section className="card">
        <h3>Pushbacks per session, by week</h3>
        <p className="small muted">
          {report.totals.pushbacks} pushbacks over {report.totals.sessions} sessions (rate {report.totals.rate})
        </p>
        {!report.weekly.length && <p className="muted">No sessions recorded yet. SessionStart writes them.</p>}
        <div className="bars">
          {report.weekly.map((w) => (
            <div key={w.week} className="bar-row">
              <span className="mono small">{w.week}</span>
              <div className="bar-track">
                <div className="bar" style={{ width: `${(w.rate / max) * 100}%` }} />
              </div>
              <span className="mono small">{w.rate.toFixed(2)} ({w.pushbacks}/{w.sessions})</span>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>Lesson efficacy</h3>
        <p className="small muted">
          Before rates are biased upward, because lessons exist because pushbacks happened. Trust the weekly trend more.
        </p>
        {!report.lessons.length ? (
          <p className="muted">No live lessons yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Lesson</th>
                <th>Status</th>
                <th>Hits</th>
                <th>Injected</th>
                <th>Before → after</th>
                <th>Repeats</th>
                <th>Prevented</th>
              </tr>
            </thead>
            <tbody>
              {report.lessons.map((l) => (
                <tr key={`${l.store}/${l.id}`}>
                  <td><code>{l.id}</code> {l.text} {l.flagged_ineffective && <span className="chip bad">ineffective</span>}</td>
                  <td>{l.status}</td>
                  <td>{l.hits}</td>
                  <td>{l.sessions_injected}</td>
                  <td>{l.activated ? `${l.before.rate} → ${l.after.rate}` : "not active"}</td>
                  <td>{l.repeats_while_injected}</td>
                  <td>{l.prevented}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3>Detector precision</h3>
        <p className="small muted">Share of each signal's captured prompts that distill judged real, not noise.</p>
        {!precision.length ? (
          <p className="muted">Fills in once distill has judged captured prompts.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Signal</th><th>n</th><th>Precision</th></tr>
            </thead>
            <tbody>
              {precision.map(([sig, p]) => (
                <tr key={sig}><td className="mono">{sig}</td><td>{p.n}</td><td>{Math.round(p.precision * 100)}%</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
