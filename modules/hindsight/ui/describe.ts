import type { Moment, MomentKind } from "./types";

export const KIND_LABEL: Record<MomentKind, string> = {
  prompt: "Correction",
  rejected_tool: "Rejected call",
  explicit: "Saved lesson",
};

export interface Described {
  title: string;
  reason: string;
  reactingTo: string;
}

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

// Moments captured before the context fix kept the first actions and ended in "… N more", so their
// real last action is unknown.
const lastAction = (m: Moment) => {
  const acts = m.context?.actions ?? [];
  if (!acts.length || /^… \d+ more$/.test(acts[acts.length - 1])) return "";
  return clip(acts[acts.length - 1], 90);
};

export function describe(m: Moment): Described {
  const reactingTo = clip(m.context?.request ?? "", 140);
  switch (m.kind) {
    case "rejected_tool": {
      const call = m.rejected || `${m.tool ?? "a tool call"}${m.file_ext ? ` on a .${m.file_ext} file` : ""}`;
      return { title: call, reason: m.clause || "no reason typed", reactingTo };
    }
    case "prompt":
      return {
        title: m.clause,
        reason: m.after_edit ? `right after Claude edited files (${lastAction(m) || "edit"})` : lastAction(m) && `after: ${lastAction(m)}`,
        reactingTo,
      };
    case "explicit":
      return { title: m.clause, reason: "saved directly with /lesson", reactingTo: "" };
  }
}
