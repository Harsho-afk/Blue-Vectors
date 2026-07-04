export default function BreachResults({ lookup }) {
  const result = lookup.result || {};
  const breaches = result.breaches || [];

  return (
    <div className="breach-results">
      <div className="breach-results__header">
        <span className="breach-results__title">BREACH LOOKUP</span>
        <span className="breach-results__email">
          {result.email || lookup.input_value}
        </span>
        {result.is_mock && (
          <span className="breach-results__mock-badge">DEMO DATA</span>
        )}
      </div>

      {result.error && (
        <div style={{ padding: "8px 16px", fontSize: 10, color: "#F6C90E" }}>
          {result.error}
        </div>
      )}

      {result.total_breaches === 0 && !result.error ? (
        <p className="breach-results__clean">No breaches found ✓</p>
      ) : breaches.length > 0 ? (
        <div className="breach-results__list">
          <span className="breach-results__count">
            {result.total_breaches} breach{result.total_breaches !== 1 ? "es" : ""} found
          </span>
          {breaches.map((breach, i) => (
            <div className="breach-result-row" key={breach.name || i}>
              <span className="breach-result-row__name">{breach.name}</span>
              <span className="breach-result-row__date">
                {breach.breach_date || breach.date || ""}
              </span>
              <div className="breach-result-row__data-classes">
                {(breach.data_classes || []).map(dc => (
                  <span className="breach-result-row__tag" key={dc}>{dc}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
