import { defineModule, Icon, ago, type ViewProps } from "@toolkit/ui";
import type { Item, Section, Snapshot, Tool, ToolExport } from "./types";
import "./styles.css";

const problems = (t: Tool) =>
  t.sections.flatMap((s) => s.items.filter((i) => i.status === "error" || i.status === "warn").map((i) => ({ ...i, section: s.title })));
const count = (t: Tool, id: string) => t.sections.find((s) => s.id === id)?.items.length ?? 0;

function Row({ item, extra }: { item: Item; extra?: string }) {
  return (
    <div className="su-row">
      <span className={`su-dot ${item.status}`} title={item.status} />
      <div className="su-name">
        {item.name}
        {item.tag && <> <span className="chip">{item.tag}</span></>}
        {extra && <div className="small muted">{extra}</div>}
      </div>
      <div>
        <div className="su-detail">{item.detail}</div>
        {item.note && <div className={`su-note ${item.status}`}>{item.note}</div>}
      </div>
    </div>
  );
}

function SectionView({ section }: { section: Section }) {
  if (!section.items.length) return <div className="card empty"><b>Nothing here</b>No {section.title.toLowerCase()} configured.</div>;
  const groups = new Map<string, Item[]>();
  for (const i of section.items) {
    const g = section.id === "mcp" || section.id === "hooks" ? "" : i.tag;
    groups.set(g, [...(groups.get(g) ?? []), i]);
  }
  return (
    <div className="card">
      {[...groups].map(([g, items]) => (
        <div key={g}>
          {g && groups.size > 1 && <div className="su-group">{g}</div>}
          {items.map((i, n) => <Row key={`${i.name}-${n}`} item={i} />)}
        </div>
      ))}
    </div>
  );
}

function ExportView({ snap, exp }: { snap: Snapshot; exp: ToolExport }) {
  const memoryFiles = exp.files.filter((f) => f.path.startsWith("memory/")).length;
  return (
    <div className="stack">
      {!snap.snapshot_dir ? (
        <div className="callout warn">
          <Icon name="alert" />
          <div>
            No snapshot folder yet. Point ai-setup at a <b>private</b> git repo, then export:
            <div className="su-cmd">ai-setup init ~/code/ai-setup --remote git@github.com:YOU/ai-setup.git{"\n"}</div>
            <div className="su-cmd">ai-setup export --push</div>
          </div>
        </div>
      ) : (
        <div className="card card-pad">
          <div className="section-title"><h2>Snapshot</h2></div>
          <p className="section-sub">
            <code>{snap.snapshot_dir}</code>
            {snap.git?.remote ? <> · origin <code>{snap.git.remote}</code></> : " · no git remote"}
            {snap.git?.dirty && <> · <span className="chip warn">uncommitted changes</span></>}
          </p>
          <div className="small">
            Last export {snap.last_export_at ? `${ago(snap.last_export_at)} from ${snap.last_export_host}` : "never"} ·{" "}
            {exp.drift.length ? <b>{exp.drift.length} file(s) changed since</b> : "up to date"} · memory{" "}
            {snap.memory ? "included" : "excluded"}
          </div>
          <div className="su-cmd">ai-setup export --push{"   "}# on this machine</div>
          <div className="su-cmd">ai-setup apply {snap.snapshot_dir} --dry-run{"   "}# on a new machine, after ./install.sh</div>
        </div>
      )}

      {exp.blocked.length > 0 && (
        <div className="callout warn">
          <Icon name="alert" />
          <div>
            <b>Export is blocked:</b> these files contain secrets. Remove the secret, then export again.
            {exp.blocked.map((b) => <div key={b.path}><code>{b.path}</code> — {b.kinds.join(", ")}</div>)}
          </div>
        </div>
      )}

      {exp.drift.length > 0 && (
        <div className="card card-pad">
          <div className="section-title"><h2>Changed since last export</h2><span className="count">{exp.drift.length}</span></div>
          {exp.drift.map((c) => (
            <div key={c.path} className="su-detail"><span className={`change-${c.change}`}>{c.change.padEnd(8)}</span> {c.path}</div>
          ))}
        </div>
      )}

      <div className="card card-pad">
        <div className="section-title"><h2>What an export writes</h2><span className="count">{exp.files.length} files</span></div>
        <p className="section-sub">
          Home paths become <code>{"{{HOME}}"}</code>, so the snapshot works under any user name. ai-toolkit's own hooks
          and commands are left out; <code>./install.sh</code> adds them back. {memoryFiles} memory file(s).
        </p>
        <div className="su-files">
          {exp.files.map((f) => (
            <div key={f.path}><span>{f.path}</span><span className="muted">{f.bytes < 1024 ? `${f.bytes} B` : `${(f.bytes / 1024).toFixed(1)} KB`}</span></div>
          ))}
        </div>
      </div>

      <div className="card card-pad">
        <div className="section-title"><h2>Secrets kept out</h2><span className="count">{exp.placeholders.length}</span></div>
        <p className="section-sub">
          Stored as <code>{"${secret:id}"}</code>. On apply, each comes from the machine's existing config, an{" "}
          <code>AI_SETUP_SECRET_*</code> env var, or a prompt.
        </p>
        {exp.placeholders.map((p) => <div key={p} className="su-detail">{p}</div>)}
        {exp.skipped.map((s) => <div key={s.path + s.reason} className="small muted">skipped {s.path}: {s.reason}</div>)}
      </div>
    </div>
  );
}

