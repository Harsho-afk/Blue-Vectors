import { useState } from "react";
import MaigretPlatformRow from "./MaigretPlatformRow";

const CATEGORY_ORDER = [
  "social_media", "developer", "gaming", "streaming",
  "professional", "creative", "messaging", "shopping", "other",
];

const CATEGORY_DISPLAY = {
  social_media: "Social Media",
  developer: "Developer & Tech",
  gaming: "Gaming",
  streaming: "Streaming & Media",
  professional: "Professional",
  creative: "Creative & Art",
  messaging: "Messaging",
  shopping: "Shopping & Finance",
  other: "Other Platforms",
};

const CATEGORY_ICONS = {
  social_media: "◉",
  developer: "⟨/⟩",
  gaming: "◆",
  streaming: "▶",
  professional: "◈",
  creative: "✦",
  messaging: "◇",
  shopping: "▣",
  other: "○",
};

export default function MaigretResults({ lookup, caseId, onAccountImported }) {
  const [expandedCategories, setExpandedCategories] = useState(new Set());

  const result = lookup.result || {};
  const categories = result.categories || {};
  const linkedAccounts = result.linked_accounts || [];

  const nonEmptyCategories = CATEGORY_ORDER.filter(
    k => categories[k] && categories[k].length > 0
  );

  const toggleCategory = (key) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="maigret-results">
      <div className="maigret-results__summary">
        <span className="maigret-results__username">
          Search: {result.username || lookup.input_value}
        </span>
        <span className="maigret-results__stats">
          {result.total_found || 0} accounts found across {nonEmptyCategories.length} categor{nonEmptyCategories.length !== 1 ? "ies" : "y"}
        </span>
      </div>

      {result.error && (
        <div style={{ padding: "10px 16px", fontSize: 11, color: "#F6C90E" }}>
          {result.error}
        </div>
      )}

      {CATEGORY_ORDER.map(categoryKey => {
        const platforms = categories[categoryKey];
        if (!platforms || platforms.length === 0) return null;

        const isExpanded = expandedCategories.has(categoryKey);

        return (
          <div className="maigret-category" key={categoryKey}>
            <div
              className="maigret-category__header"
              onClick={() => toggleCategory(categoryKey)}
            >
              <span className="maigret-category__icon">
                {CATEGORY_ICONS[categoryKey] || "○"}
              </span>
              <span className="maigret-category__name">
                {CATEGORY_DISPLAY[categoryKey] || categoryKey}
              </span>
              <span className="maigret-category__count">{platforms.length}</span>
              <span className="maigret-category__chevron">
                {isExpanded ? "▼" : "▶"}
              </span>
            </div>

            {isExpanded && (
              <div className="maigret-category__list">
                {platforms.map(platform => (
                  <MaigretPlatformRow
                    key={platform.platform}
                    platform={platform}
                    caseId={caseId}
                    searchedUsername={result.username || lookup.input_value}
                    onImported={onAccountImported}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}

      {linkedAccounts.length > 0 && (
        <div className="maigret-linked">
          <div className="maigret-linked__header">
            <span className="maigret-linked__title">DISCOVERED LINKED ACCOUNTS</span>
            <span className="maigret-linked__count">{linkedAccounts.length}</span>
          </div>
          {linkedAccounts.map((linked, i) => (
            <div className="maigret-linked__item" key={linked.username || i}>
              <span className="maigret-linked__username">{linked.username}</span>
              <span className="maigret-linked__source">
                Found in {linked.source_platform} profile of {result.username}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
