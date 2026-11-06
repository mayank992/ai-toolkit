import type { RepoContext } from "../types";
import { ago } from "../time";
import { shortRepo } from "../repo";
import Icon from "../Icon";

function parseWhy(rendered: string, id: string): string {
  const line = rendered.split("\n").find((l) => l.includes(`[${id}]`)) ?? "";
  const m = line.match(/\(why: (.*)\)$/);
  return m ? m[1] : "";
}

export default function ContextView({ repos, injectOn }: { repos: RepoContext[]; injectOn: boolean }) {
  return (
    <>
      {!injectOn && (
        <div className="callout warn">
          <Icon name="alert" />
          <div>SessionStart isn't registered, so nothing is injected yet. Run <code>./install.sh</code>.</div>
        </div>
      )}
      <div className="callout">
        <Icon name="inject" />
        <div>
          This is what Claude receives. When a session starts in a repo, these lessons are added to its context. Only active
          lessons are injected, best first, up to 15 lines.
        </div>
      </div>
      {!repos.length ? (
        <div className="card empty"><Icon name="repo" /><b>No repos seen yet</b>Work in a repo and it will show up here.</div>
      ) : (
        <div className="stack">
          {[...repos].sort((a, b) => b.lessons.length - a.lessons.length).map((r) => (
            <section key={r.repo} className="card card-pad">
              <div className="ctx-head">
                <Icon name="repo" />
                <h2 style={{ fontSize: 15 }} title={r.repo}>{shortRepo(r.repo)}</h2>
                {r.langs.map((l) => <span key={l} className="chip">{l}</span>)}
                <span className="spacer" />
                <span className="small muted">
                  {r.last_inject ? `last injected ${ago(r.last_inject.ts)}` : "not injected yet"}
                  {r.last_seen && ` · active ${ago(r.last_seen)}`}
                </span>
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>{r.repo}</div>
              {r.lessons.length ? (
                <>
                  <ul className="ctx-lines">
                    {r.lessons.map((l) => (
                      <li key={l.id}>
                        {l.text}
                        {parseWhy(r.rendered, l.id) && <div className="why">Why: {parseWhy(r.rendered, l.id)}</div>}
                      </li>
                    ))}
                  </ul>
                  <details>
                    <summary>Exact text Claude sees</summary>
                    <pre>{r.rendered}</pre>
                  </details>
                </>
              ) : (
                <p className="small muted" style={{ marginBottom: 0 }}>Nothing yet. No active lessons apply to this repo.</p>
              )}
            </section>
          ))}
        </div>
      )}
    </>
  );
}
