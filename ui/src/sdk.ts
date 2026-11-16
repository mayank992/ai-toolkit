/**
 * The contract between the dashboard shell and module UIs, imported by modules as "@toolkit/ui".
 *
 * A feature mounts into the dashboard by shipping src/features/<name>/index.tsx whose default export is
 * `defineModule({ View, freshKeys })`, plus an entry in src/ai_toolkit/dashboard/registry.py naming the
 * Python module whose snapshot() feeds it. The shell owns the page frame, theme, polling and the HTTP server; the
 * module owns everything inside its own view.
 */
import type { ComponentType } from "react";

export { default as Icon, type IconName } from "./shell/Icon";
export { ago, stamp } from "./shell/time";

export interface ViewProps<S> {
  /** The module's latest snapshot, as printed by its snapshot command. */
  snap: S;
  /** Keys from `freshKeys` that appeared since the previous poll, for highlighting. */
  fresh: Set<string>;
  /** The module's part of the URL hash (after "#<module>/"), for sub-tabs and deep links. */
  route: string;
  navigate: (route: string) => void;
}

export interface ModuleUI<S = unknown> {
  View: ComponentType<ViewProps<S>>;
  /** Stable ids of the items in a snapshot; the shell diffs them between polls to compute `fresh`. */
  freshKeys?: (snap: S) => Iterable<string>;
}

export const defineModule = <S,>(m: ModuleUI<S>): ModuleUI<S> => m;
