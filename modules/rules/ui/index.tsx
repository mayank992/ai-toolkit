import { useState } from "react";
import { defineModule, Icon, ago, type ViewProps } from "@toolkit/ui";
import type { Hook, InstructionFile, MemoryNote, Project, Scope, Snapshot } from "./types";
import "./styles.css";

const tilde = (p: string) => p.replace(/^\/Users\/[^/]+|^\/home\/[^/]+/, "~");
const SCOPE_LABEL: Record<Scope, string> = { user: "personal · all projects", project: "shared · committed", local: "personal · this project" };
const scopeChip = (s: Scope) => <span className={`chip ru-scope ${s}`}>{SCOPE_LABEL[s]}</span>;

function gitChip(f: InstructionFile) {
  if (f.git === "ignored") return <span className="chip good">hidden from git</span>;
  if (f.git === "untracked") return <span className="chip bad">shows in git status</span>;
  if (f.git === "tracked") return <span className="chip">committed</span>;
  return null;
}

function StackView({ p, go }: { p: Project; go: (t: string) => void }) {
  const personalHooks = p.hooks.filter((h) => h.scope !== "project");
  const layers = [
    ...p.instructions.map((f) => ({
      key: f.path, icon: "layers" as const, title: f.scope === "local" ? "CLAUDE.local.md" : "CLAUDE.md", scope: f.scope,
      sub: `${tilde(f.path)} · ${f.rules.length} rules in ${f.sections.length} sections · ${f.lines} lines`, extra: gitChip(f), tab: `file:${f.path}`,
    })),
    { key: "mem", icon: "bookmark" as const, title: "Memory", scope: "local" as Scope,
      sub: `${p.memory.notes.length} notes · ${tilde(p.memory.dir)}`, extra: null, tab: "memory" },
    { key: "hooks", icon: "ban" as const, title: "Hooks", scope: null,
      sub: `${personalHooks.length} personal, ${p.hooks.length - personalHooks.length} shared with the repo`, extra: null, tab: "hooks" },
    { key: "lessons", icon: "inject" as const, title: "hindsight lessons", scope: "user" as Scope,
      sub: `${p.lessons.filter((l) => l.status === "active").length} active, ${p.lessons.filter((l) => l.status === "candidate").length} candidates`, extra: null, tab: "lessons" },
  ];
  return (
    <div className="stack">
      <p className="section-sub">What Claude Code reads in <code>{tilde(p.path)}</code>, in load order. Everything marked personal stays on this machine.</p>
      <div className="card">
        {layers.map((l, i) => (
          <div key={l.key} className="item clickable" onClick={() => go(l.tab)}>
            <div className="item-icon ru-step">{i + 1}</div>
            <div className="item-body">
              <div className="item-title">{l.title} {l.scope && scopeChip(l.scope)} {l.extra}</div>
              <div className="item-sub">{l.sub}</div>
            </div>
            <div className="item-side"><Icon name="arrow" /></div>
          </div>
        ))}
      </div>
      {p.overlaps.length > 0 && (
        <div className="card card-pad">
          <div className="section-title"><h2>Said in more than one place</h2><span className="count">{p.overlaps.length}</span></div>
          <p className="section-sub">Rules in different layers that share most of their wording. Keep one, or make sure they agree.</p>
          {p.overlaps.map((o, i) => (
            <div key={i} className="ru-overlap">
              <span className="chip">{o.a.layer}</span> <span>{o.a.name}</span>
              <span className="muted">↔</span>
              <span className="chip">{o.b.layer}</span> <span>{o.b.name}</span>
              <span className="muted small">{Math.round(o.score * 100)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FileView({ f }: { f: InstructionFile }) {
  return (
    <div className="card card-pad">
      <div className="section-title"><h2>{tilde(f.path)}</h2>{scopeChip(f.scope)} {gitChip(f)}</div>
      <p className="section-sub">Changed {ago(f.modified)} · {f.lines} lines</p>
      <ul className="ru-rules">{f.rules.map((r, i) => <li key={i}>{r}</li>)}</ul>
    </div>
  );
}

function MemoryView({ notes }: { notes: MemoryNote[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!notes.length) return <div className="card empty"><b>No memory notes</b>Claude saves them here as you correct it.</div>;
  const sorted = [...notes].sort((a, b) => (b.modified || "").localeCompare(a.modified || ""));
  return (
    <div className="card">
      {sorted.map((n) => (
        <div key={n.file} className="item clickable" onClick={() => setOpen(open === n.file ? null : n.file)}>
          <div className={`item-icon ru-type ${n.type}`}><Icon name="bookmark" /></div>
          <div className="item-body">
            <div className="item-title">{n.name} {!n.indexed && <span className="chip warn">not in MEMORY.md</span>} {n.type && <span className="chip">{n.type}</span>}</div>
            <div className="item-sub">{n.description}</div>
            {open === n.file && (
              <div className="ru-note">
                {n.why && <p><b>Why</b> {n.why}</p>}
                {n.how && <p><b>How to apply</b> {n.how}</p>}
                {!n.why && !n.how && <pre>{n.body}</pre>}
                {n.links.length > 0 && <p className="small muted">Links: {n.links.join(", ")}</p>}
                <p className="small muted">{tilde(n.path)}</p>
              </div>
            )}
          </div>
          <div className="item-side small muted">{n.modified ? ago(n.modified) : ""}</div>
        </div>
      ))}
    </div>
  );
}

function HookRow({ h }: { h: Hook }) {
  const d = h.fires.decisions;
  return (
    <div className="ru-hook">
      <div><b>{h.name}</b>{!h.exists && <> <span className="chip bad">script missing</span></>}<div className="small muted">{h.doc || tilde(h.command)}</div></div>
      <div className="ru-mono">{h.event}{h.matcher ? ` · ${h.matcher}` : ""}</div>
      <div className="ru-fires">
        {h.logged ? (
          <>
            <b>{h.fires.count}</b> in 30d
            {Object.keys(d).length > 0 && <div className="small muted">{Object.entries(d).map(([k, v]) => `${v} ${k}`).join(" · ")}</div>}
            {h.fires.last && <div className="small muted">last {ago(h.fires.last)}</div>}
          </>
        ) : <span className="small muted">not logged</span>}
      </div>
    </div>
  );
}

function HooksView({ hooks }: { hooks: Hook[] }) {
  const groups: [string, Hook[]][] = [
    ["This project, personal", hooks.filter((h) => h.scope === "local")],
    ["All projects, personal", hooks.filter((h) => h.scope === "user")],
    ["Shared with the repo", hooks.filter((h) => h.scope === "project")],
  ];
  return (
    <div className="stack">
      {groups.filter(([, hs]) => hs.length).map(([title, hs]) => (
        <div key={title} className="card">
          <div className="ru-group">{title} <span className="count">{hs.length}</span></div>
          {hs.map((h, i) => <HookRow key={`${h.event}-${h.name}-${i}`} h={h} />)}
        </div>
      ))}
    </div>
  );
}

function LessonsView({ p }: { p: Project }) {
  if (!p.lessons.length) return <div className="card empty"><b>No hindsight lessons</b>Lessons appear after the same pushback recurs.</div>;
  const order = ["active", "candidate"];
  const sorted = [...p.lessons].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status));
  return (
    <div className="card">
      {sorted.map((l) => (
        <div key={l.id} className="item">
          <div className="item-icon ru-type"><Icon name="inject" /></div>
          <div className="item-body">
            <div className="item-title">{l.text} <span className={`chip ${l.status === "active" ? "good" : ""}`}>{l.status}</span></div>
            <div className="item-sub">{l.why}</div>
            <div className="small muted">{l.id} · {l.scope.replace(/^repo:.*\//, "repo:")} · {l.store} store{l.created ? ` · ${l.created}` : ""}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function RetrosView({ p }: { p: Project }) {
  return (
    <div className="stack">
      <div className="card card-pad">
        <div className="section-title"><h2>Refresh after a merge</h2></div>
        <p className="section-sub">In Claude Code, in this project, run the retro for the merged MR. It gathers the transcripts, the MR comments and Claude's share of the merged code, then proposes rule changes for you to approve.</p>
        <div className="ru-cmd">/mr-retro &lt;MR number or URL&gt;</div>
      </div>
      {p.retros.length === 0 ? (
        <div className="card empty"><b>No retros yet</b>Each finished retro is listed here.</div>
      ) : (
        <div className="card">
          {p.retros.map((r) => (
            <div key={r.mr + r.at} className="item">
              <div className="item-icon ru-type"><Icon name="curate" /></div>
              <div className="item-body">
                <div className="item-title">!{r.mr} {r.title}</div>
                <div className="item-sub">
                  {r.applied} of {r.proposed} proposed changes applied
                  {r.share != null && <> · {r.share}% of new lines from Claude</>}
                  {r.summary && <> · {r.summary.pushback} pushback prompts in {r.summary.sessions} sessions</>}
                </div>
                {r.note && <div className="small muted">{r.note}</div>}
              </div>
              <div className="item-side small muted">{ago(r.at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ProblemsView({ p }: { p: Project }) {
  if (!p.problems.length) return <div className="card empty"><Icon name="check" /><b>No problems</b>Personal files are hidden from git, every note is indexed and every hook script exists.</div>;
  return (
    <div className="card">
      {p.problems.map((x, i) => (
        <div key={i} className="item">
          <div className={`item-icon ru-level ${x.level}`}><Icon name={x.level === "info" ? "message" : "alert"} /></div>
          <div className="item-body">
            <div className="item-title">{x.text}</div>
            <div className="item-sub">{tilde(x.where)}</div>
            {x.fix && <div className="ru-cmd">{x.fix}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

function RulesView({ snap, route, navigate }: ViewProps<Snapshot>) {
  const projects = snap.projects;
  if (!projects.length) return <div className="card empty"><b>No projects with rules</b>Open a project in Claude Code first.</div>;
  const [pname, ...rest] = route.split(":");
  const p = projects.find((x) => x.name === pname) ?? projects[0];
  const tab = rest.join(":") || "stack";
  const go = (t: string) => navigate(`${p.name}:${t}`);
  const errs = p.problems.filter((x) => x.level !== "info").length;
  const fired = p.hooks.reduce((n, h) => n + h.fires.count, 0);
  const rules = p.instructions.reduce((n, f) => n + f.rules.length, 0);
  const tabs = [
    { id: "stack", label: "Stack", n: p.instructions.length + 3 },
    ...p.instructions.map((f) => ({ id: `file:${f.path}`, label: f.scope === "local" ? "CLAUDE.local.md" : f.scope === "user" ? "User CLAUDE.md" : "CLAUDE.md", n: f.rules.length })),
    { id: "memory", label: "Memory", n: p.memory.notes.length },
    { id: "hooks", label: "Hooks", n: p.hooks.length },
    { id: "lessons", label: "Lessons", n: p.lessons.length },
    { id: "retros", label: "Retros", n: p.retros.length },
    { id: "problems", label: "Problems", n: p.problems.length },
  ];
  const file = p.instructions.find((f) => `file:${f.path}` === tab);

  return (
    <>
      <div className="toolbar">
        <select className="ru-select" value={p.name} onChange={(e) => navigate(`${e.target.value}:${tab.startsWith("file:") ? "stack" : tab}`)}>
          {projects.map((x) => <option key={x.path} value={x.name}>{x.name} — {tilde(x.path)}</option>)}
        </select>
        {p.repo && <span className="small muted">{p.repo}</span>}
      </div>
      <div className="ru-kpis">
        <button className="card ru-kpi" onClick={() => go("stack")}>
          <div className="ru-kpi-label">Instructions</div><div className="ru-kpi-value">{rules}</div>
          <div className="ru-kpi-foot">rules in {p.instructions.length} file(s)</div>
        </button>
        <button className="card ru-kpi" onClick={() => go("memory")}>
          <div className="ru-kpi-label">Memory</div><div className="ru-kpi-value">{p.memory.notes.length}</div>
          <div className="ru-kpi-foot">notes for this project</div>
        </button>
        <button className="card ru-kpi" onClick={() => go("hooks")}>
          <div className="ru-kpi-label">Hooks</div><div className="ru-kpi-value">{p.hooks.length}</div>
          <div className="ru-kpi-foot">{fired} logged fires in 30 days</div>
        </button>
        <button className="card ru-kpi" onClick={() => go("lessons")}>
          <div className="ru-kpi-label">Lessons</div><div className="ru-kpi-value">{p.lessons.filter((l) => l.status === "active").length}</div>
          <div className="ru-kpi-foot">active, {p.lessons.filter((l) => l.status === "candidate").length} candidates</div>
        </button>
        <button className={`card ru-kpi ${errs ? "warn" : ""}`} onClick={() => go(errs ? "problems" : "retros")}>
          <div className="ru-kpi-label">{errs ? "Problems" : "Last retro"}</div>
          <div className="ru-kpi-value">{errs ? errs : p.retros[0] ? `!${p.retros[0].mr}` : "None"}</div>
          <div className="ru-kpi-foot">{errs ? "need a fix" : p.retros[0] ? ago(p.retros[0].at) : "run /mr-retro after a merge"}</div>
        </button>
      </div>
      <nav className="tabs">
        {tabs.map((t) => (
          <button key={t.id} className={t.id === tab ? "active" : ""} onClick={() => go(t.id)}>{t.label} <span className="count">{t.n}</span></button>
        ))}
      </nav>
      <main>
        {tab === "stack" && <StackView p={p} go={go} />}
        {file && <FileView f={file} />}
        {tab === "memory" && <MemoryView notes={p.memory.notes} />}
        {tab === "hooks" && <HooksView hooks={p.hooks} />}
        {tab === "lessons" && <LessonsView p={p} />}
        {tab === "retros" && <RetrosView p={p} />}
        {tab === "problems" && <ProblemsView p={p} />}
      </main>
    </>
  );
}

export default defineModule<Snapshot>({
  View: RulesView,
  freshKeys: (s) => s.projects.flatMap((p) => [
    ...p.memory.notes.map((n) => `${p.path}|mem|${n.file}|${n.modified}`),
    ...p.retros.map((r) => `${p.path}|retro|${r.mr}|${r.at}`),
    ...p.hooks.map((h) => `${p.path}|hook|${h.name}|${h.fires.count}`),
  ]),
});
