export type Scope = "user" | "project" | "local" | "plugin";

export interface InstructionFile {
  scope: Scope;
  path: string;
  lines: number;
  modified: string;
  sections: string[];
  rules: string[];
  git: "tracked" | "ignored" | "untracked" | "n/a";
  shared: boolean;
  /** The CLAUDE.md that pulls this file in with `@path`; empty for the CLAUDE.md files themselves. */
  imported_from: string;
}

export interface MemoryNote {
  file: string;
  path: string;
  name: string;
  type: string;
  description: string;
  modified: string;
  body: string;
  why: string;
  how: string;
  indexed: boolean;
  links: string[];
}

export interface FireStats {
  count: number;
  last: string;
  decisions: Record<string, number>;
  projects: Record<string, number>;
}

export interface Hook {
  scope: Scope;
  /** Name of the plugin that registers it; empty for hooks in settings files. */
  plugin: string;
  settings: string;
  event: string;
  matcher: string;
  command: string;
  script: string;
  name: string;
  exists: boolean;
  shared: boolean;
  logged: boolean;
  fires: FireStats;
  doc: string;
}

export interface Lesson {
  id: string;
  text: string;
  scope: string;
  store: string;
  status: string;
  why: string;
  issue: string;
  created: string;
}

export interface Problem {
  level: "error" | "warn" | "info";
  where: string;
  text: string;
  fix: string;
}

export interface Overlap {
  a: { layer: string; name: string };
  b: { layer: string; name: string };
  score: number;
}

export interface Retro {
  mr: string;
  at: string;
  title?: string;
  proposed: number;
  applied: number;
  note: string;
  share?: number | null;
  summary?: { sessions: number; prompts: number; pushback: number; threads: Record<string, number> };
}

export interface Project {
  path: string;
  name: string;
  repo: string;
  langs: string[];
  instructions: InstructionFile[];
  memory: { dir: string; notes: MemoryNote[]; index_missing_files: string[] };
  hooks: Hook[];
  lessons: Lesson[];
  retros: Retro[];
  overlaps: Overlap[];
  problems: Problem[];
}

export interface Snapshot {
  generated_at: string;
  fire_log: string;
  projects: Project[];
}
