"""Clean, lightweight, leak-checked Tempo-styled static exporters for L1, L2, and L3 views.

Zero private JS, zero private CSS leakage, strict CSP on HTML exports, print-ready.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .db import CareerVault

STATIC_CSS = """
:root {
  --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, "Times New Roman", serif;
  --sans: "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, sans-serif;
  --bg: #f6f3ec; --paper: #fffdf9; --ink: #1b221e; --muted: #5c635d;
  --line: #dfd9cb; --line-strong: #c4bba6; --accent: #1d5c48;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: var(--sans); background: var(--bg); color: var(--ink); line-height: 1.62; overflow-x: hidden; overflow-wrap: anywhere; }
main { max-width: 860px; margin: 0 auto; padding: 3rem 1.5rem 4.5rem; }
.hero { margin-bottom: 3rem; }
.badge { display: inline-block; font-size: 0.8rem; font-weight: 500; color: var(--muted); }
.badge.flagship { padding: 0.06rem 0.45rem; border-radius: 6px; background: #dceee5; color: #16543f; font-weight: 600; }
h1 { margin: 0.6rem 0 0.3rem; font-family: var(--serif); font-size: clamp(2rem, 4.2vw, 3rem); font-weight: 600; letter-spacing: -0.025em; line-height: 1.06; }
.headline { margin: 0 0 1.1rem; color: var(--accent); font-size: 1.06rem; font-weight: 600; }
.overview { margin: 0; font-size: 1.08rem; line-height: 1.62; max-width: 62ch; }
h2 { margin: 3rem 0 1rem; font-family: var(--serif); font-size: 1.3rem; font-weight: 600; letter-spacing: -0.015em; }
.card { background: var(--paper); border-radius: 12px; padding: 1.4rem 1.6rem; margin-bottom: 0.75rem; }
.card h3 { margin: 0 0 0.25rem; font-family: var(--serif); font-size: 1.2rem; font-weight: 600; letter-spacing: -0.015em; line-height: 1.3; display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; }
.meta { font-size: 0.86rem; color: var(--muted); margin-bottom: 0.7rem; font-variant-numeric: tabular-nums; }
.card p { margin: 0.55rem 0; font-size: 0.98rem; max-width: 72ch; }
.tags { display: flex; flex-wrap: wrap; gap: 0.2rem 0.9rem; margin-top: 0.9rem; }
.tag { font-size: 0.8rem; color: var(--muted); }
ul { margin: 0.65rem 0; padding: 0; list-style: none; }
li { padding-left: 0.9rem; margin-bottom: 0.5rem; font-size: 0.95rem; border-left: 2px solid var(--line-strong); }
a { color: var(--accent); text-decoration: underline; text-decoration-color: var(--line-strong); text-underline-offset: 3px; font-weight: 600; }
a:hover { text-decoration-color: currentColor; }
.role-row { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; padding: 0.8rem 0; border-top: 1px solid var(--line); }
.role-row:last-child { border-bottom: 1px solid var(--line); }
.role-row strong { font-weight: 600; }
.role-row span { color: var(--muted); font-size: 0.9rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
footer { margin-top: 3rem; padding-top: 1.1rem; border-top: 1px solid var(--line); font-size: 0.82rem; color: var(--muted); }
@media print {
  body { background: #fff; color: #000; }
  .card { break-inside: avoid; padding-inline: 0; }
  .role-row { break-inside: avoid; }
}
"""


def _esc(val: Any) -> str:
    return html.escape(str(val or ""), quote=True)


def render_markdown(snapshot: dict[str, Any]) -> str:
    tier = snapshot["tier"]
    person = snapshot["person"]
    name = person.get("name") or "Career Overview"
    overview = person.get("overview_l1") if tier == "L1" else person.get("overview", "")
    lines = [f"# {name}", ""]
    if person.get("headline"):
        lines += [f"*{person['headline']}*", ""]
    lines += [f"> **Tier:** `{tier}` — {snapshot['privacy_notice']}", ""]
    if overview:
        lines += [overview, ""]

    roles = snapshot.get("roles") or []
    if roles:
        lines += ["## Experience", ""]
        for r in roles:
            org = f" — {r['organization']}" if r.get("organization") else ""
            period = r.get("period_label") or r.get("period") or ""
            lines.append(f"- **{r['title']}{org}** ({period})")
        lines.append("")

    episodes = snapshot.get("episodes") or []
    if episodes:
        lines += ["## Work & Knowledge Highlights", ""]
        for ep in episodes:
            period = ep.get("period_label") or ep.get("period") or ""
            status = ep.get("status", "")
            lines.append(f"### {ep['title']}")
            lines.append(f"*{period} · {status}*")
            lines.append("")
            summary = ep.get("summary_l1") if tier == "L1" else ep.get("summary", "")
            if summary:
                lines += [summary, ""]
            decisions = ep.get("decisions") or []
            if decisions:
                lines.append("**Key decisions:**")
                for d in decisions:
                    lines.append(f"- {d}")
                lines.append("")
            outcome = ep.get("outcome_l1") if tier == "L1" else ep.get("outcome", "")
            if outcome:
                lines += [f"**Impact & scope:** {outcome}", ""]
            credit = ep.get("shared_credit_l1") if tier == "L1" else ep.get("shared_credit", "")
            if credit:
                lines += [f"**Collaboration:** {credit}", ""]
            links = ep.get("public_links") or []
            if links:
                lines.append("**Public links:** " + " · ".join(f"[{l['label']}]({l['url']})" for l in links))
                lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_resume_markdown(snapshot: dict[str, Any]) -> str:
    """High-signal resume view derived directly from L2 or L3 (no raw confidential leaks)."""
    person = snapshot["person"]
    tier = snapshot["tier"]
    overview = person.get("overview_l1") if tier == "L1" else person.get("overview", "")
    lines = [f"# {person.get('name', '')}", f"**{person.get('headline', '')}**", ""]
    if overview:
        lines += [overview, ""]
    lines += ["## Experience", ""]
    for r in snapshot.get("roles", []):
        org = f", {r['organization']}" if r.get("organization") else ""
        period = r.get("period_label") or r.get("period") or ""
        lines.append(f"### {r['title']}{org} ({period})")
        lines.append("")
    lines += ["## Selected Work", ""]
    for ep in snapshot.get("episodes", []):
        summary = ep.get("summary_l1") if tier == "L1" else ep.get("summary", "")
        outcome = ep.get("outcome_l1") if tier == "L1" else ep.get("outcome", "")
        lines.append(f"- **{ep['title']}** ({ep.get('period_label') or ep.get('period') or ''}): {summary}")
        if outcome:
            lines.append(f"  - *Impact:* {outcome}")
    return "\n".join(lines).strip() + "\n"


def render_static_html(snapshot: dict[str, Any]) -> str:
    tier = snapshot["tier"]
    person = snapshot["person"]
    name = person.get("name") or "Career Overview"
    overview = person.get("overview_l1") if tier == "L1" else person.get("overview", "")

    role_blocks = []
    for r in snapshot.get("roles", []):
        org = f" · {_esc(r['organization'])}" if r.get("organization") else ""
        period = _esc(r.get("period_label") or r.get("period") or "")
        role_blocks.append(
            f'<div class="role-row"><strong>{_esc(r["title"])}{org}</strong><span class="meta" style="margin:0">{period}</span></div>'
        )
    roles_html = (
        f'<section><h2>Experience</h2><div class="roles">{"".join(role_blocks)}</div></section>'
        if role_blocks else ""
    )

    def render_ep_card(ep: dict[str, Any]) -> str:
        period = _esc(ep.get("period_label") or ep.get("period") or "")
        status = _esc(ep.get("status") or "")
        imp = int(ep.get("importance") or 0)
        imp_badge = '<span class="badge flagship">Flagship</span>' if imp >= 3 else ""
        summary = _esc(ep.get("summary_l1") if tier == "L1" else ep.get("summary", ""))
        outcome = _esc(ep.get("outcome_l1") if tier == "L1" else ep.get("outcome", ""))
        credit = _esc(ep.get("shared_credit_l1") if tier == "L1" else ep.get("shared_credit", ""))
        decisions = ep.get("decisions") or []
        dec_html = (
            "<ul>" + "".join(f"<li>{_esc(d)}</li>" for d in decisions) + "</ul>"
            if decisions else ""
        )
        links = ep.get("public_links") or []
        links_html = (
            "<p>" + " · ".join(
                f'<a href="{_esc(l["url"])}" rel="noopener noreferrer">{_esc(l["label"])}</a>'
                for l in links if str(l.get("url", "")).startswith("https://")
            ) + "</p>"
            if links else ""
        )
        tags = ep.get("tags") or []
        tags_html = (
            '<div class="tags">' + "".join(f'<span class="tag">{_esc(t)}</span>' for t in tags) + "</div>"
            if tags else ""
        )
        arts = [a for a in (ep.get("artifacts") or []) if a.get("data_url")]
        arts_html = (
            '<div style="display:grid;gap:0.85rem;margin:0.9rem 0">' + "".join(
                f'<figure style="margin:0"><img src="{_esc(a["data_url"])}" alt="{_esc(a.get("title") or a.get("caption") or "Work artifact")}" style="max-width:100%;border-radius:10px;border:1px solid var(--line)">'
                f'<figcaption class="meta" style="margin-top:0.35rem">{_esc(a.get("title") or "")}{" — " + _esc(a["caption"]) if a.get("caption") else ""}</figcaption></figure>'
                for a in arts
            ) + "</div>"
            if arts else ""
        )
        outcome_html = f"<p><strong>Impact &amp; scope:</strong> {outcome}</p>" if outcome else ""
        credit_html = f"<p><strong>Collaboration:</strong> {credit}</p>" if credit else ""
        return (
            f'<article class="card"><h3>{_esc(ep["title"])}{imp_badge}</h3>'
            f'<div class="meta">{period} · {status}</div>'
            f"<p>{summary}</p>{dec_html}{arts_html}{outcome_html}{credit_html}{links_html}{tags_html}</article>"
        )

    all_eps = snapshot.get("episodes", [])
    flagships = [e for e in all_eps if int(e.get("importance") or 0) >= 3]
    supporting = [e for e in all_eps if int(e.get("importance") or 0) == 2]
    others = [e for e in all_eps if int(e.get("importance") or 0) < 2]

    sections_html = []
    if flagships:
        sections_html.append(f'<section><h2>Flagship Stories</h2>{"".join(render_ep_card(e) for e in flagships)}</section>')
    if supporting:
        sections_html.append(f'<section><h2>Core Delivery &amp; Leadership</h2>{"".join(render_ep_card(e) for e in supporting)}</section>')
    if others:
        heading = "Experiments, Prototypes &amp; Context" if (flagships or supporting) else "Selected Work"
        sections_html.append(f'<section><h2>{heading}</h2>{"".join(render_ep_card(e) for e in others)}</section>')
    episodes_html = "".join(sections_html) or '<section><p class="meta">No episodes projected for this tier yet.</p></section>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>{_esc(name)} — Career Overview ({_esc(tier)})</title>
<style>{STATIC_CSS}</style>
</head>
<body>
<main>
  <header class="hero">
    <span class="badge">{_esc(tier)} · {_esc(snapshot['schema'])}</span>
    <h1>{_esc(name)}</h1>
    <p class="headline">{_esc(person.get('headline', ''))}</p>
    <p class="overview">{_esc(overview)}</p>
  </header>
  {roles_html}
  {episodes_html}
  <footer>{_esc(snapshot['privacy_notice'])} · Generated {_esc(snapshot['generated_at'])}</footer>
</main>
</body>
</html>
"""


def render_agent_pack_markdown(snapshot: dict[str, Any], knowledge: dict[str, Any] | None = None) -> str:
    """Exhaustive, leak-checked Markdown context pack built for someone else's AI agent to read."""
    person = snapshot["person"]
    tier = snapshot["tier"]
    all_eps = snapshot.get("episodes", [])
    roles = snapshot.get("roles", [])
    lines = [
        f"# Career Context Pack ({tier} · Exhaustive AI-Reader Format)",
        "",
        "## Instructions for Receiving AI Agents",
        "- This document is a verified, leak-checked career context export prepared by the candidate.",
        "- Read all sections before answering questions—depth is intentional so you do not have to guess.",
        "- Keep scope and shared credit exact: distinguish what the person led, co-built, proposed, piloted, or shipped.",
        "- Do not extrapolate confidential names, exact internal revenue, or metrics that are not stated here.",
        f"- Privacy tier: `{tier}` — {snapshot['privacy_notice']}",
        "",
        "---",
        "",
        f"## Profile: {person.get('name') or 'Candidate'}",
    ]
    if person.get("headline"):
        lines.append(f"**Headline:** {person['headline']}")
    if person.get("overview"):
        lines.extend(["", person["overview"]])

    if roles:
        lines.extend(["", "## Chronological Roles & Experience"])
        for r in roles:
            org = f" @ {r['organization']}" if r.get("organization") else ""
            period = f" ({r['period']})" if r.get("period") else ""
            curr = " [Current]" if r.get("is_current") else ""
            lines.append(f"- **{r['title']}**{org}{period}{curr}")

    if knowledge:
        caps = knowledge.get("capabilities") or []
        themes = knowledge.get("themes") or []
        if caps:
            lines.extend(["", "## Capabilities & Tools"])
            lines.append(", ".join(f"{c['name']} ({len(c.get('episodes', []))})" for c in caps[:40]))
        if themes:
            lines.extend(["", "## Recurring Themes"])
            lines.append(", ".join(f"{t['tag']} ({t['count']})" for t in themes[:30]))

    groups = [
        ("Flagship Work (Highest Prominence)", [e for e in all_eps if int(e.get("importance") or 0) >= 3]),
        ("Core Delivery & Operations", [e for e in all_eps if int(e.get("importance") or 0) == 2]),
        ("Additional Projects, Prototypes & Proof Points", [e for e in all_eps if int(e.get("importance") or 0) < 2]),
    ]
    for heading, eps in groups:
        if not eps:
            continue
        lines.extend(["", f"## {heading}"])
        for ep in eps:
            meta = " · ".join(x for x in [ep.get("period"), ep.get("status")] if x)
            lines.extend(["", f"### {ep['title']}"])
            if meta:
                lines.append(f"*{meta}*")
            if ep.get("summary"):
                lines.extend(["", ep["summary"]])
            if ep.get("decisions"):
                lines.extend(["", "**Key Decisions & Trade-offs:**"])
                for d in ep["decisions"]:
                    lines.append(f"- {d}")
            if ep.get("outcome"):
                lines.append(f"\n**Outcome / Scope:** {ep['outcome']}")
            if ep.get("shared_credit"):
                lines.append(f"\n**Collaboration / Shared Credit:** {ep['shared_credit']}")
            if ep.get("tags"):
                lines.append(f"\n**Tags:** {', '.join(ep['tags'])}")
            links = [l for l in (ep.get("public_links") or []) if str(l.get("url", "")).startswith("https://")]
            if links:
                lines.append("\n**Public Links:** " + " · ".join(f"[{l['label']}]({l['url']})" for l in links))

    lines.extend([
        "",
        "---",
        f"*Generated {snapshot['generated_at']} · Tier {tier} · {len(all_eps)} leak-checked stories · Raw L0 vault excluded.*",
    ])
    return "\n".join(lines).strip() + "\n"


def export_vault(
    vault: CareerVault,
    *,
    tier: str = "L2",
    fmt: str = "html",
    out_path: str | Path | None = None,
    episode_ids: list[str] | None = None,
    approved_only: bool = False,
    strict_leaks: bool = True,
) -> dict[str, Any]:
    fmt = fmt.lower().strip()
    snapshot = vault.build_tier_snapshot(
        tier=tier,
        episode_ids=episode_ids,
        approved_only=approved_only,
        strict_leaks=strict_leaks,
        embed_artifacts=(fmt == "html"),
    )
    if fmt == "json":
        content = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    elif fmt == "agent_json":
        kg = vault.get_knowledge_graph()
        # Only include safe aggregated tags/capabilities (never raw L1 decisions which may contain unredacted terms)
        safe_caps = [{"name": c["name"], "kind": c.get("kind", ""), "story_count": len(c.get("episodes", []))} for c in kg.get("capabilities", [])]
        safe_themes = [t for t in kg.get("themes", []) if "confidential" not in str(t.get("tag", ""))]
        pack = {
            **snapshot,
            "export_mode": "exhaustive_agent_pack",
            "ai_reader_instructions": (
                "Leak-checked exhaustive career context pack. Preserve exact scope, shared credit, "
                "and honest stopping points; do not infer redacted client names or internal metrics."
            ),
            "capabilities": safe_caps,
            "themes": safe_themes,
        }
        # Re-verify entire JSON payload is leak-free on L2/L3
        if tier in ("L2", "L3") and strict_leaks:
            leaks = vault.scan_leaks(json.dumps(pack, ensure_ascii=False))
            if leaks:
                matched = sorted({f["matched"] for f in leaks})
                raise ValueError(f"Blocked {tier} agent_json export: contains sensitive terms: {matched}")
        content = json.dumps(pack, indent=2, ensure_ascii=False) + "\n"
    elif fmt == "agent_pack":
        kg = vault.get_knowledge_graph()
        safe_kg = {
            "capabilities": kg.get("capabilities", []),
            "themes": [t for t in kg.get("themes", []) if "confidential" not in str(t.get("tag", ""))],
        }
        content = render_agent_pack_markdown(snapshot, safe_kg)
        if tier in ("L2", "L3") and strict_leaks:
            leaks = vault.scan_leaks(content)
            if leaks:
                matched = sorted({f["matched"] for f in leaks})
                raise ValueError(f"Blocked {tier} agent_pack export: contains sensitive terms: {matched}")
    elif fmt == "markdown" or fmt == "md":
        content = render_markdown(snapshot)
    elif fmt == "resume":
        content = render_resume_markdown(snapshot)
    elif fmt == "html":
        content = render_static_html(snapshot)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")

    result: dict[str, Any] = {
        "tier": tier,
        "format": fmt,
        "episodes": len(snapshot.get("episodes", [])),
        "bytes": len(content.encode("utf-8")),
        "leak_checked": snapshot.get("leak_checked", False),
    }
    if out_path:
        dest = Path(out_path).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        result["path"] = str(dest)
    else:
        result["content"] = content
    return result
