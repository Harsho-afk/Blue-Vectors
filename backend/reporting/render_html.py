"""
Render a report JSON snapshot into a self-contained HTML preview.
All user-supplied content is escaped to prevent XSS.
"""

import html
from datetime import datetime


def render_report_html(report: dict) -> str:
    """Render report_json into a complete HTML document string."""
    meta = report.get("report_metadata", {})
    scope = report.get("scope_and_methodology", {})
    summary = report.get("executive_summary", {})
    accounts_section = report.get("identified_accounts", {})
    correlations = report.get("correlation_findings", [])
    sources = report.get("open_source_references", [])
    insights = report.get("analytical_insights", {})
    limitations = report.get("limitations", [])
    confidence = report.get("confidence_notes", {})
    intelligence = report.get("intelligence_briefing")
    appendix = report.get("appendix", {})

    parts = [_html_head(meta)]
    parts.append(_section_metadata(meta))
    parts.append(_section_scope(scope))
    parts.append(_section_summary(summary))
    parts.append(_section_accounts(accounts_section))
    parts.append(_section_correlations(correlations))
    parts.append(_section_sources(sources))
    parts.append(_section_insights(insights))
    parts.append(_section_limitations(limitations))
    parts.append(_section_confidence(confidence))
    if intelligence:
        parts.append(_section_intelligence(intelligence))
    parts.append(_section_appendix(appendix))
    parts.append(_html_footer())

    return "\n".join(parts)


def _e(text) -> str:
    """Escape HTML entities."""
    if text is None:
        return ""
    return html.escape(str(text))


