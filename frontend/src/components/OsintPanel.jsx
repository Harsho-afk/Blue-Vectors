import { useState, useEffect, useCallback } from "react";
import { API } from "../lib/api";
import MaigretResults from "./MaigretResults";
import BreachResults from "./BreachResults";
import PhoneResults from "./PhoneResults";

export default function OsintPanel({ caseId, identifiers, onAccountImported }) {
  const [lookups, setLookups] = useState([]);
  const [searchingUsername, setSearchingUsername] = useState(null);
  const [searchingEmail, setSearchingEmail] = useState(null);
  const [searchingPhone, setSearchingPhone] = useState(null);
  const [error, setError] = useState(null);

  const fetchLookups = useCallback(() => {
    fetch(`${API}/api/cases/${caseId}/osint`, { credentials: "include" })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => setLookups(data.lookups || []))
      .catch(e => setError(e.message));
  }, [caseId]);

  useEffect(() => { fetchLookups(); }, [fetchLookups]);

  const handleUsernameSearch = async (value) => {
    setSearchingUsername(value);
    setError(null);
    try {
      const res = await fetch(`${API}/api/cases/${caseId}/osint/username-search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: value }),
      });
      if (!res.ok) {
        const detail = await res.json().then(d => d.detail).catch(() => res.statusText);
        throw new Error(detail);
      }
      fetchLookups();
    } catch (e) {
      setError(e.message);
    } finally {
      setSearchingUsername(null);
    }
  };

  const handleBreachLookup = async (value) => {
    setSearchingEmail(value);
    setError(null);
    try {
      const res = await fetch(`${API}/api/cases/${caseId}/osint/breach-lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: value }),
      });
      if (!res.ok) {
        const detail = await res.json().then(d => d.detail).catch(() => res.statusText);
        throw new Error(detail);
      }
      fetchLookups();
    } catch (e) {
      setError(e.message);
    } finally {
      setSearchingEmail(null);
    }
  };

  const handlePhoneLookup = async (value) => {
    setSearchingPhone(value);
    setError(null);
    try {
      const res = await fetch(`${API}/api/cases/${caseId}/osint/phone-lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ phone: value }),
      });
      if (!res.ok) {
        const detail = await res.json().then(d => d.detail).catch(() => res.statusText);
        throw new Error(detail);
      }
      fetchLookups();
    } catch (e) {
      setError(e.message);
    } finally {
      setSearchingPhone(null);
    }
  };

  const usernameIdents = identifiers.filter(i => i.identifier_type === "username");
  const emailIdents    = identifiers.filter(i => i.identifier_type === "email");
  const phoneIdents    = identifiers.filter(i => i.identifier_type === "phone");

  return (
    <div className="osint-panel">
      <div className="osint-panel__header">
        <span className="osint-panel__title">OSINT DISCOVERY</span>
        <span className="osint-panel__count">
          {lookups.length} lookup{lookups.length !== 1 ? "s" : ""} completed
        </span>
      </div>

      {error && (
        <div className="aria-auth-error" style={{ marginBottom: 12, fontSize: 11 }}>
          {error}
        </div>
      )}

      {(usernameIdents.length > 0 || emailIdents.length > 0 || phoneIdents.length > 0) && (
        <div className="osint-panel__actions">
          {usernameIdents.map(ident => (
            <div key={ident.id} className="osint-action-row">
              <span className="osint-action-row__label">
                <span className="osint-action-row__type">USERNAME</span>
                <span className="osint-action-row__value">{ident.value}</span>
              </span>
              <button
                className="osint-action-btn"
                disabled={searchingUsername === ident.value}
                onClick={() => handleUsernameSearch(ident.value)}
              >
                {searchingUsername === ident.value ? "SEARCHING..." : "SEARCH PLATFORMS ▶"}
              </button>
            </div>
          ))}
          {emailIdents.map(ident => (
            <div key={ident.id} className="osint-action-row">
              <span className="osint-action-row__label">
                <span className="osint-action-row__type">EMAIL</span>
                <span className="osint-action-row__value">{ident.value}</span>
              </span>
              <button
                className="osint-action-btn"
                disabled={searchingEmail === ident.value}
                onClick={() => handleBreachLookup(ident.value)}
              >
                {searchingEmail === ident.value ? "CHECKING..." : "CHECK BREACHES ▶"}
              </button>
            </div>
          ))}
          {phoneIdents.map(ident => (
            <div key={ident.id} className="osint-action-row">
              <span className="osint-action-row__label">
                <span className="osint-action-row__type">PHONE</span>
                <span className="osint-action-row__value">{ident.value}</span>
              </span>
              <button
                className="osint-action-btn"
                disabled={searchingPhone === ident.value}
                onClick={() => handlePhoneLookup(ident.value)}
              >
                {searchingPhone === ident.value ? "LOOKING UP..." : "LOOKUP PHONE ▶"}
              </button>
            </div>
          ))}
        </div>
      )}

      {lookups.length === 0 && !error && (
        <p className="no-records" style={{ marginTop: 12 }}>No lookups yet</p>
      )}

      {lookups.map(lookup =>
        lookup.lookup_type === "maigret" ? (
          <MaigretResults
            key={lookup.id}
            lookup={lookup}
            caseId={caseId}
            onAccountImported={() => { fetchLookups(); onAccountImported?.(); }}
          />
        ) : (lookup.lookup_type === "xposedornot" || lookup.lookup_type === "hibp") ? (
          <BreachResults key={lookup.id} lookup={lookup} />
        ) : lookup.lookup_type === "phone" ? (
          <PhoneResults key={lookup.id} lookup={lookup} />
        ) : null
      )}
    </div>
  );
}
