"""Multi-channel local importers for Career Context AI v2 (zero external dependencies).

Supports:
- folder / file: Markdown, TXT, HTML (cleaned), JSON, CSV (resumes, notes, Google Docs exports)
- github: local git repo history (`git log`) OR GitHub PR/Issue/RFC JSON exports
- slack: standard Slack workspace export folder (channels.json + <channel>/*.json, threaded)
- notion: Notion Markdown/CSV export folder (strips 32-char Notion UUID filename suffixes)
- linkedin: LinkedIn data export folder/CSVs (Profile.csv, Positions.csv, Shares.csv, Articles)
- x: X/Twitter data archive (tweets.js or tweets.json)
- substack: Substack RSS/Atom XML feed OR exported HTML/CSV posts
- direct: single pasted text / voice-note / live-connector capture passed by the user's LLM
"""
from __future__ import annotations

import base64
import csv
import email.utils
import html
import io
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .db import CareerVault

TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".org", ".html", ".htm", ".json", ".csv", ".docx"}
NOTION_ID_SUFFIX = re.compile(r"\s+[0-9a-f]{32}$", re.IGNORECASE)


def extract_docx_bytes(data: bytes) -> str:
    """Extract clean paragraph text from a .docx archive using pure Python stdlib."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("Invalid .docx file: missing word/document.xml")
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for p in root.iter():
        if p.tag.endswith("}p") or p.tag == "p":
            runs = [t.text for t in p.iter() if (t.tag.endswith("}t") or t.tag == "t") and t.text]
            line = "".join(runs).strip()
            if line:
                paragraphs.append(line)
    return "\n\n".join(paragraphs)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True
        elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self._parts))
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", raw)).strip()


def strip_html(raw_html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    return parser.text()


def _iso_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    # RFC-2822 (RSS pubDate / Twitter created_at)
    for parser in (
        lambda s: email.utils.parsedate_to_datetime(s),
        lambda s: datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y"),
        lambda s: datetime.strptime(s, "%b %Y"),
        lambda s: datetime.strptime(s, "%Y/%m/%d"),
    ):
        try:
            dt = parser(raw)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    # Unix timestamp string (Slack ts: "1726675200.000100")
    if re.match(r"^\d{10}(\.\d+)?$", raw):
        dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    return raw[:10] if re.match(r"^\d{4}", raw) else ""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── 1. Generic Folder / File (Resumes, Docs, Google Docs exports, Notes) ────

def import_folder(
    vault: CareerVault,
    target: str | Path,
    *,
    channel: str = "doc",
    sensitivity: str = "L0",
    scope: str = "",
) -> dict[str, Any]:
    root = Path(target).expanduser().resolve()
    files = [root] if root.is_file() else sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS
        and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )
    ingested: list[dict[str, Any]] = []
    for path in files:
        if path.suffix.lower() == ".docx":
            raw = extract_docx_bytes(path.read_bytes())
        else:
            raw = _read_text(path)
            if path.suffix.lower() in (".html", ".htm"):
                raw = strip_html(raw)
        if not raw.strip():
            continue
        title = path.stem.replace("_", " ").replace("-", " ").strip()
        rel = str(path.relative_to(root)) if root.is_dir() else path.name
        res = vault.ingest_source(
            title=title,
            raw_text=raw,
            channel=channel,
            locator=rel,
            scope=scope or f"Imported local file ({rel})",
            sensitivity=sensitivity,
            metadata={"filename": path.name, "extension": path.suffix.lower()},
        )
        ingested.append(res)
    return {"importer": "folder", "channel": channel, "count": len(ingested), "items": ingested}


# ── 2. GitHub (PR/Issue JSON export OR local git repo history) ──────────────

def import_github(
    vault: CareerVault,
    target: str | Path,
    *,
    author_filter: str = "",
    max_commits: int = 100,
    sensitivity: str = "L1",
) -> dict[str, Any]:
    path = Path(target).expanduser().resolve()
    ingested: list[dict[str, Any]] = []

    if path.is_file() and path.suffix.lower() == ".json":
        payload = json.loads(_read_text(path))
        records = payload if isinstance(payload, list) else payload.get("items", payload.get("pull_requests", [payload]))
        for rec in records:
            if not isinstance(rec, dict):
                continue
            title = rec.get("title") or f"GitHub #{rec.get('number', 'item')}"
            body = rec.get("body") or ""
            comments = rec.get("comments") or []
            if isinstance(comments, list):
                comment_lines = [
                    f"- {c.get('author', c.get('user', {}).get('login', 'reviewer'))}: {c.get('body', '')}"
                    for c in comments if isinstance(c, dict) and c.get("body")
                ]
                if comment_lines:
                    body = f"{body}\n\nDiscussion:\n" + "\n".join(comment_lines)
            author = rec.get("author") or (rec.get("user") or {}).get("login", "")
            if isinstance(author, dict):
                author = author.get("login", "")
            if author_filter and author_filter.lower() not in str(author).lower():
                continue
            event_date = _iso_date(rec.get("merged_at") or rec.get("created_at") or rec.get("date") or "")
            url = rec.get("html_url") or rec.get("url") or ""
            state = rec.get("state", "")
            prefix = f"[PR/Issue #{rec.get('number', '')} | state={state} | author={author}]\n"
            res = vault.ingest_source(
                title=title,
                raw_text=(prefix + body).strip(),
                channel="github",
                author=str(author),
                event_date=event_date,
                url=url,
                locator=f"github:{path.name}#{rec.get('number', '')}",
                scope="GitHub PR/Issue JSON export",
                sensitivity=sensitivity,
                metadata={"number": rec.get("number"), "state": state, "repo": rec.get("repo", "")},
            )
            ingested.append(res)
        return {"importer": "github_json", "count": len(ingested), "items": ingested}

    # Local git repository: group commits into monthly digests or individual notable commits
    if (path / ".git").exists():
        cmd = ["git", "-C", str(path), "log", f"-n{max_commits}", "--format=%H%x1f%an%x1f%ad%x1f%s%x1f%b%x1e", "--date=short"]
        if author_filter:
            cmd.append(f"--author={author_filter}")
        out = subprocess.check_output(cmd, text=True, errors="replace")
        for entry in out.split("\x1e"):
            parts = entry.strip().split("\x1f")
            if len(parts) < 4:
                continue
            sha, author, date, subj = parts[0], parts[1], parts[2], parts[3]
            body = parts[4].strip() if len(parts) > 4 else ""
            raw = f"Commit {sha[:10]} ({date}) by {author}\n{subj}\n\n{body}".strip()
            res = vault.ingest_source(
                title=f"[{path.name}] {subj[:80]}",
                raw_text=raw,
                channel="github",
                author=author,
                event_date=date,
                locator=f"git:{path.name}@{sha[:10]}",
                scope=f"Local git commit in {path.name}",
                sensitivity=sensitivity,
                metadata={"repo": path.name, "sha": sha},
            )
            ingested.append(res)
        return {"importer": "github_git_log", "count": len(ingested), "items": ingested}

    raise ValueError(f"Expected a GitHub JSON export file or local git repo at {path}")


# ── 3. Slack Export (Standard Workspace Export Folder or Single Channel JSON) ─

def import_slack(
    vault: CareerVault,
    target: str | Path,
    *,
    sensitivity: str = "L0",
) -> dict[str, Any]:
    path = Path(target).expanduser().resolve()
    users: dict[str, str] = {}
    if path.is_dir() and (path / "users.json").is_file():
        for u in json.loads(_read_text(path / "users.json")):
            if isinstance(u, dict) and u.get("id"):
                profile = u.get("profile") or {}
                users[u["id"]] = profile.get("real_name") or u.get("name") or u["id"]

    json_files: list[tuple[str, Path]] = []
    if path.is_file():
        json_files.append((path.stem, path))
    else:
        for child in sorted(path.iterdir()):
            if child.is_dir():
                for jf in sorted(child.glob("*.json")):
                    json_files.append((child.name, jf))

    ingested: list[dict[str, Any]] = []
    for channel_name, jf in json_files:
        messages = json.loads(_read_text(jf))
        if not isinstance(messages, list):
            continue
        # Group by thread_ts (or standalone ts)
        threads: dict[str, list[dict[str, Any]]] = {}
        for msg in messages:
            if not isinstance(msg, dict) or not msg.get("text"):
                continue
            key = msg.get("thread_ts") or msg.get("ts") or "0"
            threads.setdefault(key, []).append(msg)

        for thread_ts, msgs in threads.items():
            msgs.sort(key=lambda m: float(m.get("ts", 0)))
            lines = []
            authors = []
            for m in msgs:
                uid = m.get("user") or m.get("username") or "unknown"
                name = users.get(uid, uid)
                if name not in authors:
                    authors.append(name)
                lines.append(f"{name}: {m.get('text', '').strip()}")
            event_date = _iso_date(thread_ts)
            first_line = msgs[0].get("text", "")[:72].replace("\n", " ")
            res = vault.ingest_source(
                title=f"#{channel_name} ({event_date}): {first_line}",
                raw_text="\n".join(lines),
                channel="slack",
                author=", ".join(authors[:5]),
                event_date=event_date,
                locator=f"slack:#{channel_name}/{jf.name}#{thread_ts}",
                scope=f"Slack export thread from #{channel_name}",
                sensitivity=sensitivity,
                metadata={"slack_channel": channel_name, "message_count": len(msgs)},
            )
            ingested.append(res)
    return {"importer": "slack", "count": len(ingested), "items": ingested}


# ── 4. Notion Export Folder (Strips 32-char UUID Suffixes) ──────────────────

def import_notion(
    vault: CareerVault,
    target: str | Path,
    *,
    sensitivity: str = "L0",
) -> dict[str, Any]:
    root = Path(target).expanduser().resolve()
    files = [root] if root.is_file() else sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in (".md", ".csv", ".html")
    )
    ingested: list[dict[str, Any]] = []
    for path in files:
        raw = _read_text(path)
        if path.suffix.lower() == ".html":
            raw = strip_html(raw)
        if not raw.strip():
            continue
        clean_title = NOTION_ID_SUFFIX.sub("", path.stem).strip() or path.stem
        # Try to extract a date from Notion frontmatter/header lines like "Date: 2024-08-12"
        m = re.search(r"^(?:Date|Created|Updated):\s*(.+)$", raw[:600], re.IGNORECASE | re.MULTILINE)
        event_date = _iso_date(m.group(1)) if m else ""
        rel = str(path.relative_to(root)) if root.is_dir() else path.name
        res = vault.ingest_source(
            title=clean_title,
            raw_text=raw,
            channel="notion",
            event_date=event_date,
            locator=f"notion:{rel}",
            scope=f"Notion export ({rel})",
            sensitivity=sensitivity,
        )
        ingested.append(res)
    return {"importer": "notion", "count": len(ingested), "items": ingested}


# ── 5. LinkedIn Data Export (Positions.csv, Shares.csv, Profile.csv) ────────

def import_linkedin(
    vault: CareerVault,
    target: str | Path,
    *,
    auto_create_roles: bool = True,
    sensitivity: str = "L3",
) -> dict[str, Any]:
    root = Path(target).expanduser().resolve()
    ingested: list[dict[str, Any]] = []
    roles_created = 0

    def read_csv(p: Path) -> list[dict[str, str]]:
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    files = [root] if root.is_file() else sorted(root.rglob("*.csv"))
    for p in files:
        low = p.name.lower()
        rows = read_csv(p)
        if "position" in low:
            for idx, r in enumerate(rows):
                company = r.get("Company Name") or r.get("Company") or ""
                title = r.get("Title") or ""
                desc = r.get("Description") or ""
                started = _iso_date(r.get("Started On") or "")
                finished = _iso_date(r.get("Finished On") or "")
                raw = f"Role: {title} at {company}\nDates: {started or '?'} to {finished or 'Present'}\n\n{desc}".strip()
                res = vault.ingest_source(
                    title=f"LinkedIn Role: {title} @ {company}",
                    raw_text=raw,
                    channel="linkedin",
                    event_date=started,
                    locator=f"linkedin:{p.name}#{idx + 1}",
                    scope="LinkedIn Positions export",
                    sensitivity=sensitivity,
                )
                ingested.append(res)
                if auto_create_roles and title:
                    vault.upsert_role(
                        title=title,
                        organization=company,
                        start_date=started,
                        end_date=finished,
                        is_current=not bool(finished),
                        summary_l1=desc,
                        source_refs=[res["id"]],
                    )
                    roles_created += 1
        elif "share" in low or "post" in low:
            for idx, r in enumerate(rows):
                commentary = (r.get("ShareCommentary") or r.get("Commentary") or r.get("Text") or "").strip()
                if not commentary:
                    continue
                date = _iso_date(r.get("Date") or "")
                url = r.get("ShareLink") or r.get("Url") or ""
                res = vault.ingest_source(
                    title=f"LinkedIn post ({date}): {commentary[:64]}",
                    raw_text=commentary,
                    channel="linkedin",
                    event_date=date,
                    url=url,
                    locator=f"linkedin:{p.name}#{idx + 1}",
                    scope="LinkedIn public post export",
                    sensitivity="L3",
                )
                ingested.append(res)
        elif "profile" in low and rows:
            r = rows[0]
            name = f"{r.get('First Name', '')} {r.get('Last Name', '')}".strip()
            headline = r.get("Headline") or ""
            summary = r.get("Summary") or ""
            raw = f"Name: {name}\nHeadline: {headline}\n\n{summary}".strip()
            if raw:
                res = vault.ingest_source(
                    title=f"LinkedIn Profile: {name or 'Self'}",
                    raw_text=raw,
                    channel="linkedin",
                    locator=f"linkedin:{p.name}",
                    scope="LinkedIn Profile export",
                    sensitivity="L3",
                )
                ingested.append(res)
    return {"importer": "linkedin", "count": len(ingested), "roles_created": roles_created, "items": ingested}


# ── 6. X / Twitter Archive (tweets.js or tweets.json) ───────────────────────

def import_x(
    vault: CareerVault,
    target: str | Path,
    *,
    min_chars: int = 40,
    exclude_retweets: bool = True,
    handle: str = "",
) -> dict[str, Any]:
    path = Path(target).expanduser().resolve()
    raw = _read_text(path).strip()
    # Standard X archive starts with `window.YTD.tweets.part0 = [...]`
    if "=" in raw[:80] and not raw.startswith("[") and not raw.startswith("{"):
        raw = raw.split("=", 1)[1].strip().rstrip(";")
    data = json.loads(raw)
    if not isinstance(data, list):
        data = [data]

    ingested: list[dict[str, Any]] = []
    for entry in data:
        tw = entry.get("tweet", entry) if isinstance(entry, dict) else {}
        text = (tw.get("full_text") or tw.get("text") or "").strip()
        if not text or len(text) < min_chars:
            continue
        if exclude_retweets and text.startswith("RT @"):
            continue
        tid = str(tw.get("id_str") or tw.get("id") or "")
        date = _iso_date(tw.get("created_at") or "")
        url = f"https://x.com/{handle}/status/{tid}" if (handle and tid) else ""
        res = vault.ingest_source(
            title=f"X post ({date}): {text[:64].replace(chr(10), ' ')}",
            raw_text=text,
            channel="x",
            author=handle,
            event_date=date,
            url=url,
            locator=f"x:{tid or path.name}",
            scope="Public X/Twitter archive post",
            sensitivity="L3",
            metadata={"tweet_id": tid, "favorites": tw.get("favorite_count"), "retweets": tw.get("retweet_count")},
        )
        ingested.append(res)
    return {"importer": "x", "count": len(ingested), "items": ingested}


# ── 7. Substack (RSS/Atom XML feed OR exported HTML posts) ──────────────────

def import_substack(
    vault: CareerVault,
    target: str | Path,
    *,
    author: str = "",
) -> dict[str, Any]:
    path = Path(target).expanduser().resolve()
    ingested: list[dict[str, Any]] = []

    if path.is_file() and path.suffix.lower() in (".xml", ".rss"):
        root = ET.fromstring(_read_text(path))
        items = root.findall(".//item")
        for item in items:
            title = (item.findtext("title") or "Substack essay").strip()
            link = (item.findtext("link") or "").strip()
            date = _iso_date(item.findtext("pubDate") or "")
            # Prefer content:encoded over description
            content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
            body_html = content_el.text if (content_el is not None and content_el.text) else (item.findtext("description") or "")
            body = strip_html(body_html)
            if not body:
                continue
            res = vault.ingest_source(
                title=title,
                raw_text=body,
                channel="substack",
                author=author,
                event_date=date,
                url=link,
                locator=f"substack:{path.name}",
                scope="Public Substack RSS essay",
                sensitivity="L3",
            )
            ingested.append(res)
        return {"importer": "substack_rss", "count": len(ingested), "items": ingested}

    # Substack export folder of HTML posts
    return import_folder(vault, path, channel="substack", sensitivity="L3", scope="Public Substack export")


# ── 8. Legacy Career Context v1 Migrator (HTML or JSON packet -> v2 Vault) ──

def _infer_v1_channel(src: dict[str, Any]) -> str:
    hay = " ".join([
        str(src.get("id", "")),
        str(src.get("label", "")),
        str(src.get("locator", "")),
        str(src.get("scope", "")),
    ]).lower()
    if "slack" in hay:
        return "slack"
    if "notion" in hay:
        return "notion"
    if "github" in hay or "git:" in hay or "commit" in hay or "pr " in hay or "pull request" in hay:
        return "github"
    if "linkedin" in hay:
        return "linkedin"
    if "twitter" in hay or "x.com" in hay or "tweet" in hay:
        return "x"
    if "substack" in hay:
        return "substack"
    if "google drive" in hay or "gdoc" in hay or "transcript" in hay:
        return "gdocs"
    if "resume" in hay or "cv" in hay:
        return "resume"
    if src.get("kind") == "person_account":
        return "voice_note"
    return "doc"


def import_v1(vault: CareerVault, target: str | Path) -> dict[str, Any]:
    """Migrate a Career Context v1 HTML or JSON packet (including embedded screenshots) into v2 SQLite."""
    path = Path(target).expanduser().resolve()
    raw = _read_text(path)
    embedded_imgs: dict[str, tuple[str, bytes]] = {}
    if path.suffix.lower() in (".html", ".htm"):
        m = re.search(r'<script[^>]+id="career-context-data"[^>]*>(.*?)</script>', raw, re.S)
        if not m:
            raise ValueError(f"No <script id='career-context-data'> block found in {path}")
        pkt = json.loads(m.group(1))
        # Extract embedded <img id="..." src="data:image/...;base64,...">
        for tag_m in re.finditer(r'<img\b[^>]*>', raw):
            tag = tag_m.group(0)
            id_m = re.search(r'\bid="([^"]+)"', tag)
            src_m = re.search(r'\bsrc="data:(image/[a-zA-Z0-9.+-]+);base64,([^"]+)"', tag)
            if id_m and src_m:
                try:
                    embedded_imgs[id_m.group(1)] = (src_m.group(1).lower(), base64.b64decode(src_m.group(2)))
                except Exception:
                    pass
    else:
        pkt = json.loads(raw)

    person = pkt.get("person") or {}
    pp = pkt.get("publicProfile") or {}
    vault.init(
        name=person.get("name", ""),
        headline=pp.get("headline", ""),
        goal="Migrated from career-context/v1",
    )
    vault.update_person(
        name=person.get("name", ""),
        headline=pp.get("headline", ""),
        overview_l1=person.get("overview", ""),
        overview_l3=pp.get("overview", "") if pp.get("shareOverview") else "",
        background=person.get("background", []),
    )

    sources_imported = 0
    for s in pkt.get("sources", []):
        content = (s.get("content") or "").strip()
        if not content:
            continue
        ch = _infer_v1_channel(s)
        locator = s.get("locator") or ""
        url = locator if locator.startswith("https://") else ""
        sens = "L3" if (url and ch in ("github", "linkedin", "x", "substack")) else "L0"
        vault.ingest_source(
            source_id=s["id"],
            title=s.get("label") or s["id"],
            raw_text=content,
            channel=ch,
            event_date=_iso_date(s.get("date") or ""),
            url=url,
            locator=locator,
            scope=s.get("scope") or f"Migrated from v1 ({s.get('kind', 'source')})",
            sensitivity=sens,
            metadata={"v1_kind": s.get("kind", "")},
        )
        sources_imported += 1

    roles_imported = 0
    account_to_role: dict[str, str] = {}
    for r in (pkt.get("presentation") or {}).get("experienceRoles") or []:
        vault.upsert_role(
            role_id=r["id"],
            title=r.get("title", ""),
            organization=r.get("organization", ""),
            period_label=r.get("period", ""),
            is_current=bool(r.get("current")),
            source_refs=[sid for sid in r.get("sourceRefs", []) if sid],
        )
        for aid in r.get("accountIds", []):
            account_to_role[aid] = r["id"]
        roles_imported += 1

    episodes_imported = 0
    artifacts_imported = 0
    for a in pkt.get("accounts", []):
        period = a.get("period", "")
        years = re.findall(r"\b(20\d{2}|19\d{2})\b", period)
        start_d = f"{years[0]}-01" if years else ""
        end_d = f"{years[-1]}-12" if len(years) > 1 else ""
        vault.upsert_episode(
            episode_id=a["id"],
            role_id=account_to_role.get(a["id"]),
            title=a.get("title", a["id"]),
            period_label=period,
            start_date=start_d,
            end_date=end_d,
            status="ongoing" if "ongoing" in period.lower() or "present" in period.lower() else "shipped",
            summary_l1=a.get("summary", ""),
            context_l1=a.get("context", ""),
            contribution_l1=a.get("contribution", ""),
            decisions=a.get("decisions", []),
            shared_credit_l1=a.get("sharedCredit", ""),
            outcome_l1=a.get("outcome", ""),
            limits=a.get("limits", []),
            questions=a.get("questions", []),
            tags=a.get("tags", []),
            capabilities=a.get("capabilities", []),
            source_refs=a.get("sourceRefs", []),
        )
        episodes_imported += 1
        for art in a.get("artifacts") or []:
            emb_id = art.get("embeddedId") or ""
            if emb_id in embedded_imgs:
                mt, data = embedded_imgs[emb_id]
                vault.add_artifact(
                    episode_id=a["id"],
                    data=data,
                    media_type=mt,
                    title=art.get("title", ""),
                    caption=art.get("caption", ""),
                    artifact_link_id=art.get("id") or None,
                    share_l2=False,
                    share_l3=False,
                )
                artifacts_imported += 1

    claims_imported = 0
    for c in (pkt.get("memory") or {}).get("claims", []):
        ev = [{"source_id": e["sourceId"], "quote": e["quote"]} for e in c.get("evidence", []) if e.get("sourceId") and e.get("quote")]
        cev = [{"source_id": e["sourceId"], "quote": e["quote"]} for e in c.get("counterEvidence", []) if e.get("sourceId") and e.get("quote")]
        try:
            vault.upsert_claim(
                claim_id=c["id"],
                episode_id=(c.get("accountIds") or [None])[0],
                statement=c.get("statement", ""),
                kind=c.get("kind", "fact"),
                status=c.get("status", "candidate"),
                rationale=c.get("rationale", ""),
                next_question=c.get("nextQuestion", ""),
                evidence_quotes=ev,
                counter_quotes=cev,
            )
            claims_imported += 1
        except Exception:
            pass

    vault.compact()
    return {
        "importer": "v1",
        "source_file": str(path),
        "sources_imported": sources_imported,
        "roles_imported": roles_imported,
        "episodes_imported": episodes_imported,
        "artifacts_imported": artifacts_imported,
        "claims_imported": claims_imported,
    }


# ── 9. Smart Single-File Browser Upload Auto-Router ─────────────────────────

def import_uploaded_file(
    vault: CareerVault,
    filename: str,
    raw_bytes: bytes,
    *,
    channel_hint: str = "auto",
    sensitivity: str = "L0",
) -> dict[str, Any]:
    """Auto-detect and ingest any file uploaded from the browser Studio UI."""
    safe_name = Path(filename).name or "upload.txt"
    ext = Path(safe_name).suffix.lower()
    low = safe_name.lower()

    if ext == ".docx":
        text = extract_docx_bytes(raw_bytes)
        ch = "resume" if ("resume" in low or "cv" in low) else (channel_hint if channel_hint != "auto" else "doc")
        item = vault.ingest_source(
            title=Path(safe_name).stem.replace("_", " ").replace("-", " ").strip(),
            raw_text=text,
            channel=ch,
            locator=f"upload:{safe_name}",
            scope=f"Browser uploaded DOCX ({safe_name})",
            sensitivity=sensitivity,
        )
        return {"importer": "docx_upload", "count": 1, "items": [item]}

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / safe_name
        p.write_bytes(raw_bytes)
        text_preview = raw_bytes[:4096].decode("utf-8", errors="replace")

        # Auto-detect v1 CAREER-CONTEXT.html or career-context/v1 JSON
        if channel_hint == "v1" or 'id="career-context-data"' in text_preview or '"career-context/v1"' in text_preview:
            return import_v1(vault, p)
        if channel_hint == "x" or "window.YTD.tweets" in text_preview or low in ("tweets.js", "tweets.json"):
            return import_x(vault, p)
        if channel_hint == "substack" or ext in (".xml", ".rss") or "<rss" in text_preview:
            return import_substack(vault, p)
        if channel_hint == "linkedin" or (ext == ".csv" and any(k in low for k in ("position", "share", "profile"))):
            return import_linkedin(vault, p)
        if channel_hint == "github" or (ext == ".json" and ('"pull_requests"' in text_preview or '"html_url"' in text_preview)):
            return import_github(vault, p)
        if channel_hint == "slack" or (ext == ".json" and '"thread_ts"' in text_preview):
            return import_slack(vault, p)
        if channel_hint == "notion" or NOTION_ID_SUFFIX.search(Path(safe_name).stem):
            return import_notion(vault, p, sensitivity=sensitivity)

        ch = channel_hint if channel_hint != "auto" else ("resume" if ("resume" in low or "cv" in low) else "doc")
        return import_folder(vault, p, channel=ch, sensitivity=sensitivity, scope=f"Browser upload ({safe_name})")


