import { useBlink } from "../lib/hooks";

export default function Blink() {
  const on = useBlink();
  return (
    <span style={{ opacity: on ? 1 : 0, color: "#4FFFB0", fontFamily: "'JetBrains Mono', monospace" }}>
      █
    </span>
  );
}
