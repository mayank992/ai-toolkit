export type Status = "ok" | "info" | "warn" | "error";

export interface Item {
  name: string;
  detail: string;
  status: Status;
  note: string;
  tag: string;
}

export interface Section {
  id: string;
  title: string;
  items: Item[];
}

export interface Change {
  path: string;
  change: "added" | "changed" | "removed";
}

export interface ToolExport {
  files: { path: string; bytes: number }[];
  placeholders: string[];
  skipped: { path: string; reason: string }[];
  blocked: { path: string; kinds: string[] }[];
  drift: Change[];
}

export interface Tool {
  id: string;
  title: string;
  detected: boolean;
  sections: Section[];
  export?: ToolExport;
}

export interface Snapshot {
  generated_at: string;
  snapshot_dir: string;
  snapshot_exists: boolean;
  memory: boolean;
  last_export_at: string | null;
  last_export_host: string | null;
  git: { remote: string; dirty: boolean; last_commit_at: string | null } | null;
  tools: Tool[];
}
