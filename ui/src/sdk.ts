/**
 * The contract between the dashboard shell and feature views, imported by features as "@toolkit/ui".
 *
 * A feature mounts into the dashboard by shipping src/features/<name>/index.tsx whose default export is
 * `defineFeature({ View, freshKeys })`, plus an entry in src/ai_toolkit/dashboard/registry.py naming the
 * Python module whose snapshot() feeds it. The shell owns the page frame, theme, polling and the HTTP server; the
 * feature owns everything inside its own view.
 */
import type { ComponentType } from "react";

export { default as Icon, type IconName } from "./shell/Icon";
export { ago, stamp } from "./shell/time";

export interface ViewProps<S> {
  /** The feature's latest snapshot, as printed by its snapshot command. */
  snap: S;
  /** Keys from `freshKeys` that appeared since the previous poll, for highlighting. */
  fresh: Set<string>;
  /** The feature's part of the URL hash (after "#<feature>/"), for sub-tabs and deep links. */
  route: string;
  navigate: (route: string) => void;
}

export interface FeatureUI<S = unknown> {
  View: ComponentType<ViewProps<S>>;
  /** Stable ids of the items in a snapshot; the shell diffs them between polls to compute `fresh`. */
  freshKeys?: (snap: S) => Iterable<string>;
}

export const defineFeature = <S,>(m: FeatureUI<S>): FeatureUI<S> => m;
