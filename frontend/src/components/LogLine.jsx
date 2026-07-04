export default function LogLine({ line }) {
  const cls = line.startsWith("[ERR]") ? "log-line--err"
    : line.startsWith("[OK]")          ? "log-line--ok"
    : line.startsWith("[>]")           ? "log-line--gt"
    : "log-line--dim";
  return <div className={`log-line ${cls}`}>{line}</div>;
}
