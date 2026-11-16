import { useEffect, useState } from "react";
import { useSnapshot } from "./useSnapshot";
import { ago } from "./time";
import Icon from "./Icon";
import { FEATURE_UIS } from "./registry";
import FeatureBoundary from "./FeatureBoundary";

interface FeatureInfo {
  name: string;
  title: string;
  tagline: string;
}
type Theme = "light" | "dark";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () =>
      (localStorage.getItem("toolkit-theme") as Theme | null) ??
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    localStorage.setItem("toolkit-theme", next);
    setTheme(next);
  };
  return [theme, toggle];
}

function useFeatures(): FeatureInfo[] | string | undefined {
  const [mods, setMods] = useState<FeatureInfo[] | string>();
  useEffect(() => {
    fetch("/api/features")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setMods, (e) => setMods(String(e)));
  }, []);
  return mods;
}

/** "#<feature>/<route>" -> [feature, route]. An unknown first segment is a route of the default feature. */
function parseHash(names: string[]): [string, string] {
  const h = decodeURIComponent(location.hash.slice(1));
  const slash = h.indexOf("/");
  const head = slash < 0 ? h : h.slice(0, slash);
  if (names.includes(head)) return [head, slash < 0 ? "" : h.slice(slash + 1)];
  return [names[0] ?? "", h];
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [paused, setPaused] = useState(false);
  const mods = useFeatures();
  const list = Array.isArray(mods) ? mods : [];
  const [[active, route], setLoc] = useState<[string, string]>(["", ""]);

  useEffect(() => {
    if (!list.length) return;
    const sync = () => setLoc(parseHash(list.map((m) => m.name)));
    sync();
    addEventListener("hashchange", sync);
    return () => removeEventListener("hashchange", sync);
  }, [mods]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = (mod: string, r = "") => {
    history.replaceState(null, "", `#${mod}${r ? `/${r}` : ""}`);
    setLoc([mod, r]);
  };

  const info = list.find((m) => m.name === active);
  const ui = FEATURE_UIS[active];
  const feed = useSnapshot<unknown>(info && ui ? `/api/features/${active}/snapshot` : null, 3000, paused, ui?.freshKeys);
  const snap = feed.state === "ready" ? feed.snap : feed.state === "error" ? feed.last : undefined;
  const fresh = feed.state === "ready" ? feed.fresh : new Set<string>();
  const stamp = (snap as { generated_at?: string } | undefined)?.generated_at;
  const liveClass = feed.state === "error" ? "error" : paused ? "paused" : "";
  const liveText =
    feed.state === "error" ? "Can't load snapshot" : paused ? "Paused" : snap ? `Live · updated ${ago(stamp)}` : "Connecting";

  return (
    <div className="app">
      <header className="top">
        <div className="brand-mark"><Icon name="layers" /></div>
        <div className="brand">
          <h1>ai-toolkit</h1>
          <p>Everything your Claude Code toolkit is doing, live and read-only</p>
        </div>
        <div className="spacer" />
        {info && (
          <span className={`live ${liveClass}`} title={feed.state === "error" ? feed.message : undefined}>
            <span className="live-dot" /> {liveText}
          </span>
        )}
        <button onClick={() => setPaused((p) => !p)}>
          <Icon name={paused ? "play" : "pause"} /> {paused ? "Resume" : "Pause"}
        </button>
        <button className="icon-btn" onClick={toggleTheme} title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          <Icon name={theme === "dark" ? "sun" : "moon"} />
        </button>
      </header>

      {typeof mods === "string" ? (
        <div className="card empty"><b>Dashboard server unreachable</b>{mods}. Start it with <code>ait ui</code>.</div>
      ) : !mods ? (
        <div className="card empty"><b>Loading features…</b></div>
      ) : !list.length ? (
        <div className="card empty"><b>No feature has a dashboard yet</b>Enable a feature in <code>~/.config/ai-toolkit/config.json</code>, or add one to <code>src/ai_toolkit/dashboard/registry.py</code>.</div>
      ) : (
        <div className="shell">
          <nav className="side" aria-label="Features">
            {list.map((m) => (
              <button key={m.name} className={m.name === active ? "active" : ""} onClick={() => go(m.name)}>
                <span className="side-title">{m.title}</span>
                <span className="side-sub">{m.tagline}</span>
              </button>
            ))}
          </nav>
          <section className="feature" key={active}>
            {!ui ? (
              <div className="card empty">
                <b>{info?.title ?? active} isn't in this build</b>
                Rebuild the dashboard to pick up new feature views: <code>pnpm -C ui build</code>
              </div>
            ) : !snap ? (
              <div className="card empty">
                <b>{feed.state === "error" ? "Snapshot failed" : "Loading snapshot…"}</b>
                {feed.state === "error" ? <pre className="err">{feed.message}</pre> : null}
              </div>
            ) : (
              <FeatureBoundary name={info?.title ?? active}>
                <ui.View snap={snap} fresh={fresh} route={route} navigate={(r) => go(active, r)} />
              </FeatureBoundary>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
