export default function StatPill({ label, value, color }) {
  return (
    <div className="stat-pill">
      <span className="stat-pill__label">{label}</span>
      <span className="stat-pill__value" style={color ? { color } : undefined}>
        {value ?? "—"}
      </span>
    </div>
  );
}
