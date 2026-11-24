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
  --sans: "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, sans-serif;
  --bg: #f7f8fc; --paper: #ffffff; --ink: #182643; --muted: #53637a;
  --line: #dce1ed; --wash: #eeedfc; --accent: #5141bd; --raised: 0 3px 0 #dce0ed;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: var(--sans); background: var(--bg); color: var(--ink); line-height: 1.62; overflow-x: hidden; overflow-wrap: anywhere; }
main { max-width: 900px; margin: 0 auto; padding: 2.5rem 1.5rem 4.5rem; }
.hero {
  position: relative; overflow: hidden; border-radius: 18px; border: 1px solid #d3d5ed;
  box-shadow: 0 3px 0 #dfe1ee; padding: 2rem 2.2rem; margin-bottom: 2.2rem;
  background: radial-gradient(ellipse at 100% 15%, #dbd8ff, transparent 68%), linear-gradient(115deg, #f3f1ff, #eae7ff);
  box-shadow: inset 6px 0 #6c58cd, 0 3px 0 #dfe1ee;
}
.hero::before {
  content: ""; position: absolute; right: 0; top: 0; width: 28px; height: 28px;
  background: linear-gradient(45deg, #c3b8ff 8%, #9887e2 49%, var(--bg) 51%);
  border-bottom-left-radius: 5px; box-shadow: -2px 2px 4px #57479825;
}
.badge { display: inline-block; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.03em; padding: 0.22rem 0.65rem; border-radius: 999px; background: #fff; border: 1px solid #c9c3ee; color: var(--accent); text-transform: uppercase; }
.badge.flagship { background: #d8f6e9; border-color: #9edec4; color: #105947; }
h1 { margin: 0.7rem 0 0.25rem; font-size: clamp(1.8rem, 3.2vw, 2.5rem); font-weight: 700; letter-spacing: -0.045em; line-height: 1.12; color: #1d1b3f; }
.headline { margin: 0 0 1rem; color: #474178; font-size: 1.05rem; font-weight: 600; letter-spacing: -0.015em; }
.overview { margin: 0; font-size: 1.05rem; line-height: 1.58; color: #262449; max-width: 66ch; }
h2 { margin: 2.2rem 0 0.9rem; font-size: 1.25rem; font-weight: 700; letter-spacing: -0.03em; color: var(--ink); }
.card { background: var(--paper); border: 1px solid var(--line); border-radius: 15px; padding: 1.35rem 1.55rem; margin-bottom: 1rem; box-shadow: var(--raised); }
.card h3 { margin: 0 0 0.25rem; font-size: 1.16rem; font-weight: 680; letter-spacing: -0.025em; line-height: 1.3; display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; }
.meta { font-size: 0.84rem; color: var(--muted); font-weight: 500; margin-bottom: 0.7rem; }
.card p { margin: 0.55rem 0; font-size: 0.96rem; color: var(--ink); }
.tags { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.85rem; }
.tag { font-size: 0.74rem; font-weight: 600; padding: 0.16rem 0.58rem; border-radius: 999px; background: var(--wash); color: var(--accent); }
ul { margin: 0.65rem 0 0.65rem 0; padding: 0; list-style: none; }
li { position: relative; padding-left: 0.9rem; margin-bottom: 0.4rem; font-size: 0.93rem; color: var(--ink); border-left: 2px solid #c5bff4; }
a { color: var(--accent); text-decoration: none; font-weight: 600; }
a:hover { text-decoration: underline; }
.roles { display: grid; gap: 0.55rem; }
.role-row { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; padding: 0.78rem 1.1rem; background: var(--paper); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 2px 0 #dce1ed; }
.role-row strong { font-weight: 650; letter-spacing: -0.015em; }
footer { margin-top: 3rem; padding-top: 1.1rem; border-top: 1px solid var(--line); font-size: 0.8rem; color: var(--muted); }
@media print {
  body { background: #fff; color: #000; }
  .hero { background: #f5f4fc; box-shadow: none; }
  .card, .role-row { box-shadow: none; break-inside: avoid; }
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
    snapshot = vault.build_tier_snapshot(
        tier=tier,
        episode_ids=episode_ids,
        approved_only=approved_only,
        strict_leaks=strict_leaks,
        embed_artifacts=(fmt.lower().strip() == "html"),
    )
    fmt = fmt.lower().strip()
    if fmt == "json":
        content = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
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
