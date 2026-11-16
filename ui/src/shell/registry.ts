import type { FeatureUI } from "../sdk";

// Every src/features/<name>/index.tsx is bundled and mounted under its folder name. The server lists
// which features are enabled (src/ai_toolkit/dashboard/registry.py); a feature needs both to appear.
const found = import.meta.glob<{ default: FeatureUI<any> }>("../features/*/index.tsx", { eager: true });

export const FEATURE_UIS: Record<string, FeatureUI<any>> = Object.fromEntries(
  Object.entries(found).map(([path, mod]) => [path.split("/").at(-2)!, mod.default]),
);
