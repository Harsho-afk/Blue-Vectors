export default function PhoneResults({ lookup }) {
  const r = lookup.result || {};

  return (
    <div className="phone-results">
      <div className="phone-results__header">
        <span className="phone-results__title">PHONE LOOKUP</span>
        <span className="phone-results__number">{r.phone_number || lookup.input_value}</span>
      </div>

      {/* ── Carrier block ── */}
      <div className="phone-results__section">
        <span className="phone-results__section-label">CARRIER</span>
        <div className="phone-results__grid">
          <PhoneField label="Valid"       value={r.valid == null ? null : r.valid ? "YES" : "NO"} ok={r.valid} />
          <PhoneField label="Line Type"   value={r.line_type} />
          <PhoneField label="Carrier"     value={r.carrier} />
          <PhoneField label="Country"     value={r.country_name} sub={r.country_code} />
          <PhoneField label="Region"      value={r.location} />
        </div>
      </div>

      {/* ── Telegram block ── */}
      <div className="phone-results__section">
        <span className="phone-results__section-label">TELEGRAM</span>
        {r.telegram_user_id ? (
          <div className="phone-results__profile-row">
            {r.telegram_profile_photo_url && (
              <img
                src={r.telegram_profile_photo_url}
                className="phone-results__avatar"
                alt="Telegram avatar"
                onError={e => { e.target.style.display = "none"; }}
              />
            )}
            <div className="phone-results__profile-info">
              <span className="phone-results__profile-name">
                {r.telegram_display_name || "Unknown"}
              </span>
              {r.telegram_username && (
                <a
                  href={`https://t.me/${r.telegram_username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="phone-results__profile-handle"
                >
                  @{r.telegram_username} ↗
                </a>
              )}
              <span className="phone-results__profile-id">ID: {r.telegram_user_id}</span>
            </div>
          </div>
        ) : (
          <p className="phone-results__not-found">
            {r.telegram_registered === false ? "Not registered on Telegram" : "Not checked / unavailable"}
          </p>
        )}
      </div>

      {/* ── WhatsApp block ── */}
      <div className="phone-results__section">
        <span className="phone-results__section-label">WHATSAPP</span>
        {r.whatsapp_registered ? (
          <div className="phone-results__profile-row">
            {r.whatsapp_profile_photo_url && (
              <img
                src={r.whatsapp_profile_photo_url}
                className="phone-results__avatar"
                alt="WhatsApp avatar"
                onError={e => { e.target.style.display = "none"; }}
              />
            )}
            <div className="phone-results__profile-info">
              <span className="phone-results__profile-name">
                {r.whatsapp_display_name || "—"}
              </span>
              {r.whatsapp_about && (
                <span className="phone-results__profile-about">
                  "{r.whatsapp_about}"
                </span>
              )}
            </div>
          </div>
        ) : (
          <p className="phone-results__not-found">
            {r.whatsapp_registered === false ? "Not registered on WhatsApp" : "Not checked / unavailable"}
          </p>
        )}
      </div>

      {/* ── Web mentions block ── */}
      {r.web_mentions && r.web_mentions.length > 0 && (
        <div className="phone-results__section">
          <span className="phone-results__section-label">
            WEB MENTIONS
            <span className="phone-results__mention-count">{r.web_mentions.length}</span>
          </span>
          <div className="phone-results__mentions">
            {r.web_mentions.map((m, i) => (
              <div className="phone-mention" key={i}>
                <a
                  href={m.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="phone-mention__title"
                >
                  {m.title || m.url} ↗
                </a>
                {m.snippet && (
                  <p className="phone-mention__snippet">{m.snippet}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {r.web_mentions && r.web_mentions.length === 0 && (
        <div className="phone-results__section">
          <span className="phone-results__section-label">WEB MENTIONS</span>
          <p className="phone-results__not-found">No public mentions found</p>
        </div>
      )}
    </div>
  );
}

function PhoneField({ label, value, sub, ok }) {
  if (value == null) return null;
  return (
    <div className="phone-field">
      <span className="phone-field__label">{label}</span>
      <span
        className="phone-field__value"
        style={ok != null ? { color: ok ? "#4FFFB0" : "#FF4444" } : undefined}
      >
        {value}
        {sub && <span className="phone-field__sub"> ({sub})</span>}
      </span>
    </div>
  );
}
