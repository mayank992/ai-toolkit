export function ago(ts: string | null | undefined, now: number = Date.now()): string {
  if (!ts) return "never";
  const s = Math.max(0, Math.round((now - Date.parse(ts)) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const stamp = (ts: string) => ts.replace("T", " ").replace("Z", "");
