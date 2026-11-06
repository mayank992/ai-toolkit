export type Health = "off" | "waiting" | "stalled" | "ok";
export type StageId = "capture" | "queue" | "distill" | "curate" | "store" | "inject";
export type LessonStatus = "candidate" | "active" | "retired" | "dismissed";
export type MomentKind = "prompt" | "rejected_tool" | "explicit";

export interface Stage {
  id: StageId;
  label: string;
  health: Health;
  note: string;
  metric: string;
  last_at: string | null;
}

export interface Hook {
  step: number;
  event: string;
  script: string;
  registered: boolean;
}

export interface TurnContext {
  request?: string;
  actions?: string[];
  reply?: string;
  edited?: boolean;
}

export interface Moment {
  id: string;
  ts: string;
  session_id: string;
  kind: MomentKind;
  clause: string;
  signals?: string[];
  repo: string;
  store: string;
  langs?: string[];
  tool?: string;
  file_ext?: string;
  rejected?: string;
  after_edit?: boolean;
  context?: TurnContext;
}

export interface Lesson {
  id: string;
  text: string;
  scope: string;
  keywords: string[];
  files: string[];
  status: LessonStatus;
  created: string;
  pinned: boolean;
  reason: string;
  merged: string[];
  why: string;
  issue: string;
  store: string;
  file: string;
}

export interface Store {
  name: string;
  path: string;
  remote: string;
  match: string[];
  default: boolean;
  initialized: boolean;
  lessons: Lesson[];
}

export interface HsEvent {
  t: string;
  ts: string;
  _store: string;
  session_id?: string;
  repo?: string;
  lesson?: string;
  kind?: string;
  phase?: string;
  noise?: boolean;
  ids?: string[];
  by?: string;
  reason?: string;
  into?: string;
  [key: string]: unknown;
}

interface RateWindow {
  sessions: number;
  pushbacks: number;
  rate: number;
}

export interface LessonEfficacy {
  id: string;
  text: string;
  scope: string;
  status: LessonStatus;
  store: string;
  pinned: boolean;
  hits: number;
  last_hit: string;
  sessions_injected: number;
  last_inject: string;
  activated: string;
  repeats_while_injected: number;
  before: RateWindow;
  after: RateWindow;
  prevented: number;
  flagged_ineffective: boolean;
}

export interface Report {
  weekly: { week: string; sessions: number; pushbacks: number; rate: number }[];
  totals: { sessions: number; pushbacks: number; rate: number };
  lessons: LessonEfficacy[];
  counts: Record<LessonStatus, number>;
  precision: Record<string, { n: number; precision: number }>;
  pushback_kinds: Record<string, number>;
  dismissed: number;
}

export interface ProcessedMoment {
  ts: string;
  store: string;
  session_id: string;
  repo: string;
  kind: MomentKind;
  signals: string[];
  tool: string;
  noise: boolean;
  lesson: string | null;
  lesson_text: string;
  lesson_status: LessonStatus | "";
}

export interface RepoContext {
  repo: string;
  langs: string[];
  last_seen: string;
  lessons: { id: string; text: string; scope: string; store: string }[];
  rendered: string;
  last_inject: { ts: string; ids: string[] } | null;
}

export interface Snapshot {
  generated_at: string;
  stages: Stage[];
  hooks: Hook[];
  queue: Moment[];
  processed: ProcessedMoment[];
  in_context: RepoContext[];
  stores: Store[];
  events: HsEvent[];
  report: Report;
  log: string[];
}
