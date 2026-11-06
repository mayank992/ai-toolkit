import type { ModuleUI } from "./sdk";

// Every modules/<name>/ui/index.tsx is bundled and mounted under its folder name; no list to maintain.
const found = import.meta.glob<{ default: ModuleUI<any> }>("../../modules/*/ui/index.tsx", { eager: true });

export const MODULE_UIS: Record<string, ModuleUI<any>> = Object.fromEntries(
  Object.entries(found).map(([path, mod]) => [path.split("/").at(-3)!, mod.default]),
);
