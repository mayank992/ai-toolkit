const isError = (l: string) => / error|exit \d|failed/.test(l);

export default function LogView({ lines }: { lines: string[] }) {
  if (!lines.length) return <p className="muted">hindsight.log is empty.</p>;
  return (
    <pre className="log">
      {[...lines].reverse().map((l, i) => (
        <div key={i} className={isError(l) ? "bad" : ""}>{l}</div>
      ))}
    </pre>
  );
}