function SetupView({ snap, route, navigate }: ViewProps<Snapshot>) {
  const detected = snap.tools.filter((t) => t.detected);
  const [toolId, tabId] = route.includes(":") ? route.split(":") : [detected[0]?.id ?? "", route];
  const tool = detected.find((t) => t.id === toolId) ?? detected[0];
  if (!tool) return <div className="card empty"><b>No supported AI tool found</b>ai-setup looked for Claude Code (~/.claude).</div>;
  const exp = tool.export!;
  const probs = problems(tool);
  const tabs = [
    { id: "problems", label: "Problems", n: probs.length },
    ...tool.sections.map((s) => ({ id: s.id, label: s.title, n: s.items.length })),
    { id: "export", label: "Export", n: exp.drift.length || exp.files.length },
  ];
  const tab = tabs.some((t) => t.id === tabId) ? tabId : "problems";
  const go = (t: string) => navigate(`${tool.id}:${t}`);
  const exportState = !snap.snapshot_dir ? "Not set up" : !snap.last_export_at ? "Never" : exp.drift.length ? `${exp.drift.length} changed` : "Up to date";

  return (
    <>
      {detected.length > 1 && (
        <div className="toolbar">
          <div className="segmented">
            {detected.map((t) => (
              <button key={t.id} className={t.id === tool.id ? "active" : ""} onClick={() => navigate(`${t.id}:${tab}`)}>{t.title}</button>
            ))}
          </div>
        </div>
      )}
      <div className="su-kpis">
        <button className={`card su-kpi ${probs.some((p) => p.status === "error") ? "bad" : probs.length ? "warn" : ""}`} onClick={() => go("problems")}>
          <div className="su-kpi-label">Problems</div>
          <div className="su-kpi-value">{probs.length}</div>
          <div className="su-kpi-foot">{probs.length ? "missing scripts, paths, plugins" : "everything resolves"}</div>
        </button>
        <button className="card su-kpi" onClick={() => go("hooks")}>
          <div className="su-kpi-label">Hooks</div>
          <div className="su-kpi-value">{count(tool, "hooks")}</div>
          <div className="su-kpi-foot">across all events</div>
        </button>
        <button className="card su-kpi" onClick={() => go("mcp")}>
          <div className="su-kpi-label">MCP servers</div>
          <div className="su-kpi-value">{count(tool, "mcp")}</div>
          <div className="su-kpi-foot">user and project scope</div>
        </button>
        <button className="card su-kpi" onClick={() => go("plugins")}>
          <div className="su-kpi-label">Plugins & marketplaces</div>
          <div className="su-kpi-value">{count(tool, "plugins")}</div>
          <div className="su-kpi-foot">installed or declared</div>
        </button>
        <button className={`card su-kpi ${exp.blocked.length ? "bad" : exp.drift.length || !snap.last_export_at ? "warn" : ""}`} onClick={() => go("export")}>
          <div className="su-kpi-label">Snapshot</div>
          <div className="su-kpi-value">{exportState}</div>
          <div className="su-kpi-foot">{snap.last_export_at ? `exported ${ago(snap.last_export_at)}` : "run ai-setup export"}</div>
        </button>
      </div>
      <nav className="tabs">
        {tabs.map((t) => (
          <button key={t.id} className={t.id === tab ? "active" : ""} onClick={() => go(t.id)}>
            {t.label} <span className="count">{t.n}</span>
          </button>
        ))}
      </nav>
      <main>
        {tab === "problems" &&
          (probs.length ? (
            <div className="card">{probs.map((p, n) => <Row key={n} item={p} extra={p.section} />)}</div>
          ) : (
            <div className="card empty"><Icon name="check" /><b>No problems</b>Every hook script, MCP command and plugin resolves.</div>
          ))}
        {tool.sections.filter((s) => s.id === tab).map((s) => <SectionView key={s.id} section={s} />)}
        {tab === "export" && <ExportView snap={snap} exp={exp} />}
      </main>
    </>
  );
}

export default defineModule<Snapshot>({
  View: SetupView,
  freshKeys: (s) => s.tools.flatMap((t) => t.sections.flatMap((sec) => sec.items.map((i) => `${t.id}|${sec.id}|${i.name}|${i.detail}`))),
});
