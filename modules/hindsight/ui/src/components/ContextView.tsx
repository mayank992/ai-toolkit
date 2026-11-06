import type { RepoContext } from "../types";
import { ago } from "../time";

export default function ContextView({ repos, injectOn }: { repos: RepoContext[]; injectOn: boolean }) {
  return (
    <>
      <p className="explain small">
        This is what Claude actually receives. At the start of each session in a repo, the SessionStart hook adds
        these lessons to Claude's context. Only <b>active</b> lessons are injected. Candidates must recur in a
        second session first.
        {!injectOn && <span className="warn-text"> SessionStart isn't registered, so nothing is injected. Run ./install.sh.</span>}
      </p>
      {!repos.length && <p className="muted">No repos seen yet.</p>}
      <div className="lessons">
        {repos.map((r) => (
          <div key={r.repo} className="card">
            <div className="lesson-head">
              <b>{r.repo}</b>
              <span className="muted small">
                {r.langs.join(", ") || "no langs"} · last active {ago(r.last_seen)} · last injected{" "}
                {r.last_inject ? `${ago(r.last_inject.ts)} (${r.last_inject.ids.length} lessons)` : "never"}
              </span>
            </div>
            {r.lessons.length ? (
              <pre className="log">{r.rendered}</pre>
            ) : (
              <p className="muted small">Nothing would be injected here yet. No active lessons match this repo.</p>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
