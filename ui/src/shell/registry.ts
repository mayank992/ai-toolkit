import type { ModuleUI } from "../sdk";

// Every src/features/<name>/index.tsx is bundled and mounted under its folder name. The server lists
// which features are enabled (src/ai_toolkit/dashboard/registry.py); a feature needs both to appear.
const found = import.meta.glob<{ default: ModuleUI<any> }>("../features/*/index.tsx", { eager: true });

export const MODULE_UIS: Record<string, ModuleUI<any>> = Object.fromEntries(
  Object.entries(found).map(([path, mod]) => [path.split("/").at(-2)!, mod.default]),
);