def _html_head(meta: dict) -> str:
    title = _e(meta.get("case_title", "SOCMINT Report"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ARIA Report — {title}</title>
<style>
:root {{
  --bg: #ffffff; --fg: #1a1a2e; --muted: #6b7280;
  --accent: #3b82f6; --border: #e5e7eb;
  --card-bg: #f9fafb; --high: #16a34a; --medium: #d97706; --low: #6b7280;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0f172a; --fg: #e2e8f0; --muted: #94a3b8;
    --accent: #60a5fa; --border: #334155;
    --card-bg: #1e293b; --high: #4ade80; --medium: #fbbf24; --low: #94a3b8;
  }}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, sans-serif; background: var(--bg);
  color: var(--fg); line-height: 1.6; padding: 2rem; max-width: 1000px; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
h2 {{ font-size: 1.2rem; margin: 2rem 0 0.75rem; padding-bottom: 0.25rem;
  border-bottom: 2px solid var(--accent); }}
h3 {{ font-size: 1rem; margin: 1rem 0 0.5rem; }}
table {{ width: 100%; border-collapse: collapse; margin: 0.5rem 0; font-size: 0.875rem; }}
th, td {{ padding: 0.5rem 0.75rem; text-align: left; border: 1px solid var(--border); }}
th {{ background: var(--card-bg); font-weight: 600; }}
.card {{ background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 0.5rem; padding: 1rem; margin: 0.5rem 0; }}
.badge {{ display: inline-block; padding: 0.125rem 0.5rem; border-radius: 0.25rem;
  font-size: 0.75rem; font-weight: 600; }}
.badge-high {{ background: var(--high); color: white; }}
.badge-medium {{ background: var(--medium); color: white; }}
.badge-low {{ background: var(--low); color: white; }}
.muted {{ color: var(--muted); font-size: 0.85rem; }}
.disclaimer {{ background: var(--card-bg); border-left: 4px solid var(--medium);
  padding: 0.75rem 1rem; margin: 1rem 0; font-size: 0.85rem; }}
ul {{ padding-left: 1.5rem; margin: 0.5rem 0; }}
li {{ margin: 0.25rem 0; }}
.overflow-x {{ overflow-x: auto; }}
@media print {{
  body {{ padding: 1rem; font-size: 11pt; }}
  h2 {{ page-break-before: auto; }}
  .card {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<h1>ARIA SOCMINT Investigation Report</h1>
<p class="muted">Case: {title} | Generated: {_e(meta.get('generated_at', ''))}</p>
"""


def _section_metadata(meta: dict) -> str:
    return f"""
<h2>Report Metadata</h2>
<div class="card">
<table>
<tr><th>Case ID</th><td>{_e(meta.get('case_id'))}</td></tr>
<tr><th>Title</th><td>{_e(meta.get('case_title'))}</td></tr>
<tr><th>Status</th><td>{_e(meta.get('case_status'))}</td></tr>
<tr><th>Investigator</th><td>{_e(meta.get('investigator'))}</td></tr>
<tr><th>Generated</th><td>{_e(meta.get('generated_at'))}</td></tr>
<tr><th>Methodology</th><td>v{_e(meta.get('methodology_version'))}</td></tr>
</table>
</div>"""


def _section_scope(scope: dict) -> str:
    seeds_html = ""
    for s in scope.get("seed_identifiers", []):
        seeds_html += f"<li><strong>{_e(s['type'])}</strong>: {_e(s['value'])}"
        if s.get("platform_hint"):
            seeds_html += f" ({_e(s['platform_hint'])})"
        seeds_html += "</li>"

    methods = ", ".join(_e(m) for m in scope.get("collection_methods", []))
    platforms = ", ".join(_e(p) for p in scope.get("platforms_collected", []))
    window = scope.get("collection_window")
    window_str = ""
    if window:
        window_str = f"<p class='muted'>Collection window: {_e(window['earliest'])} — {_e(window['latest'])}</p>"

    return f"""
<h2>Scope &amp; Methodology</h2>
<h3>Seed Identifiers</h3>
<ul>{seeds_html}</ul>
<p><strong>Methods:</strong> {methods or 'None'}</p>
<p><strong>Platforms:</strong> {platforms or 'None'}</p>
{window_str}
<div class="disclaimer">{_e(scope.get('public_source_statement', ''))}</div>"""


def _section_summary(summary: dict) -> str:
    bands = summary.get("correlation_bands", {})
    cats = summary.get("insight_categories", {})
    cat_rows = "".join(f"<li>{_e(k)}: {v}</li>" for k, v in cats.items())

    return f"""
<h2>Executive Summary</h2>
<div class="card">
<table>
<tr><th>Accounts collected</th><td>{summary.get('total_accounts_collected', 0)}</td>
<th>Platforms</th><td>{summary.get('total_platforms', 0)}</td></tr>
<tr><th>Correlations</th><td>{summary.get('total_correlations', 0)}</td>
<th>Sources</th><td>{summary.get('total_sources', 0)}</td></tr>
<tr><th>High-confidence</th><td>{bands.get('High', 0)}</td>
<th>Medium</th><td>{bands.get('Medium', 0)}</td></tr>
<tr><th>Low-confidence</th><td>{bands.get('Low', 0)}</td>
<th>Insights</th><td>{summary.get('total_insights', 0)}</td></tr>
</table>
</div>
<h3>Insights by Category</h3>
<ul>{cat_rows}</ul>"""


def _section_accounts(section: dict) -> str:
    collected = section.get("collected_accounts", [])
    leads = section.get("discovered_leads", [])

    rows = ""
    for a in collected:
        rows += f"""<tr>
<td>{_e(a.get('reference_id'))}</td>
<td>{_e(a.get('platform'))}</td>
<td>{_e(a.get('username'))}</td>
<td>{_e(a.get('display_name'))}</td>
<td>{a.get('post_count', 0)}</td>
<td>{_e(a.get('collection_status'))}</td>
</tr>"""

    lead_rows = ""
    for d in leads[:20]:
        url = d.get("url") or ""
        safe_url = _e(url)
        lead_rows += f"""<tr>
<td>{_e(d.get('platform'))}</td>
<td>{_e(d.get('username'))}</td>
<td><a href="{safe_url}" rel="noopener">{safe_url[:60]}</a></td>
<td>{_e(d.get('source_lookup'))}</td>
</tr>"""

    return f"""
<h2>Identified Accounts</h2>
<h3>Collected Accounts ({section.get('total_collected', 0)})</h3>
<div class="overflow-x">
<table>
<tr><th>Ref</th><th>Platform</th><th>Username</th><th>Display Name</th><th>Posts</th><th>Status</th></tr>
{rows}
</table>
</div>
<h3>Discovered Leads ({section.get('total_leads', 0)})</h3>
<div class="overflow-x">
<table>
<tr><th>Platform</th><th>Username</th><th>URL</th><th>Source</th></tr>
{lead_rows}
</table>
</div>"""


def _section_correlations(correlations: list) -> str:
    rows = ""
    for c in correlations:
        a = c.get("account_a", {})
        b = c.get("account_b", {})
        band = c.get("band", "Low")
        badge_cls = f"badge-{band.lower()}"

        rows += f"""<div class="card">
<p><strong>{_e(c.get('reference_id'))}</strong>:
{_e(a.get('platform'))}/{_e(a.get('username'))} ({_e(a.get('ref'))})
↔ {_e(b.get('platform'))}/{_e(b.get('username'))} ({_e(b.get('ref'))})</p>
<p><span class="badge {badge_cls}">{_e(band)}</span>
 Confidence: {c.get('confidence_pct', 0):.1f}% |
 Evidence: {_e(c.get('evidence_type'))}</p>
<p class="muted">{_e(c.get('conclusion'))}</p>
</div>"""

    return f"""
<h2>Correlation Findings</h2>
{rows if rows else '<p class="muted">No correlations available.</p>'}"""


def _section_sources(sources: list) -> str:
    rows = ""
    for s in sources[:40]:
        url = s.get("url", "")
        safe_url = _e(url)
        rows += f"""<tr>
<td>{_e(s.get('reference_id'))}</td>
<td>{_e(s.get('source_type'))}</td>
<td><a href="{safe_url}" rel="noopener">{_e(s.get('title', ''))}</a></td>
<td class="muted">{_e(s.get('retrieved_at', ''))}</td>
</tr>"""

    return f"""
<h2>Open-Source References</h2>
<div class="overflow-x">
<table>
<tr><th>Ref</th><th>Type</th><th>Source</th><th>Retrieved</th></tr>
{rows}
</table>
</div>"""


def _section_insights(insights_by_cat: dict) -> str:
    parts = ["<h2>Analytical Insights</h2>"]
    for category, items in insights_by_cat.items():
        parts.append(f"<h3>{_e(category.replace('_', ' ').title())}</h3>")
        for item in items:
            conf = item.get("confidence", "low")
            badge_cls = f"badge-{conf}"
            parts.append(f"""<div class="card">
<p><strong>{_e(item.get('reference_id'))}</strong>
<span class="badge {badge_cls}">{_e(conf)}</span></p>
<p>{_e(item.get('claim'))}</p>
<p class="muted">{_e(item.get('evidence_summary') or '')}</p>
</div>""")
    return "\n".join(parts)


def _section_limitations(limitations: list) -> str:
    items = "".join(f"<li>{_e(l)}</li>" for l in limitations)
    return f"""
<h2>Limitations</h2>
<ul>{items}</ul>"""


def _section_confidence(confidence: dict) -> str:
    bands = confidence.get("band_definitions", {})
    band_rows = "".join(
        f"<tr><td><span class='badge badge-{_e(k.lower())}'>{_e(k)}</span></td>"
        f"<td>{_e(v)}</td></tr>"
        for k, v in bands.items()
    )

    return f"""
<h2>Confidence Framework</h2>
<table>
<tr><th>Band</th><th>Meaning</th></tr>
{band_rows}
</table>
<div class="disclaimer">{_e(confidence.get('disclaimer', ''))}</div>"""


def _section_intelligence(intelligence: dict) -> str:
    return f"""
<h2>Intelligence Briefing (AI-Assisted)</h2>
<div class="disclaimer">{_e(intelligence.get('disclaimer', ''))}</div>
<div class="card">
<p>{_e(intelligence.get('narrative', 'No briefing available.'))}</p>
</div>
<p class="muted">Label: {_e(intelligence.get('label'))} |
Generated: {_e(intelligence.get('generated_at'))}</p>"""


def _section_appendix(appendix: dict) -> str:
    seeds = appendix.get("seeds", [])
    seed_items = "".join(
        f"<li>{_e(s['type'])}: {_e(s['value'])}</li>" for s in seeds
    )
    lookups = appendix.get("lookup_summary", [])
    lookup_rows = ""
    for lk in lookups:
        lookup_rows += f"""<tr>
<td>{_e(lk.get('ref'))}</td>
<td>{_e(lk.get('type'))}</td>
<td>{_e(lk.get('input'))}</td>
<td class="muted">{_e(lk.get('performed_at'))}</td>
</tr>"""

    gen = appendix.get("generation_metadata", {})
    return f"""
<h2>Appendix</h2>
<h3>Seed Identifiers</h3>
<ul>{seed_items}</ul>
<h3>Lookup Summary</h3>
<div class="overflow-x">
<table>
<tr><th>Ref</th><th>Type</th><th>Input</th><th>Performed</th></tr>
{lookup_rows}
</table>
</div>
<h3>Generation Metadata</h3>
<p class="muted">Schema: v{_e(gen.get('report_schema_version'))} |
Methodology: v{_e(gen.get('methodology_version'))} |
Generated: {_e(gen.get('generated_at'))}</p>"""


def _html_footer() -> str:
    return """
<hr style="margin-top:2rem; border-color: var(--border);">
<p class="muted" style="margin-top:1rem; text-align:center;">
Generated by ARIA — Social Media Intelligence &amp; OSINT-Based Suspect Profiling System<br>
This report contains analytical assessments of publicly available information only.
</p>
</body>
</html>"""
