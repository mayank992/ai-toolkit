import { Icon } from "@toolkit/ui";

const isError = (l: string) => / error|exit \d|failed/.test(l);

export default function LogView({ lines }: { lines: string[] }) {
  if (!lines.length) return <div className="card empty"><Icon name="clock" /><b>Log is empty</b>hindsight.log has no entries yet.</div>;
  return (
    <div className="card">
      <pre className="log">
        {[...lines].reverse().map((l, i) => (
          <div key={i} className={isError(l) ? "bad" : ""}>{l}</div>
        ))}
      </pre>
    </div>
  );
}
