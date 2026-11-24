"""SQLite FTS5 career knowledge vault, dynamic timeline, artifacts, and L0-L3 granularity engine.

Zero external dependencies (Python 3.11+ stdlib only).
- L0: Raw ingested source vault (never exported; collect-first without forced interpretation).
- L1: Private candid synthesis (roles, episodes, claims, contradictions, voice; default mode).
- L2: Confidential-safe overview (decisions, architecture, generalized scope; leak-checked).
- L3: Public / high-signal summary (approved public facts & public links; leak-checked).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPLICATION_ID = 0x43435632  # 'CCV2'
SCHEMA_VERSION = 3

VALID_CHANNELS = {
    "resume", "github", "slack", "notion", "gdocs", "linkedin",
    "x", "substack", "blog", "doc", "voice_note", "email", "other",
}
VALID_TIERS = ("L0", "L1", "L2", "L3")
EXPORTABLE_TIERS = ("L1", "L2", "L3")
SHAREABLE_TIERS = ("L2", "L3")
VALID_CLAIM_KINDS = {"fact", "self_report", "interpretation", "hypothesis", "correction"}
VALID_CLAIM_STATUS = {"candidate", "supported", "qualified", "disputed", "rejected", "withdrawn"}
VALID_RELATIONS = {"supports", "qualifies", "contradicts", "supersedes"}
VALID_SENSITIVITY_CATEGORIES = {
    "customer", "metric", "proprietary", "person", "internal_id", "compensation", "other",
}

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

BUILTIN_LEAK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("token_or_key", re.compile(
        r"(?:api[_-]?key|access[_-]?token|secret|bearer|x-amz-signature|sk-[a-zA-Z0-9]{12,}|ghp_[a-zA-Z0-9]{20,})",
        re.IGNORECASE,
    )),
    ("email_address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("slack_channel_ref", re.compile(r"(?:^|\s)#[a-z][a-z0-9_-]{2,}\b")),
]

# Common non-sensitive capitalized words ignored by suggest_sensitive_terms
COMMON_CAP_WORDS = {
    "The", "This", "That", "These", "Those", "There", "Their", "They", "When", "Where", "What",
    "Which", "While", "With", "Without", "After", "Before", "During", "From", "Into", "Over",
    "Under", "Between", "Through", "About", "Across", "Also", "Both", "Each", "Some", "Many",
    "Most", "More", "Less", "First", "Second", "Third", "Later", "Early", "Earlier", "Still",
    "Only", "Even", "Because", "However", "Instead", "Rather", "Other", "Another", "Built",
    "Led", "Made", "Used", "Kept", "Moved", "Ran", "Wrote", "Created", "Designed", "Worked",
    "Helped", "Started", "Turned", "Shared", "Reviewed", "Tested", "Proposed", "Authored",
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday", "Present", "Draft", "Note", "Notes", "Summary", "Outcome", "Context",
    "Team", "Teams", "Role", "Roles", "Work", "Project", "Projects", "Hiring", "Recruiting",
    "Engineering", "Product", "Design", "Operations", "Leadership", "Management", "Staff",
    "Senior", "Principal", "Founder", "Founding", "Engineer", "Manager", "Director", "Head",
    "Python", "Postgres", "PostgreSQL", "SQLite", "JavaScript", "TypeScript", "React", "Go",
    "Rust", "Git", "GitHub", "Slack", "Notion", "LinkedIn", "Substack", "Google", "Drive",
    "HTML", "JSON", "CSV", "API", "MCP", "AI", "LLM", "LLMs", "ATS", "EU", "US", "UK", "OK",
    "PR", "RFC", "Q1", "Q2", "Q3", "Q4", "H1", "H2",
}

DDL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL DEFAULT '',
    headline TEXT NOT NULL DEFAULT '',
    overview_l1 TEXT NOT NULL DEFAULT '',
    overview_l2 TEXT NOT NULL DEFAULT '',
    overview_l3 TEXT NOT NULL DEFAULT '',
    background_json TEXT NOT NULL DEFAULT '[]',
    preferences_json TEXT NOT NULL DEFAULT '{}',
    goal TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- Layer 0: Collect-first raw source vault
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    event_date TEXT NOT NULL DEFAULT '',
    captured_at TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    locator TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    sensitivity TEXT NOT NULL DEFAULT 'L0',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS source_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    text TEXT NOT NULL,
    chunk_sha256 TEXT NOT NULL,
    UNIQUE(source_id, chunk_index)
);

-- External-content FTS5: stores ONLY the inverted index, ZERO duplicate text copy!
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='source_chunks',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS source_chunks_ai AFTER INSERT ON source_chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS source_chunks_ad AFTER DELETE ON source_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS source_chunks_au AFTER UPDATE ON source_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;

-- Compact float16 cached embeddings keyed by content hash (shared by chunks AND episodes)
CREATE TABLE IF NOT EXISTS embeddings_cache (
    content_sha256 TEXT NOT NULL,
    model_id TEXT NOT NULL,
    dim INTEGER NOT NULL,
    dtype TEXT NOT NULL DEFAULT 'float16',
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (content_sha256, model_id)
);

-- Content-addressed binary artifacts (screenshots/images stored ONCE, never duplicated)
CREATE TABLE IF NOT EXISTS artifacts (
    sha256 TEXT PRIMARY KEY,
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    data BLOB NOT NULL,
    created_at TEXT NOT NULL
);

-- Channel & MCP Scan Ledger (tracks what channels the user works on & what has been scanned)
CREATE TABLE IF NOT EXISTS channel_scans (
    channel TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    access_method TEXT NOT NULL DEFAULT 'mcp',      -- mcp | connector | export | manual
    status TEXT NOT NULL DEFAULT 'declared',        -- declared | scanning | scanned | skipped
    date_range_covered TEXT NOT NULL DEFAULT '',
    queries_run_json TEXT NOT NULL DEFAULT '[]',
    items_ingested INTEGER NOT NULL DEFAULT 0,
    remaining_notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- Layer 1: Private canonical knowledge graph
CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    organization TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    period_label TEXT NOT NULL DEFAULT '',
    is_current INTEGER NOT NULL DEFAULT 0,
    summary_l1 TEXT NOT NULL DEFAULT '',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    role_id TEXT REFERENCES roles(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    period_label TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'shipped',
    summary_l1 TEXT NOT NULL,
    context_l1 TEXT NOT NULL DEFAULT '',
    contribution_l1 TEXT NOT NULL DEFAULT '',
    decisions_json TEXT NOT NULL DEFAULT '[]',
    shared_credit_l1 TEXT NOT NULL DEFAULT '',
    outcome_l1 TEXT NOT NULL DEFAULT '',
    limits_json TEXT NOT NULL DEFAULT '[]',
    questions_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    review_status TEXT NOT NULL DEFAULT 'draft',
    importance INTEGER NOT NULL DEFAULT 0,
    content_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episode_artifacts (
    id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    artifact_sha256 TEXT NOT NULL REFERENCES artifacts(sha256),
    title TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    share_l2 INTEGER NOT NULL DEFAULT 0,
    share_l3 INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    episode_id UNINDEXED,
    title,
    summary_l1,
    decisions,
    outcome_l1,
    tags,
    tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    episode_id TEXT REFERENCES episodes(id) ON DELETE SET NULL,
    statement TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'fact',
    status TEXT NOT NULL DEFAULT 'candidate',
    actor TEXT NOT NULL DEFAULT '',
    action_state TEXT NOT NULL DEFAULT 'unknown',
    rationale TEXT NOT NULL DEFAULT '',
    next_question TEXT NOT NULL DEFAULT '',
    anchors_json TEXT NOT NULL DEFAULT '[]',
    counter_anchors_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_relations (
    from_claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    to_claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    PRIMARY KEY (from_claim_id, to_claim_id, relation_type)
);

-- Layer 2 & 3: Explicit Granularity Projections + Sensitivity Registry
CREATE TABLE IF NOT EXISTS sensitive_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE,
    replacement TEXT NOT NULL DEFAULT '[redacted]',
    category TEXT NOT NULL DEFAULT 'other',
    case_sensitive INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tier_projections (
    episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('L2', 'L3')),
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    decisions_json TEXT NOT NULL DEFAULT '[]',
    outcome TEXT NOT NULL DEFAULT '',
    shared_credit TEXT NOT NULL DEFAULT '',
    public_links_json TEXT NOT NULL DEFAULT '[]',
    approved INTEGER NOT NULL DEFAULT 0,
    derived_from_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (episode_id, tier)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(obj: Any) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or fallback


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[tuple[int, int, str]]:
    if not text:
        return [(0, 0, "")]
    if len(text) <= size:
        return [(0, len(text), text)]
    chunks: list[tuple[int, int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + size)
        if end < n:
            cut = text.rfind("\n\n", start + size // 2, end)
            if cut == -1:
                cut = text.rfind(". ", start + size // 2, end)
                if cut != -1:
                    cut += 1
            if cut == -1:
                cut = text.rfind(" ", start + size // 2, end)
            if cut > start:
                end = cut
        piece = text[start:end]
        chunks.append((start, end, piece))
        if end >= n:
            break
        start = max(start + 1, end - overlap)
    return chunks


FTS_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "between", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "give", "had", "has", "have", "he", "her", "him", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "just", "make", "me", "my", "no", "not",
    "of", "on", "or", "our", "out", "over", "say", "she", "so", "some", "take", "tell", "than",
    "that", "the", "their", "them", "then", "there", "these", "they", "this", "to", "two", "up",
    "us", "was", "we", "were", "what", "when", "where", "which", "who", "whose", "will", "with",
    "without", "would", "you", "your",
}


def _fts_query(raw: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", raw.lower())
    filtered = [t for t in tokens if len(t) >= 2 and t not in FTS_STOPWORDS]
    use = filtered or tokens
    if not use:
        return '""'
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(use))


class CareerVault:
    """Direct local SQLite interface for Career Context AI v2."""

    def __init__(self, path: str | Path, *, readonly: bool = False):
        self.path = Path(path).expanduser().resolve()
        self.readonly = readonly
        if readonly:
            if not self.path.is_file():
                raise FileNotFoundError(f"No career database at {self.path}")
            self.conn = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA trusted_schema = OFF")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "CareerVault":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def compact(self) -> int:
        """Checkpoint WAL and VACUUM SQLite for minimal disk footprint."""
        if self.readonly:
            return self.path.stat().st_size
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.execute("VACUUM")
        return self.path.stat().st_size

    # ── Initialization & Person ──────────────────────────────────────────────

    def init(self, name: str = "", goal: str = "", headline: str = "") -> dict[str, Any]:
        if self.readonly:
            raise PermissionError("Cannot initialize a read-only vault")
        with self.conn:
            self.conn.executescript(DDL)
            self.conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            ts = now_iso()
            self.conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema', 'career-vault/v2')")
            self.conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('created_at', ?)", (ts,))
            self.conn.execute(
                """INSERT INTO person(id, name, headline, goal, updated_at)
                   VALUES (1, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name = CASE WHEN excluded.name != '' THEN excluded.name ELSE person.name END,
                     headline = CASE WHEN excluded.headline != '' THEN excluded.headline ELSE person.headline END,
                     goal = CASE WHEN excluded.goal != '' THEN excluded.goal ELSE person.goal END,
                     updated_at = excluded.updated_at""",
                (name.strip(), headline.strip(), goal.strip(), ts),
            )
            self._log("init", {"name": name, "goal": goal})
        return self.get_person()

    def get_person(self) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM person WHERE id = 1").fetchone()
        if not row:
            return {"name": "", "headline": "", "overview_l1": "", "overview_l2": "", "overview_l3": "",
                    "background": [], "preferences": {}, "goal": "", "updated_at": ""}
        return {
            "name": row["name"],
            "headline": row["headline"],
            "overview_l1": row["overview_l1"],
            "overview_l2": row["overview_l2"],
            "overview_l3": row["overview_l3"],
            "background": json.loads(row["background_json"]),
            "preferences": json.loads(row["preferences_json"]),
            "goal": row["goal"],
            "updated_at": row["updated_at"],
        }

    def update_person(self, **fields: Any) -> dict[str, Any]:
        current = self.get_person()
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """UPDATE person SET name=?, headline=?, overview_l1=?, overview_l2=?, overview_l3=?,
                   background_json=?, preferences_json=?, goal=?, updated_at=? WHERE id=1""",
                (
                    fields.get("name", current["name"]),
                    fields.get("headline", current["headline"]),
                    fields.get("overview_l1", current["overview_l1"]),
                    fields.get("overview_l2", current["overview_l2"]),
                    fields.get("overview_l3", current["overview_l3"]),
                    json.dumps(fields.get("background", current["background"]), ensure_ascii=False),
                    json.dumps(fields.get("preferences", current["preferences"]), ensure_ascii=False),
                    fields.get("goal", current["goal"]),
                    ts,
                ),
            )
            self._log("update_person", {"fields": sorted(fields.keys())})
        return self.get_person()

    # ── Layer 0: Collect-First Source Vault ──────────────────────────────────

    def ingest_source(
        self,
        *,
        title: str,
        raw_text: str,
        channel: str = "doc",
        source_id: str | None = None,
        author: str = "",
        event_date: str = "",
        url: str = "",
        locator: str = "",
        scope: str = "",
        sensitivity: str = "L0",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        channel = channel.lower().strip()
        if channel not in VALID_CHANNELS:
            channel = "other"
        if sensitivity not in VALID_TIERS:
            raise ValueError(f"Invalid sensitivity tier: {sensitivity}")
        raw_text = raw_text.strip()
        if not raw_text:
            raise ValueError("Source raw_text cannot be empty")
        digest = sha256_text(raw_text)
        ts = now_iso()

        if not source_id:
            existing = self.conn.execute(
                "SELECT id, title, channel, content_sha256 FROM sources WHERE content_sha256 = ?",
                (digest,),
            ).fetchone()
            if existing:
                return {
                    "id": existing["id"],
                    "title": existing["title"],
                    "channel": existing["channel"],
                    "content_sha256": existing["content_sha256"],
                    "deduplicated": True,
                }
            source_id = f"{channel}-{slugify(title)[:40]}-{digest[:8]}"

        chunks = chunk_text(raw_text)
        with self.conn:
            self.conn.execute(
                """INSERT INTO sources(
                     id, channel, title, author, event_date, captured_at, url, locator,
                     scope, raw_text, content_sha256, sensitivity, metadata_json
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     channel=excluded.channel, title=excluded.title, author=excluded.author,
                     event_date=excluded.event_date, captured_at=excluded.captured_at,
                     url=excluded.url, locator=excluded.locator, scope=excluded.scope,
                     raw_text=excluded.raw_text, content_sha256=excluded.content_sha256,
                     sensitivity=excluded.sensitivity, metadata_json=excluded.metadata_json""",
                (source_id, channel, title.strip(), author.strip(), event_date.strip(), ts,
                 url.strip(), locator.strip(), scope.strip(), raw_text, digest, sensitivity,
                 json.dumps(metadata or {}, ensure_ascii=False)),
            )
            # External-content triggers keep chunks_fts automatically synced!
            self.conn.execute("DELETE FROM source_chunks WHERE source_id = ?", (source_id,))
            for idx, (start, end, piece) in enumerate(chunks):
                c_sha = sha256_text(piece)
                self.conn.execute(
                    """INSERT INTO source_chunks(source_id, chunk_index, start_offset, end_offset, text, chunk_sha256)
                       VALUES (?,?,?,?,?,?)""",
                    (source_id, idx, start, end, piece, c_sha),
                )
            self._log("ingest_source", {"source_id": source_id, "channel": channel, "chunks": len(chunks)})
        return {
            "id": source_id,
            "title": title.strip(),
            "channel": channel,
            "event_date": event_date.strip(),
            "chunks": len(chunks),
            "content_sha256": digest,
            "deduplicated": False,
        }

    def list_sources(
        self,
        *,
        channel: str | None = None,
        unlinked_only: bool = False,
        include_raw: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        linked_ids = self._linked_source_ids()
        sql = "SELECT * FROM sources"
        params: list[Any] = []
        if channel:
            sql += " WHERE channel = ?"
            params.append(channel.lower())
        sql += " ORDER BY CASE WHEN event_date = '' THEN 1 ELSE 0 END, event_date DESC, captured_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            is_linked = r["id"] in linked_ids
            if unlinked_only and is_linked:
                continue
            item: dict[str, Any] = {
                "id": r["id"],
                "channel": r["channel"],
                "title": r["title"],
                "author": r["author"],
                "event_date": r["event_date"],
                "captured_at": r["captured_at"],
                "url": r["url"],
                "locator": r["locator"],
                "scope": r["scope"],
                "sensitivity": r["sensitivity"],
                "content_sha256": r["content_sha256"],
                "chars": len(r["raw_text"]),
                "linked": is_linked,
                "metadata": json.loads(r["metadata_json"]),
            }
            if include_raw:
                item["raw_text"] = r["raw_text"]
            else:
                item["preview"] = r["raw_text"][:240] + ("..." if len(r["raw_text"]) > 240 else "")
            out.append(item)
        return out

    def get_source(self, source_id: str) -> dict[str, Any]:
        r = self.conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not r:
            raise KeyError(f"Unknown source_id: {source_id}")
        return {
            "id": r["id"],
            "channel": r["channel"],
            "title": r["title"],
            "author": r["author"],
            "event_date": r["event_date"],
            "captured_at": r["captured_at"],
            "url": r["url"],
            "locator": r["locator"],
            "scope": r["scope"],
            "sensitivity": r["sensitivity"],
            "content_sha256": r["content_sha256"],
            "raw_text": r["raw_text"],
            "metadata": json.loads(r["metadata_json"]),
        }

    def _linked_source_ids(self) -> set[str]:
        linked: set[str] = set()
        for r in self.conn.execute("SELECT source_refs_json FROM roles"):
            linked.update(json.loads(r["source_refs_json"]))
        for r in self.conn.execute("SELECT source_refs_json FROM episodes"):
            linked.update(json.loads(r["source_refs_json"]))
        for r in self.conn.execute("SELECT anchors_json, counter_anchors_json FROM claims"):
            for a in json.loads(r["anchors_json"]) + json.loads(r["counter_anchors_json"]):
                if isinstance(a, dict) and a.get("source_id"):
                    linked.add(a["source_id"])
        return linked

    # ── Content-Addressed Visual Artifacts ───────────────────────────────────

    def add_artifact(
        self,
        *,
        episode_id: str,
        data: bytes,
        media_type: str,
        title: str = "",
        caption: str = "",
        artifact_link_id: str | None = None,
        share_l2: bool = False,
        share_l3: bool = False,
    ) -> dict[str, Any]:
        if not self.conn.execute("SELECT 1 FROM episodes WHERE id = ?", (episode_id,)).fetchone():
            raise KeyError(f"Unknown episode_id: {episode_id}")
        if media_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
            raise ValueError(f"Unsupported artifact media_type: {media_type}")
        digest = sha256_bytes(data)
        lid = artifact_link_id or f"{episode_id}-{digest[:10]}"
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO artifacts(sha256, media_type, size_bytes, data, created_at)
                   VALUES (?,?,?,?,?)""",
                (digest, media_type, len(data), data, ts),
            )
            self.conn.execute(
                """INSERT INTO episode_artifacts(id, episode_id, artifact_sha256, title, caption, share_l2, share_l3, created_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, caption=excluded.caption,
                     share_l2=excluded.share_l2, share_l3=excluded.share_l3""",
                (lid, episode_id, digest, title.strip(), caption.strip(), int(bool(share_l2)), int(bool(share_l3)), ts),
            )
            self._log("add_artifact", {"episode_id": episode_id, "sha256": digest, "bytes": len(data)})
        return {
            "id": lid,
            "episode_id": episode_id,
            "sha256": digest,
            "media_type": media_type,
            "size_bytes": len(data),
            "title": title.strip(),
            "caption": caption.strip(),
            "share_l2": bool(share_l2),
            "share_l3": bool(share_l3),
        }

    def set_artifact_sharing(self, link_id: str, *, share_l2: bool | None = None, share_l3: bool | None = None) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM episode_artifacts WHERE id = ?", (link_id,)).fetchone()
        if not row:
            raise KeyError(f"Unknown artifact link id: {link_id}")
        l2 = int(row["share_l2"] if share_l2 is None else bool(share_l2))
        l3 = int(row["share_l3"] if share_l3 is None else bool(share_l3))
        with self.conn:
            self.conn.execute("UPDATE episode_artifacts SET share_l2=?, share_l3=? WHERE id=?", (l2, l3, link_id))
        return {"id": link_id, "share_l2": bool(l2), "share_l3": bool(l3)}

    def get_artifact_bytes(self, digest: str) -> tuple[str, bytes]:
        row = self.conn.execute("SELECT media_type, data FROM artifacts WHERE sha256 = ?", (digest,)).fetchone()
        if not row:
            raise KeyError(f"Unknown artifact sha256: {digest}")
        return row["media_type"], bytes(row["data"])

    def _list_episode_artifacts(self, episode_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT ea.id, ea.episode_id, ea.artifact_sha256, ea.title, ea.caption,
                      ea.share_l2, ea.share_l3, a.media_type, a.size_bytes
               FROM episode_artifacts ea
               JOIN artifacts a ON a.sha256 = ea.artifact_sha256
               WHERE ea.episode_id = ?
               ORDER BY ea.created_at ASC""",
            (episode_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "sha256": r["artifact_sha256"],
                "media_type": r["media_type"],
                "size_bytes": r["size_bytes"],
                "title": r["title"],
                "caption": r["caption"],
                "share_l2": bool(r["share_l2"]),
                "share_l3": bool(r["share_l3"]),
            }
            for r in rows
        ]

    # ── Automatic Quote Anchoring ────────────────────────────────────────────

    def anchor_quote(self, source_id: str, quote: str) -> dict[str, Any]:
        src = self.get_source(source_id)
        text = src["raw_text"]
        quote_clean = quote.strip()
        if not quote_clean:
            raise ValueError("Quote cannot be empty")
        idx = text.find(quote_clean)
        if idx == -1:
            idx = text.lower().find(quote_clean.lower())
        if idx == -1:
            raise ValueError(f"Quote not found verbatim in source '{source_id}': {quote_clean[:80]!r}")
        exact_quote = text[idx : idx + len(quote_clean)]
        return {
            "source_id": source_id,
            "source_sha256": src["content_sha256"],
            "start": idx,
            "end": idx + len(exact_quote),
            "quote": exact_quote,
        }

    # ── Fast External-Content FTS5 Search ────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        channel: str | None = None,
        limit: int = 12,
        include_episodes: bool = True,
    ) -> dict[str, Any]:
        fts_q = _fts_query(query)
        source_hits: list[dict[str, Any]] = []
        sql = """
            SELECT sc.source_id, s.channel, s.title,
                   snippet(chunks_fts, 0, '[', ']', '...', 24) AS snippet,
                   bm25(chunks_fts) AS score,
                   s.event_date, s.sensitivity, s.url
            FROM chunks_fts
            JOIN source_chunks sc ON sc.id = chunks_fts.rowid
            JOIN sources s ON s.id = sc.source_id
            WHERE chunks_fts MATCH ?
        """
        params: list[Any] = [fts_q]
        if channel:
            sql += " AND s.channel = ?"
            params.append(channel.lower())
        sql += " ORDER BY score LIMIT ?"
        params.append(limit * 3)
        seen_sources: set[str] = set()
        for r in self.conn.execute(sql, params):
            if r["source_id"] in seen_sources:
                continue
            seen_sources.add(r["source_id"])
            source_hits.append({
                "source_id": r["source_id"],
                "channel": r["channel"],
                "title": r["title"],
                "event_date": r["event_date"],
                "sensitivity": r["sensitivity"],
                "url": r["url"],
                "snippet": r["snippet"],
                "bm25": round(float(r["score"]), 4),
            })
            if len(source_hits) >= limit:
                break

        episode_hits: list[dict[str, Any]] = []
        if include_episodes:
            ep_sql = """
                SELECT f.episode_id, f.title,
                       snippet(episodes_fts, 2, '[', ']', '...', 24) AS snippet,
                       bm25(episodes_fts) AS score,
                       e.period_label, e.status, e.role_id
                FROM episodes_fts f
                JOIN episodes e ON e.id = f.episode_id
                WHERE episodes_fts MATCH ?
                ORDER BY score LIMIT ?
            """
            for r in self.conn.execute(ep_sql, (fts_q, limit)):
                episode_hits.append({
                    "episode_id": r["episode_id"],
                    "title": r["title"],
                    "period_label": r["period_label"],
                    "status": r["status"],
                    "role_id": r["role_id"],
                    "snippet": r["snippet"],
                    "bm25": round(float(r["score"]), 4),
                })

        return {
            "query": query,
            "method": "sqlite_fts5_bm25",
            "sources": source_hits,
            "episodes": episode_hits,
        }

    # ── Layer 1: Roles, Episodes, Claims ─────────────────────────────────────

    def upsert_role(
        self,
        *,
        role_id: str | None = None,
        title: str,
        organization: str = "",
        start_date: str = "",
        end_date: str = "",
        period_label: str = "",
        is_current: bool = False,
        summary_l1: str = "",
        source_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        rid = role_id or slugify(f"{organization}-{title}", "role")
        refs = self._validate_source_refs(source_refs or [])
        ts = now_iso()
        label = period_label or self._format_period(start_date, end_date, is_current)
        with self.conn:
            self.conn.execute(
                """INSERT INTO roles(id, title, organization, start_date, end_date, period_label,
                                     is_current, summary_l1, source_refs_json, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, organization=excluded.organization,
                     start_date=excluded.start_date, end_date=excluded.end_date,
                     period_label=excluded.period_label, is_current=excluded.is_current,
                     summary_l1=excluded.summary_l1, source_refs_json=excluded.source_refs_json,
                     updated_at=excluded.updated_at""",
                (rid, title.strip(), organization.strip(), start_date.strip(), end_date.strip(),
                 label, int(bool(is_current)), summary_l1.strip(), json.dumps(refs), ts),
            )
            self._log("upsert_role", {"role_id": rid})
        return self.get_role(rid)

    def get_role(self, role_id: str) -> dict[str, Any]:
        r = self.conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        if not r:
            raise KeyError(f"Unknown role_id: {role_id}")
        return {
            "id": r["id"],
            "title": r["title"],
            "organization": r["organization"],
            "start_date": r["start_date"],
            "end_date": r["end_date"],
            "period_label": r["period_label"],
            "is_current": bool(r["is_current"]),
            "summary_l1": r["summary_l1"],
            "source_refs": json.loads(r["source_refs_json"]),
            "updated_at": r["updated_at"],
        }

    def list_roles(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM roles ORDER BY is_current DESC, start_date DESC, title ASC"
        ).fetchall()
        return [self.get_role(r["id"]) for r in rows]

    def delete_role(self, role_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            self._log("delete_role", {"role_id": role_id})
        return cur.rowcount > 0

    def delete_source(self, source_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            self._log("delete_source", {"source_id": source_id})
        return cur.rowcount > 0

    def delete_episode(self, episode_id: str) -> bool:
        with self.conn:
            self.conn.execute("DELETE FROM episodes_fts WHERE episode_id = ?", (episode_id,))
            cur = self.conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
            self._log("delete_episode", {"episode_id": episode_id})
        return cur.rowcount > 0

    def delete_claim(self, claim_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM claims WHERE id = ?", (claim_id,))
            self._log("delete_claim", {"claim_id": claim_id})
        return cur.rowcount > 0

    def unlink_source_from_episode(self, episode_id: str, source_id: str) -> dict[str, Any]:
        ep = self.get_episode(episode_id)
        remaining = [sid for sid in ep["source_refs"] if sid != source_id]
        return self.upsert_episode(
            episode_id=ep["id"], role_id=ep["role_id"], title=ep["title"], summary_l1=ep["summary_l1"],
            start_date=ep["start_date"], end_date=ep["end_date"], period_label=ep["period_label"],
            status=ep["status"], context_l1=ep["context_l1"], contribution_l1=ep["contribution_l1"],
            decisions=ep["decisions"], shared_credit_l1=ep["shared_credit_l1"], outcome_l1=ep["outcome_l1"],
            limits=ep["limits"], questions=ep["questions"], tags=ep["tags"],
            capabilities=ep["capabilities"], source_refs=remaining,
            review_status=ep["review_status"], importance=ep["importance"],
        )

    def upsert_episode(
        self,
        *,
        episode_id: str | None = None,
        title: str,
        summary_l1: str,
        role_id: str | None = None,
        start_date: str = "",
        end_date: str = "",
        period_label: str = "",
        status: str = "shipped",
        context_l1: str = "",
        contribution_l1: str = "",
        decisions: list[str] | None = None,
        shared_credit_l1: str = "",
        outcome_l1: str = "",
        limits: list[str] | None = None,
        questions: list[str] | None = None,
        tags: list[str] | None = None,
        capabilities: list[dict[str, Any]] | None = None,
        source_refs: list[str] | None = None,
        review_status: str = "draft",
        importance: int = 0,
    ) -> dict[str, Any]:
        eid = episode_id or slugify(title, "episode")
        refs = self._validate_source_refs(source_refs or [])
        if role_id:
            self.get_role(role_id)
        label = period_label or self._format_period(start_date, end_date, status == "ongoing")
        decisions_l = [d.strip() for d in (decisions or []) if d.strip()]
        limits_l = [x.strip() for x in (limits or []) if x.strip()]
        questions_l = [q.strip() for q in (questions or []) if q.strip()]
        tags_l = [t.strip().lower() for t in (tags or []) if t.strip()]
        caps_l = capabilities or []
        content_payload = {
            "title": title.strip(),
            "summary_l1": summary_l1.strip(),
            "context_l1": context_l1.strip(),
            "contribution_l1": contribution_l1.strip(),
            "decisions": decisions_l,
            "shared_credit_l1": shared_credit_l1.strip(),
            "outcome_l1": outcome_l1.strip(),
            "limits": limits_l,
            "source_refs": sorted(refs),
        }
        c_hash = canonical_hash(content_payload)
        ts = now_iso()

        with self.conn:
            self.conn.execute(
                """INSERT INTO episodes(
                     id, role_id, title, start_date, end_date, period_label, status,
                     summary_l1, context_l1, contribution_l1, decisions_json, shared_credit_l1,
                     outcome_l1, limits_json, questions_json, tags_json, capabilities_json,
                     source_refs_json, review_status, importance, content_sha256, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     role_id=excluded.role_id, title=excluded.title,
                     start_date=excluded.start_date, end_date=excluded.end_date,
                     period_label=excluded.period_label, status=excluded.status,
                     summary_l1=excluded.summary_l1, context_l1=excluded.context_l1,
                     contribution_l1=excluded.contribution_l1, decisions_json=excluded.decisions_json,
                     shared_credit_l1=excluded.shared_credit_l1, outcome_l1=excluded.outcome_l1,
                     limits_json=excluded.limits_json, questions_json=excluded.questions_json,
                     tags_json=excluded.tags_json, capabilities_json=excluded.capabilities_json,
                     source_refs_json=excluded.source_refs_json, review_status=excluded.review_status,
                     importance=excluded.importance, content_sha256=excluded.content_sha256,
                     updated_at=excluded.updated_at""",
                (eid, role_id, title.strip(), start_date.strip(), end_date.strip(), label, status.strip(),
                 summary_l1.strip(), context_l1.strip(), contribution_l1.strip(),
                 json.dumps(decisions_l, ensure_ascii=False), shared_credit_l1.strip(),
                 outcome_l1.strip(), json.dumps(limits_l, ensure_ascii=False),
                 json.dumps(questions_l, ensure_ascii=False), json.dumps(tags_l, ensure_ascii=False),
                 json.dumps(caps_l, ensure_ascii=False), json.dumps(refs), review_status,
                 int(importance), c_hash, ts),
            )
            self.conn.execute("DELETE FROM episodes_fts WHERE episode_id = ?", (eid,))
            self.conn.execute(
                "INSERT INTO episodes_fts(episode_id, title, summary_l1, decisions, outcome_l1, tags) VALUES (?,?,?,?,?,?)",
                (eid, title.strip(), f"{summary_l1} {context_l1} {contribution_l1}",
                 " ".join(decisions_l), outcome_l1.strip(), " ".join(tags_l)),
            )
            self._log("upsert_episode", {"episode_id": eid, "content_sha256": c_hash})
        return self.get_episode(eid)

    def get_episode(self, episode_id: str) -> dict[str, Any]:
        r = self.conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not r:
            raise KeyError(f"Unknown episode_id: {episode_id}")
        tiers = self._get_episode_tiers(r["id"], r["content_sha256"])
        claims = self.list_claims(episode_id=r["id"])
        artifacts = self._list_episode_artifacts(r["id"])
        return {
            "id": r["id"],
            "role_id": r["role_id"],
            "title": r["title"],
            "start_date": r["start_date"],
            "end_date": r["end_date"],
            "period_label": r["period_label"],
            "status": r["status"],
            "summary_l1": r["summary_l1"],
            "context_l1": r["context_l1"],
            "contribution_l1": r["contribution_l1"],
            "decisions": json.loads(r["decisions_json"]),
            "shared_credit_l1": r["shared_credit_l1"],
            "outcome_l1": r["outcome_l1"],
            "limits": json.loads(r["limits_json"]),
            "questions": json.loads(r["questions_json"]),
            "tags": json.loads(r["tags_json"]),
            "capabilities": json.loads(r["capabilities_json"]),
            "source_refs": json.loads(r["source_refs_json"]),
            "review_status": r["review_status"],
            "importance": r["importance"],
            "content_sha256": r["content_sha256"],
            "updated_at": r["updated_at"],
            "tiers": tiers,
            "claims": claims,
            "artifacts": artifacts,
        }

    def list_episodes(self, *, role_id: str | None = None) -> list[dict[str, Any]]:
        if role_id:
            rows = self.conn.execute(
                "SELECT id FROM episodes WHERE role_id = ? ORDER BY start_date DESC, title ASC", (role_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id FROM episodes ORDER BY importance DESC, CASE WHEN start_date = '' THEN 1 ELSE 0 END, start_date DESC, title ASC"
            ).fetchall()
        return [self.get_episode(r["id"]) for r in rows]

    def upsert_claim(
        self,
        *,
        claim_id: str | None = None,
        statement: str,
        episode_id: str | None = None,
        kind: str = "fact",
        status: str = "candidate",
        actor: str = "",
        action_state: str = "unknown",
        rationale: str = "",
        next_question: str = "",
        evidence_quotes: list[dict[str, str]] | None = None,
        counter_quotes: list[dict[str, str]] | None = None,
        relations: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if kind not in VALID_CLAIM_KINDS:
            raise ValueError(f"Invalid claim kind: {kind}")
        if status not in VALID_CLAIM_STATUS:
            raise ValueError(f"Invalid claim status: {status}")
        if episode_id and not self.conn.execute("SELECT 1 FROM episodes WHERE id = ?", (episode_id,)).fetchone():
            raise KeyError(f"Unknown episode_id: {episode_id}")
        cid = claim_id or slugify(f"claim-{statement[:48]}", "claim")
        anchors = [self.anchor_quote(q["source_id"], q["quote"]) for q in (evidence_quotes or [])]
        counter_anchors = [self.anchor_quote(q["source_id"], q["quote"]) for q in (counter_quotes or [])]
        ts = now_iso()

        with self.conn:
            self.conn.execute(
                """INSERT INTO claims(
                     id, episode_id, statement, kind, status, actor, action_state,
                     rationale, next_question, anchors_json, counter_anchors_json, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     episode_id=excluded.episode_id, statement=excluded.statement,
                     kind=excluded.kind, status=excluded.status, actor=excluded.actor,
                     action_state=excluded.action_state, rationale=excluded.rationale,
                     next_question=excluded.next_question, anchors_json=excluded.anchors_json,
                     counter_anchors_json=excluded.counter_anchors_json, updated_at=excluded.updated_at""",
                (cid, episode_id, statement.strip(), kind, status, actor.strip(), action_state.strip(),
                 rationale.strip(), next_question.strip(),
                 json.dumps(anchors, ensure_ascii=False),
                 json.dumps(counter_anchors, ensure_ascii=False), ts),
            )
            if relations is not None:
                self.conn.execute("DELETE FROM claim_relations WHERE from_claim_id = ?", (cid,))
                for rel in relations:
                    rtype = rel["type"]
                    if rtype not in VALID_RELATIONS:
                        raise ValueError(f"Invalid relation type: {rtype}")
                    self.conn.execute(
                        "INSERT OR IGNORE INTO claim_relations(from_claim_id, to_claim_id, relation_type) VALUES (?,?,?)",
                        (cid, rel["claim_id"], rtype),
                    )
            self._log("upsert_claim", {"claim_id": cid, "kind": kind, "status": status})
        return self.get_claim(cid)

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        r = self.conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not r:
            raise KeyError(f"Unknown claim_id: {claim_id}")
        rels = [
            {"claim_id": x["to_claim_id"], "type": x["relation_type"]}
            for x in self.conn.execute("SELECT to_claim_id, relation_type FROM claim_relations WHERE from_claim_id = ?", (claim_id,))
        ]
        return {
            "id": r["id"],
            "episode_id": r["episode_id"],
            "statement": r["statement"],
            "kind": r["kind"],
            "status": r["status"],
            "actor": r["actor"],
            "action_state": r["action_state"],
            "rationale": r["rationale"],
            "next_question": r["next_question"],
            "anchors": json.loads(r["anchors_json"]),
            "counter_anchors": json.loads(r["counter_anchors_json"]),
            "relations": rels,
            "updated_at": r["updated_at"],
        }

    def list_claims(self, *, episode_id: str | None = None) -> list[dict[str, Any]]:
        if episode_id is not None:
            rows = self.conn.execute("SELECT id FROM claims WHERE episode_id = ? ORDER BY id", (episode_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT id FROM claims ORDER BY id").fetchall()
        return [self.get_claim(r["id"]) for r in rows]

    # ── Layer 2 & 3: Sensitivity Registry, Entity Suggester & Leak Scanner ───

    def add_sensitive_term(
        self,
        term: str,
        *,
        replacement: str = "[redacted]",
        category: str = "other",
        case_sensitive: bool = False,
        notes: str = "",
    ) -> dict[str, Any]:
        term = term.strip()
        if not term:
            raise ValueError("Sensitive term cannot be empty")
        if category not in VALID_SENSITIVITY_CATEGORIES:
            category = "other"
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """INSERT INTO sensitive_terms(term, replacement, category, case_sensitive, notes, created_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(term) DO UPDATE SET
                     replacement=excluded.replacement, category=excluded.category,
                     case_sensitive=excluded.case_sensitive, notes=excluded.notes""",
                (term, replacement.strip() or "[redacted]", category, int(bool(case_sensitive)), notes.strip(), ts),
            )
            self._log("add_sensitive_term", {"category": category})
        row = self.conn.execute("SELECT * FROM sensitive_terms WHERE term = ?", (term,)).fetchone()
        return dict(row)

    def remove_sensitive_term(self, term_or_id: str | int) -> bool:
        with self.conn:
            if isinstance(term_or_id, int) or str(term_or_id).isdigit():
                cur = self.conn.execute("DELETE FROM sensitive_terms WHERE id = ?", (int(term_or_id),))
            else:
                cur = self.conn.execute("DELETE FROM sensitive_terms WHERE term = ?", (str(term_or_id),))
        return cur.rowcount > 0

    def list_sensitive_terms(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM sensitive_terms ORDER BY length(term) DESC, term ASC").fetchall()
        return [
            {
                "id": r["id"],
                "term": r["term"],
                "replacement": r["replacement"],
                "category": r["category"],
                "case_sensitive": bool(r["case_sensitive"]),
                "notes": r["notes"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def suggest_sensitive_terms(self, *, limit: int = 30) -> list[dict[str, Any]]:
        """Scan L1 episodes for unregistered proper nouns, currency figures, and confidential candidates."""
        existing = {t["term"].lower() for t in self.list_sensitive_terms()}
        person_name = (self.get_person().get("name") or "").strip().lower()
        name_parts = set(person_name.split())

        candidates: Counter[tuple[str, str]] = Counter()
        episodes_seen: dict[str, set[str]] = {}
        lowercase_words: set[str] = set()

        currency_re = re.compile(r"(?:[$£€]\s?\d[\d,]*(?:\.\d+)?(?:\s?[kKmMbB])?)")
        multi_proper_re = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){1,2})\b")
        mid_proper_re = re.compile(r"(?<=[a-z,;(\s]\s)([A-Z][a-zA-Z0-9]{2,}(?:-[A-Z][a-zA-Z0-9]+)?)")
        handle_re = re.compile(r"(?:@[a-zA-Z0-9_]{3,}|#[a-z][a-z0-9_-]{2,})")

        episodes = self.list_episodes()
        for ep in episodes:
            blob = "\n".join([
                ep["title"], ep["summary_l1"], ep["context_l1"], ep["contribution_l1"],
                ep["shared_credit_l1"], ep["outcome_l1"], *ep["decisions"], *ep["limits"],
            ])
            lowercase_words.update(re.findall(r"\b[a-z]{3,}\b", blob))

        for ep in episodes:
            eid = ep["id"]
            text = "\n".join([
                ep["title"], ep["summary_l1"], ep["context_l1"], ep["contribution_l1"],
                ep["shared_credit_l1"], ep["outcome_l1"], *ep["decisions"], *ep["limits"],
            ])
            for m in currency_re.findall(text):
                term = m.strip()
                if term.lower() not in existing:
                    candidates[(term, "metric")] += 1
                    episodes_seen.setdefault(term, set()).add(eid)
            for m in handle_re.findall(text):
                term = m.strip()
                if term.lower() not in existing:
                    candidates[(term, "internal_id")] += 1
                    episodes_seen.setdefault(term, set()).add(eid)
            for m in multi_proper_re.findall(text):
                words = m.split()
                if all(w in COMMON_CAP_WORDS or w.lower() in lowercase_words for w in words):
                    continue
                if m.lower() == person_name or m.lower() in existing:
                    continue
                candidates[(m, "customer")] += 1
                episodes_seen.setdefault(m, set()).add(eid)
            for m in mid_proper_re.findall(text):
                if m in COMMON_CAP_WORDS or m.lower() in lowercase_words or m.lower() in name_parts or m.lower() in existing:
                    continue
                candidates[(m, "customer")] += 1
                episodes_seen.setdefault(m, set()).add(eid)

        default_repl = {
            "metric": "an undisclosed figure",
            "internal_id": "[internal reference]",
            "customer": "a partner organization",
            "person": "a colleague",
        }
        ranked = sorted(
            candidates.items(),
            key=lambda kv: (len(episodes_seen.get(kv[0][0], set())), kv[1], len(kv[0][0])),
            reverse=True,
        )
        out: list[dict[str, Any]] = []
        seen_lower: set[str] = set()
        for (term, cat), count in ranked:
            if term.lower() in seen_lower:
                continue
            seen_lower.add(term.lower())
            eps = sorted(episodes_seen.get(term, set()))
            out.append({
                "term": term,
                "category": cat,
                "suggested_replacement": default_repl.get(cat, "[redacted]"),
                "occurrences": count,
                "episode_count": len(eps),
                "episodes": eps[:6],
            })
            if len(out) >= limit:
                break
        return out

    def scan_leaks(self, text: str, *, include_heuristics: bool = True) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        if not text:
            return findings
        for item in self.list_sensitive_terms():
            flags = 0 if item["case_sensitive"] else re.IGNORECASE
            escaped = re.escape(item["term"])
            prefix = r"\b" if re.match(r"^\w", item["term"]) else ""
            suffix = r"\b" if re.search(r"\w$", item["term"]) else ""
            pat = re.compile(f"{prefix}{escaped}{suffix}", flags)
            for m in pat.finditer(text):
                findings.append({
                    "kind": "sensitive_term",
                    "category": item["category"],
                    "matched": m.group(0),
                    "term": item["term"],
                    "suggested_replacement": item["replacement"],
                    "start": m.start(),
                    "end": m.end(),
                })
        if include_heuristics:
            for name, pat in BUILTIN_LEAK_PATTERNS:
                for m in pat.finditer(text):
                    findings.append({
                        "kind": "heuristic",
                        "category": name,
                        "matched": m.group(0).strip(),
                        "term": name,
                        "suggested_replacement": f"[remove {name}]",
                        "start": m.start(),
                        "end": m.end(),
                    })
        return findings

    def draft_sanitized_projection(self, episode_id: str, tier: str = "L2") -> dict[str, Any]:
        if tier not in SHAREABLE_TIERS:
            raise ValueError("Sanitized drafts are for L2 or L3")
        ep = self.get_episode(episode_id)
        terms = self.list_sensitive_terms()

        def scrub(text: str) -> str:
            out = text
            for item in terms:
                flags = 0 if item["case_sensitive"] else re.IGNORECASE
                escaped = re.escape(item["term"])
                prefix = r"\b" if re.match(r"^\w", item["term"]) else ""
                suffix = r"\b" if re.search(r"\w$", item["term"]) else ""
                out = re.sub(f"{prefix}{escaped}{suffix}", item["replacement"], out, flags=flags)
            return out

        public_links = []
        for sid in ep["source_refs"]:
            try:
                src = self.get_source(sid)
                if src["url"].startswith("https://") and src["sensitivity"] in ("L2", "L3"):
                    public_links.append({"label": src["title"], "url": src["url"]})
            except KeyError:
                pass

        summary = scrub(ep["summary_l1"])
        if tier == "L3" and len(summary) > 260:
            sents = re.split(r"(?<=[.!?])\s+", summary)
            summary = " ".join(sents[:2])

        return {
            "episode_id": episode_id,
            "tier": tier,
            "title": scrub(ep["title"]),
            "summary": summary,
            "decisions": [scrub(d) for d in ep["decisions"]] if tier == "L2" else [],
            "outcome": scrub(ep["outcome_l1"]),
            "shared_credit": scrub(ep["shared_credit_l1"]) if tier == "L2" else "",
            "public_links": public_links,
            "remaining_leaks": self.scan_leaks(f"{scrub(ep['title'])}\n{summary}\n{scrub(ep['outcome_l1'])}"),
        }

    def set_tier_projection(
        self,
        *,
        episode_id: str,
        tier: str,
        title: str,
        summary: str,
        decisions: list[str] | None = None,
        outcome: str = "",
        shared_credit: str = "",
        public_links: list[dict[str, str]] | None = None,
        approved: bool = False,
        allow_leaks: bool = False,
    ) -> dict[str, Any]:
        if tier not in SHAREABLE_TIERS:
            raise ValueError(f"Tier must be L2 or L3, got {tier}")
        ep = self.get_episode(episode_id)
        decisions_l = [d.strip() for d in (decisions or []) if d.strip()]
        links_l = public_links or []
        combined = "\n".join([title, summary, outcome, shared_credit, *decisions_l,
                              *(f"{l.get('label','')} {l.get('url','')}" for l in links_l)])
        leaks = self.scan_leaks(combined)
        if leaks and not allow_leaks:
            matched = sorted({f["matched"] for f in leaks})
            raise ValueError(
                f"Blocked saving {tier} projection for '{episode_id}': detected confidential/sensitive leaks: {matched}"
            )
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """INSERT INTO tier_projections(
                     episode_id, tier, title, summary, decisions_json, outcome,
                     shared_credit, public_links_json, approved, derived_from_sha256, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(episode_id, tier) DO UPDATE SET
                     title=excluded.title, summary=excluded.summary,
                     decisions_json=excluded.decisions_json, outcome=excluded.outcome,
                     shared_credit=excluded.shared_credit, public_links_json=excluded.public_links_json,
                     approved=excluded.approved, derived_from_sha256=excluded.derived_from_sha256,
                     updated_at=excluded.updated_at""",
                (episode_id, tier, title.strip(), summary.strip(),
                 json.dumps(decisions_l, ensure_ascii=False), outcome.strip(),
                 shared_credit.strip(), json.dumps(links_l, ensure_ascii=False),
                 int(bool(approved)), ep["content_sha256"], ts),
            )
            self._log("set_tier_projection", {"episode_id": episode_id, "tier": tier, "approved": approved})
        return self._get_episode_tiers(episode_id, ep["content_sha256"])[tier]

    def _get_episode_tiers(self, episode_id: str, current_sha: str) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tier_projections WHERE episode_id = ?", (episode_id,)
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            decisions = json.loads(r["decisions_json"])
            links = json.loads(r["public_links_json"])
            combined = "\n".join([r["title"], r["summary"], r["outcome"], r["shared_credit"], *decisions])
            leaks = self.scan_leaks(combined)
            out[r["tier"]] = {
                "episode_id": r["episode_id"],
                "tier": r["tier"],
                "title": r["title"],
                "summary": r["summary"],
                "decisions": decisions,
                "outcome": r["outcome"],
                "shared_credit": r["shared_credit"],
                "public_links": links,
                "approved": bool(r["approved"]),
                "derived_from_sha256": r["derived_from_sha256"],
                "stale": r["derived_from_sha256"] != current_sha,
                "leaks": leaks,
                "updated_at": r["updated_at"],
            }
        return out

    def audit_tier_leaks(self, tier: str = "L2") -> dict[str, Any]:
        if tier not in SHAREABLE_TIERS:
            raise ValueError("Leak audit applies to L2 or L3")
        person = self.get_person()
        overview_key = "overview_l2" if tier == "L2" else "overview_l3"
        overview_leaks = self.scan_leaks(person.get(overview_key, ""))
        episode_issues = []
        missing_projections = []
        stale_projections = []
        for ep in self.list_episodes():
            proj = ep["tiers"].get(tier)
            if not proj:
                missing_projections.append(ep["id"])
                continue
            if proj["stale"]:
                stale_projections.append(ep["id"])
            if proj["leaks"]:
                episode_issues.append({"episode_id": ep["id"], "leaks": proj["leaks"]})
        return {
            "tier": tier,
            "clean": not overview_leaks and not episode_issues,
            "overview_leaks": overview_leaks,
            "episode_leaks": episode_issues,
            "stale_projections": stale_projections,
            "missing_projections": missing_projections,
        }

    # ── Dynamic Timeline & Status Briefing ───────────────────────────────────

    def get_timeline(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        roles_by_id = {r["id"]: r for r in self.list_roles()}

        for r in roles_by_id.values():
            events.append({
                "kind": "role",
                "id": r["id"],
                "sort_date": r["start_date"] or "0000",
                "period": r["period_label"] or r["start_date"] or "Undated",
                "title": f"{r['title']} — {r['organization']}" if r["organization"] else r["title"],
                "summary": r["summary_l1"],
                "current": r["is_current"],
            })

        for ep in self.list_episodes():
            role = roles_by_id.get(ep["role_id"] or "")
            events.append({
                "kind": "episode",
                "id": ep["id"],
                "role_id": ep["role_id"],
                "role_label": f"{role['title']} @ {role['organization']}" if role else "",
                "sort_date": ep["start_date"] or (role["start_date"] if role else "0000"),
                "period": ep["period_label"] or ep["start_date"] or "Undated",
                "status": ep["status"],
                "title": ep["title"],
                "summary": ep["summary_l1"],
                "tags": ep["tags"],
                "tiers_available": sorted(ep["tiers"].keys()),
                "source_count": len(ep["source_refs"]),
                "artifact_count": len(ep["artifacts"]),
            })

        for s in self.list_sources(unlinked_only=True, limit=200):
            events.append({
                "kind": "unlinked_source",
                "id": s["id"],
                "channel": s["channel"],
                "sort_date": s["event_date"] or s["captured_at"][:10],
                "period": s["event_date"] or f"Captured {s['captured_at'][:10]}",
                "title": s["title"],
                "summary": s["preview"],
            })

        events.sort(key=lambda e: (e["sort_date"], e["kind"]), reverse=True)
        return events

    def link_sources_to_episode(self, episode_id: str, source_ids: list[str]) -> dict[str, Any]:
        """Attach one or more L0 vault sources to an existing L1 episode."""
        ep = self.get_episode(episode_id)
        merged = list(dict.fromkeys([*ep["source_refs"], *source_ids]))
        return self.upsert_episode(
            episode_id=ep["id"],
            role_id=ep["role_id"],
            title=ep["title"],
            summary_l1=ep["summary_l1"],
            start_date=ep["start_date"],
            end_date=ep["end_date"],
            period_label=ep["period_label"],
            status=ep["status"],
            context_l1=ep["context_l1"],
            contribution_l1=ep["contribution_l1"],
            decisions=ep["decisions"],
            shared_credit_l1=ep["shared_credit_l1"],
            outcome_l1=ep["outcome_l1"],
            limits=ep["limits"],
            questions=ep["questions"],
            tags=ep["tags"],
            capabilities=ep["capabilities"],
            source_refs=merged,
            review_status=ep["review_status"],
            importance=ep["importance"],
        )

    def get_knowledge_graph(self) -> dict[str, Any]:
        """Aggregate capabilities, tools, recurring themes, and decision patterns across episodes."""
        episodes = self.list_episodes()
        cap_map: dict[str, dict[str, Any]] = {}
        tag_map: dict[str, list[dict[str, str]]] = {}
        decisions_index: list[dict[str, Any]] = []

        for ep in episodes:
            for cap in ep.get("capabilities") or []:
                name = (cap.get("name") or "").strip()
                if not name:
                    continue
                key = name.lower()
                entry = cap_map.setdefault(key, {
                    "name": name,
                    "kind": cap.get("kind", "practice"),
                    "episodes": [],
                    "applications": [],
                })
                entry["episodes"].append({"id": ep["id"], "title": ep["title"], "period": ep["period_label"]})
                if cap.get("application"):
                    entry["applications"].append(cap["application"])
            for tag in ep.get("tags") or []:
                tag_map.setdefault(tag, []).append({"id": ep["id"], "title": ep["title"], "period": ep["period_label"]})
            for d in ep.get("decisions") or []:
                decisions_index.append({
                    "episode_id": ep["id"],
                    "episode_title": ep["title"],
                    "period": ep["period_label"],
                    "decision": d,
                })

        capabilities = sorted(cap_map.values(), key=lambda x: (-len(x["episodes"]), x["name"].lower()))
        themes = [
            {"tag": tag, "count": len(eps), "episodes": eps}
            for tag, eps in sorted(tag_map.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ]
        return {
            "capabilities": capabilities,
            "themes": themes,
            "decisions": decisions_index,
            "totals": {
                "capabilities": len(capabilities),
                "themes": len(themes),
                "decisions": len(decisions_index),
            },
        }

    def triage_unlinked_sources(self, *, limit: int = 80) -> dict[str, Any]:
        """Fast lexical triage of unlinked L0 sources into likely episode matches vs new-story clusters."""
        unlinked = self.list_sources(unlinked_only=True, limit=limit)
        episodes = self.list_episodes()
        attach_candidates: list[dict[str, Any]] = []
        orphan_clusters: dict[str, list[dict[str, Any]]] = {}

        ep_tokens: list[tuple[dict[str, Any], set[str]]] = []
        stop = {"this", "that", "with", "from", "into", "their", "about", "after", "before", "have", "been", "were", "they", "them", "when", "what", "which", "work", "team"}
        for ep in episodes:
            toks = {
                t for t in re.findall(r"[a-z0-9]{4,}", f"{ep['title']} {ep['summary_l1']} {' '.join(ep['tags'])}".lower())
                if t not in stop
            }
            ep_tokens.append((ep, toks))

        for s in unlinked:
            s_toks = {
                t for t in re.findall(r"[a-z0-9]{4,}", f"{s['title']} {s['preview']}".lower())
                if t not in stop
            }
            best_ep = None
            best_overlap = 0
            for ep, toks in ep_tokens:
                ov = len(s_toks & toks)
                if ov > best_overlap:
                    best_overlap = ov
                    best_ep = ep
            if best_ep and best_overlap >= 4:
                attach_candidates.append({
                    "source_id": s["id"],
                    "channel": s["channel"],
                    "title": s["title"],
                    "event_date": s["event_date"],
                    "suggested_episode_id": best_ep["id"],
                    "suggested_episode_title": best_ep["title"],
                    "score": best_overlap,
                    "method": "lexical_overlap",
                })
            else:
                ym = (s["event_date"] or "undated")[:7]
                cluster_key = f"{s['channel']} · {ym}"
                orphan_clusters.setdefault(cluster_key, []).append({
                    "source_id": s["id"],
                    "channel": s["channel"],
                    "title": s["title"],
                    "event_date": s["event_date"],
                    "preview": s["preview"][:140],
                })

        attach_candidates.sort(key=lambda x: x["score"], reverse=True)
        clusters_list = [
            {"cluster": k, "count": len(v), "sources": v[:8]}
            for k, v in sorted(orphan_clusters.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ]
        return {
            "method": "lexical_triage",
            "unlinked_examined": len(unlinked),
            "attach_candidates": attach_candidates,
            "potential_new_clusters": clusters_list,
        }

    def get_status(self) -> dict[str, Any]:
        person = self.get_person()
        sources = self.list_sources(limit=1000)
        unlinked = [s for s in sources if not s["linked"]]
        episodes = self.list_episodes()
        roles = self.list_roles()
        claims = self.list_claims()
        artifact_count = self.conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        contradictions = [
            c for c in claims
            if c["status"] in ("disputed", "rejected")
            or any(r["type"] == "contradicts" for r in c["relations"])
        ]
        open_questions = [
            {"episode_id": ep["id"], "question": q}
            for ep in episodes for q in ep["questions"]
        ]
        by_channel: dict[str, int] = {}
        for s in sources:
            by_channel[s["channel"]] = by_channel.get(s["channel"], 0) + 1

        l2_audit = self.audit_tier_leaks("L2")
        l3_audit = self.audit_tier_leaks("L3")

        return {
            "schema": "career-vault/v2",
            "database": str(self.path),
            "person": {
                "name": person["name"],
                "headline": person["headline"],
                "goal": person["goal"],
            },
            "counts": {
                "sources": len(sources),
                "unlinked_sources": len(unlinked),
                "roles": len(roles),
                "episodes": len(episodes),
                "artifacts": artifact_count,
                "claims": len(claims),
                "contradictions": len(contradictions),
                "sensitive_terms": len(self.list_sensitive_terms()),
                "open_questions": len(open_questions),
            },
            "channels": by_channel,
            "unlinked_inbox": [{"id": s["id"], "channel": s["channel"], "title": s["title"], "event_date": s["event_date"]} for s in unlinked[:20]],
            "open_questions": open_questions[:20],
            "granularity": {
                "L2": {
                    "ready": len(episodes) - len(l2_audit["missing_projections"]),
                    "total": len(episodes),
                    "stale": l2_audit["stale_projections"],
                    "leaks": len(l2_audit["episode_leaks"]) + len(l2_audit["overview_leaks"]),
                },
                "L3": {
                    "ready": len(episodes) - len(l3_audit["missing_projections"]),
                    "total": len(episodes),
                    "stale": l3_audit["stale_projections"],
                    "leaks": len(l3_audit["episode_leaks"]) + len(l3_audit["overview_leaks"]),
                },
            },
        }

    # ── Channel & MCP Scan Ledger ────────────────────────────────────────────

    def _ensure_channel_scans_table(self) -> None:
        if self.readonly:
            return
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS channel_scans (
                channel TEXT PRIMARY KEY,
                label TEXT NOT NULL DEFAULT '',
                access_method TEXT NOT NULL DEFAULT 'mcp',
                status TEXT NOT NULL DEFAULT 'declared',
                date_range_covered TEXT NOT NULL DEFAULT '',
                queries_run_json TEXT NOT NULL DEFAULT '[]',
                items_ingested INTEGER NOT NULL DEFAULT 0,
                remaining_notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )"""
        )

    def upsert_channel_scan(
        self,
        *,
        channel: str,
        label: str = "",
        access_method: str = "mcp",
        status: str = "declared",
        date_range_covered: str = "",
        queries_run: list[str] | None = None,
        items_ingested: int | None = None,
        remaining_notes: str = "",
    ) -> dict[str, Any]:
        """Record a work/communication channel and its MCP or export scan progress."""
        if self.readonly:
            raise PermissionError("Cannot update channel_scans on a read-only vault")
        ch = channel.strip().lower()
        if not ch:
            raise ValueError("channel is required")
        if status not in ("declared", "scanning", "scanned", "skipped"):
            raise ValueError("status must be one of: declared, scanning, scanned, skipped")
        if access_method not in ("mcp", "connector", "export", "manual"):
            raise ValueError("access_method must be one of: mcp, connector, export, manual")
        self._ensure_channel_scans_table()
        existing = self.conn.execute("SELECT * FROM channel_scans WHERE channel = ?", (ch,)).fetchone()
        prev_queries = json.loads(existing["queries_run_json"]) if existing else []
        merged_queries = list(dict.fromkeys([*prev_queries, *(q.strip() for q in (queries_run or []) if q.strip())]))
        if items_ingested is None:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM sources WHERE channel = ?", (ch,)).fetchone()
            ingested = int(row["n"]) if row else 0
        else:
            ingested = int(items_ingested)
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """INSERT INTO channel_scans(
                     channel, label, access_method, status, date_range_covered,
                     queries_run_json, items_ingested, remaining_notes, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(channel) DO UPDATE SET
                     label=CASE WHEN excluded.label != '' THEN excluded.label ELSE channel_scans.label END,
                     access_method=excluded.access_method,
                     status=excluded.status,
                     date_range_covered=CASE WHEN excluded.date_range_covered != '' THEN excluded.date_range_covered ELSE channel_scans.date_range_covered END,
                     queries_run_json=excluded.queries_run_json,
                     items_ingested=excluded.items_ingested,
                     remaining_notes=excluded.remaining_notes,
                     updated_at=excluded.updated_at""",
                (ch, label.strip() or ch.title(), access_method, status, date_range_covered.strip(),
                 json.dumps(merged_queries, ensure_ascii=False), ingested, remaining_notes.strip(), ts),
            )
            self._log("upsert_channel_scan", {"channel": ch, "status": status, "items_ingested": ingested})
        return [c for c in self.list_channel_scans() if c["channel"] == ch][0]

    def list_channel_scans(self) -> list[dict[str, Any]]:
        has_tbl = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='channel_scans'"
        ).fetchone()
        if not has_tbl:
            return []
        counts = {
            r["channel"]: int(r["n"])
            for r in self.conn.execute("SELECT channel, COUNT(*) AS n FROM sources GROUP BY channel")
        }
        rows = self.conn.execute("SELECT * FROM channel_scans ORDER BY status ASC, channel ASC").fetchall()
        out = []
        for r in rows:
            out.append({
                "channel": r["channel"],
                "label": r["label"] or r["channel"].title(),
                "access_method": r["access_method"],
                "status": r["status"],
                "date_range_covered": r["date_range_covered"],
                "queries_run": json.loads(r["queries_run_json"]),
                "items_ingested": max(int(r["items_ingested"]), counts.get(r["channel"], 0)),
                "remaining_notes": r["remaining_notes"],
                "updated_at": r["updated_at"],
            })
        return out

    # ── Deterministic Deepening & Coverage Audit ("What Did I Miss?") ────────

    _LEGALESE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("selected record establishes", re.compile(r"\b(?:the\s+)?selected\s+record\s+(?:establishes|shows|reflects|indicates)\b", re.I)),
        ("does not constitute verification", re.compile(r"\bdoes\s+not\s+constitute\b", re.I)),
        ("not independently verified", re.compile(r"\bnot\s+independently\s+verified\b", re.I)),
        ("available record reflects", re.compile(r"\b(?:the\s+)?available\s+record\s+(?:reflects|shows|establishes|supports)\b", re.I)),
        ("cannot be verified from", re.compile(r"\bcannot\s+be\s+verified\s+from\b", re.I)),
        ("within the retained evidence", re.compile(r"\bwithin\s+the\s+(?:retained|preserved|selected)\s+(?:evidence|record|sources)\b", re.I)),
    ]

    def audit_gaps(self, *, max_examples: int = 8) -> dict[str, Any]:
        """Deterministically audit vault coverage, story depth, voice quality, and sharing gaps.

        Gives both humans and BYO-LLMs an objective 'What else have I missed?' checklist
        so the system drives iterative deepening automatically instead of stopping shallow.
        """
        roles = self.list_roles()
        episodes = self.list_episodes()
        sources = self.list_sources(limit=2000)
        sensitive_terms = self.list_sensitive_terms()
        l2_audit = self.audit_tier_leaks("L2")
        l3_audit = self.audit_tier_leaks("L3")

        # 1. Role & era coverage
        ep_by_role: dict[str, int] = {}
        unassigned_role_eps = 0
        for ep in episodes:
            rid = ep.get("role_id")
            if rid:
                ep_by_role[rid] = ep_by_role.get(rid, 0) + 1
            else:
                unassigned_role_eps += 1

        empty_roles = [
            {"id": r["id"], "title": r["title"], "organization": r["organization"], "period": r["period_label"]}
            for r in roles if ep_by_role.get(r["id"], 0) == 0
        ]

        # 2. Unlinked evidence blindspots
        unlinked_sources = [s for s in sources if not s["linked"]]
        substantive_unlinked = sorted(
            [s for s in unlinked_sources if int(s.get("chars") or 0) >= 1000],
            key=lambda x: int(x.get("chars") or 0),
            reverse=True,
        )
        triage = self.triage_unlinked_sources(limit=80) if unlinked_sources else {
            "attach_candidates": [], "potential_new_clusters": [], "unlinked_examined": 0
        }

        # 3. Per-episode depth audit
        thin_episodes: list[dict[str, Any]] = []
        for ep in episodes:
            missing: list[str] = []
            if not ep["decisions"]:
                missing.append("decisions")
            if not ep["outcome_l1"].strip():
                missing.append("outcome")
            if not ep["shared_credit_l1"].strip():
                missing.append("shared_credit")
            if not ep["claims"]:
                missing.append("anchored_claims")
            if len(ep["summary_l1"].strip()) < 200:
                missing.append("detailed_summary")
            if ep["importance"] >= 2 and len(ep["source_refs"]) < 2:
                missing.append("multi_source_evidence")
            if missing:
                thin_episodes.append({
                    "episode_id": ep["id"],
                    "title": ep["title"],
                    "importance": ep["importance"],
                    "missing": missing,
                })
        thin_episodes.sort(key=lambda x: (-x["importance"], -len(x["missing"])))

        # 4. Channel blindspots & MCP scan ledger
        channel_scans = self.list_channel_scans()
        unscanned_channels = [
            c for c in channel_scans
            if c["status"] in ("declared", "scanning")
        ]
        present_channels = {s["channel"] for s in sources}
        channel_groups = {
            "docs_or_resume": bool(present_channels & {"doc", "resume", "gdoc", "note"}),
            "slack_or_chat": bool(present_channels & {"slack", "chat", "teams", "discord"}),
            "notion_or_wiki": bool(present_channels & {"notion", "wiki", "confluence"}),
            "calendar_and_transcripts": bool(present_channels & {
                "calendar", "transcript", "transcripts", "meeting", "voice_note",
                "granola", "gong", "fireflies", "otter", "zoom",
            }),
            "github_or_code": bool(present_channels & {"github", "git", "linear", "jira"}),
            "email_or_slides": bool(present_channels & {"gmail", "email", "slides", "figma"}),
            "linkedin": bool(present_channels & {"linkedin"}),
            "public_writing": bool(present_channels & {"x", "substack", "blog", "youtube"}),
        }
        missing_channels = [k for k, ok in channel_groups.items() if not ok]

        # 5. Narrative hierarchy, legalese voice check & sensitive suggestions
        flagship_count = sum(1 for e in episodes if e["importance"] >= 3)
        hierarchy_issue = None
        if len(episodes) >= 4 and flagship_count == 0:
            hierarchy_issue = "No Flagship stories ranked yet (importance=3). Rank your top 3-6 career-defining arcs."
        elif flagship_count > 6:
            hierarchy_issue = f"{flagship_count} stories marked Flagship. Narrow to 4-6 so your strongest arcs stand out."

        legalese_hits: list[dict[str, Any]] = []
        for ep in episodes:
            for tier_name in ("L2", "L3"):
                proj = ep["tiers"].get(tier_name)
                if not proj:
                    continue
                blob = f"{proj.get('title', '')}\n{proj.get('summary', '')}\n{proj.get('outcome', '')}"
                matched_labels = [lbl for lbl, pat in self._LEGALESE_PATTERNS if pat.search(blob)]
                if matched_labels:
                    legalese_hits.append({
                        "episode_id": ep["id"],
                        "title": ep["title"],
                        "tier": tier_name,
                        "phrases": matched_labels,
                    })

        unregistered_sensitive = self.suggest_sensitive_terms(limit=8) if episodes else []

        # 6. Transparent 0-100 Depth Score across 4 pillars
        # Coverage (25): roles present + role coverage + source link ratio
        cov = 0
        if sources:
            cov += 6
            linked_ratio = (len(sources) - len(unlinked_sources)) / max(1, len(sources))
            cov += round(min(1.0, linked_ratio / 0.65) * 9)
        if roles:
            cov += 4
            role_cov = (len(roles) - len(empty_roles)) / max(1, len(roles))
            cov += round(role_cov * 6)
        cov = min(25, cov)

        # Story Depth (30): episodes exist + average completeness of decisions/outcome/credit/claims/length
        dep = 0
        if episodes:
            per_ep_scores = []
            for ep in episodes:
                pts = 0
                if len(ep["summary_l1"].strip()) >= 200:
                    pts += 25
                if ep["decisions"]:
                    pts += 25
                if ep["outcome_l1"].strip():
                    pts += 20
                if ep["shared_credit_l1"].strip():
                    pts += 15
                if ep["claims"]:
                    pts += 15
                per_ep_scores.append(pts)
            dep = round((sum(per_ep_scores) / len(per_ep_scores)) * 0.30)
        dep = min(30, dep)

        # Narrative & Voice (20): hierarchy ranked + zero legalese + channel breadth
        nar = 0
        if episodes and not hierarchy_issue:
            nar += 8
        elif episodes:
            nar += 3
        if not legalese_hits:
            nar += 7
        nar += round((sum(1 for ok in channel_groups.values() if ok) / len(channel_groups)) * 5)
        nar = min(20, nar)

        # Sharing Safety (25): L2/L3 coverage + 0 stale + 0 leaks + sensitive scan done
        shr = 0
        if episodes:
            l2_ratio = (len(episodes) - len(l2_audit["missing_projections"])) / len(episodes)
            l3_ratio = (len(episodes) - len(l3_audit["missing_projections"])) / len(episodes)
            shr += round(((l2_ratio + l3_ratio) / 2.0) * 12)
            if l2_audit["clean"] and l3_audit["clean"]:
                shr += 8
            if not l2_audit["stale_projections"] and not l3_audit["stale_projections"]:
                shr += 3
            if sensitive_terms or not unregistered_sensitive:
                shr += 2
        shr = min(25, shr)
        depth_score = min(100, cov + dep + nar + shr)

        # 7. Prioritized Next Actions (What's Missing?)
        next_actions: list[dict[str, Any]] = []
        if unscanned_channels:
            ch_desc = ", ".join(
                f"{c['label']} ({c['status']}{': ' + c['remaining_notes'] if c['remaining_notes'] else ''})"
                for c in unscanned_channels[:4]
            )
            next_actions.append({
                "id": "unscanned_channels",
                "severity": "high",
                "category": "coverage",
                "title": f"{len(unscanned_channels)} declared work channel(s) not fully scanned yet",
                "detail": f"Finish sweeping via your agent's MCP connectors: {ch_desc}.",
                "target_tab": "vault",
            })
        if not roles and sources:
            next_actions.append({
                "id": "add_roles",
                "severity": "high",
                "category": "coverage",
                "title": "Add your career roles to anchor the timeline",
                "detail": "You have saved sources, but 0 roles are recorded yet. Add your roles on the Experience tab or scan LinkedIn.",
                "target_tab": "experience",
            })
        if empty_roles:
            names = ", ".join(f"{r['title']} ({r['organization'] or r['period']})" for r in empty_roles[:3])
            next_actions.append({
                "id": "empty_roles",
                "severity": "high",
                "category": "coverage",
                "title": f"{len(empty_roles)} career role(s) have zero stories yet",
                "detail": f"Unexplored eras: {names}{'...' if len(empty_roles) > 3 else ''}. Mine docs/notes or interview yourself for 1-2 defining arcs per role.",
                "target_tab": "experience",
            })
        if substantive_unlinked:
            top_titles = "; ".join(s["title"] for s in substantive_unlinked[:3])
            next_actions.append({
                "id": "substantive_unlinked",
                "severity": "high",
                "category": "evidence",
                "title": f"{len(substantive_unlinked)} long unlinked source(s) (>=1k chars) sitting in inbox",
                "detail": f"Unmined material includes: {top_titles}. Run Inbox Triage to attach them or start new stories.",
                "target_tab": "vault",
            })
        if triage["potential_new_clusters"]:
            c_preview = ", ".join(c["cluster"] for c in triage["potential_new_clusters"][:3])
            next_actions.append({
                "id": "unwritten_clusters",
                "severity": "medium",
                "category": "evidence",
                "title": f"{len(triage['potential_new_clusters'])} unwritten source cluster(s) detected",
                "detail": f"Clustered evidence not yet turned into stories: {c_preview}.",
                "target_tab": "vault",
            })
        if thin_episodes:
            worst = thin_episodes[0]
            next_actions.append({
                "id": "thin_stories",
                "severity": "high" if any(t["importance"] >= 2 for t in thin_episodes) else "medium",
                "category": "depth",
                "title": f"{len(thin_episodes)} story/stories missing key depth fields",
                "detail": f"Top priority: '{worst['title']}' is missing {', '.join(worst['missing'])}.",
                "target_tab": "episodes",
                "episode_id": worst["episode_id"],
            })
        if hierarchy_issue:
            next_actions.append({
                "id": "rank_hierarchy",
                "severity": "medium",
                "category": "narrative",
                "title": "Rank your 4-6 Flagship stories",
                "detail": hierarchy_issue,
                "target_tab": "episodes",
            })
        if legalese_hits:
            first_leg = legalese_hits[0]
            next_actions.append({
                "id": "legalese_voice",
                "severity": "medium",
                "category": "narrative",
                "title": f"{len(legalese_hits)} L2/L3 projection(s) read like a legal brief",
                "detail": f"'{first_leg['title']}' ({first_leg['tier']}) uses {', '.join(first_leg['phrases'])}. Rewrite in confident human voice (Stakes -> Decision -> Result).",
                "target_tab": "sharing",
                "episode_id": first_leg["episode_id"],
            })
        if l2_audit["missing_projections"] or l2_audit["stale_projections"] or not l2_audit["clean"]:
            next_actions.append({
                "id": "l2_readiness",
                "severity": "high" if not l2_audit["clean"] else "medium",
                "category": "sharing",
                "title": "Finish & refresh confidential-safe L2 projections",
                "detail": (
                    f"{len(l2_audit['missing_projections'])} missing, "
                    f"{len(l2_audit['stale_projections'])} stale, "
                    f"{len(l2_audit['episode_leaks']) + len(l2_audit['overview_leaks'])} leak finding(s)."
                ),
                "target_tab": "sharing",
            })
        if unregistered_sensitive:
            cand = ", ".join(s["term"] for s in unregistered_sensitive[:4])
            next_actions.append({
                "id": "sensitive_scan",
                "severity": "medium",
                "category": "sharing",
                "title": f"{len(unregistered_sensitive)} potential sensitive term(s) unregistered",
                "detail": f"Review candidates in Sharing Studio: {cand}.",
                "target_tab": "sharing",
            })
        if missing_channels:
            next_actions.append({
                "id": "channel_blindspots",
                "severity": "low",
                "category": "coverage",
                "title": f"{len(missing_channels)} untapped career channel(s)",
                "detail": f"No sources ingested yet from: {', '.join(missing_channels)}. Adding code, chat, or public writing deepens signal.",
                "target_tab": "vault",
            })

        # Build ready-to-run Deepening Prompt for any BYO-LLM
        prompt_lines = [
            f"My Career Vault depth score is {depth_score}/100. Help me close the highest-signal gaps without inventing facts:",
        ]
        for act in next_actions[:5]:
            prompt_lines.append(f"- [{act['severity'].upper()}] {act['title']}: {act['detail']}")
        prompt_lines.append(
            "For each gap, tell me (1) what evidence already in my vault fills it, and (2) the 2-3 sharpest follow-up questions only I can answer."
        )

        # 8. Five-stage guided journey status
        l2_ready_count = len(episodes) - len(l2_audit["missing_projections"])
        l3_ready_count = len(episodes) - len(l3_audit["missing_projections"])
        s1_status = "done" if (sources and not unscanned_channels) else ("in_progress" if (sources or channel_scans) else "pending")
        s2_status = "done" if (roles and len(episodes) >= 3) else ("in_progress" if (roles or episodes) else "pending")
        s3_status = "done" if (episodes and depth_score >= 85 and not empty_roles and not unscanned_channels) else ("in_progress" if episodes else "pending")
        s4_status = "done" if (episodes and l2_ready_count == len(episodes) and l2_audit["clean"] and not legalese_hits and not hierarchy_issue) else ("in_progress" if (l2_ready_count > 0 or sensitive_terms) else "pending")
        s5_status = "done" if (s4_status == "done" and l3_ready_count > 0 and l3_audit["clean"]) else ("in_progress" if (l2_ready_count > 0 and l2_audit["clean"]) else "pending")

        def _pl(n: int, singular: str, plural: str | None = None) -> str:
            return f"{n} {singular if n == 1 else (plural or singular + 's')}"

        stages = [
            {
                "stage": 1,
                "id": "scan_channels",
                "short_title": "Scan Channels",
                "title": "Map and scan your work channels (L0)",
                "status": s1_status,
                "metric": f"{_pl(len(sources), 'source')} · {_pl(len(present_channels), 'active channel')}",
                "summary": "List every tool where your work lives—Slack, Notion, Calendar, meeting transcripts, Google Docs, GitHub, and public writing—then let your agent sweep authorized history via MCP into your local vault.",
                "why": "You cannot synthesize decisions or eras your assistant never saw. Tracking channels prevents shallow, one-off searches.",
                "cta": "Open Vault & Scan Ledger",
                "target_tab": "vault",
            },
            {
                "stage": 2,
                "id": "build_l1",
                "short_title": "Roles & Stories",
                "title": "Organize roles and private stories (L1)",
                "status": s2_status,
                "metric": f"{_pl(len(roles), 'role')} · {_pl(len(episodes), 'private story', 'private stories')}",
                "summary": "Build your full, candid career database: chronological roles, key decisions, shared credit, honest outcomes, screenshots, and verbatim evidence-anchored claims.",
                "why": "Keeping L1 strictly private means you never censor your own memory or lose early prototypes, nuances, and hard lessons.",
                "cta": "Open Roles & Experience",
                "target_tab": "experience",
            },
            {
                "stage": 3,
                "id": "deepen_gaps",
                "short_title": "Deepen Gaps",
                "title": "Close blindspots automatically",
                "status": s3_status,
                "metric": f"Depth {depth_score}/100 · {_pl(len(next_actions), 'open gap')}",
                "summary": "Run the deterministic Deepening Radar to catch unscanned MCP channels, roles with zero stories, long unlinked documents, and thin stories before stopping.",
                "why": "Replaces the tedious loop of repeatedly asking your AI 'what else did I miss?' with an objective coverage checklist.",
                "cta": "Inspect Deepening Radar",
                "target_tab": "studio",
            },
            {
                "stage": 4,
                "id": "polish_tiers",
                "short_title": "Polish Tiers",
                "title": "Rank Flagships and sanitize L2 / L3",
                "status": s4_status,
                "metric": f"{_pl(flagship_count, 'Flagship')} · {l2_ready_count}/{len(episodes)} L2 ready",
                "summary": "Register confidential names and metrics, highlight 4–6 career-defining Flagship stories, and rewrite honest records into crisp, human-voiced L2 and L3 narratives.",
                "why": "Separates private candor from confidential-safe storytelling—eliminating both accidental leaks and robotic legal disclaimers.",
                "cta": "Open Sharing Studio",
                "target_tab": "sharing",
            },
            {
                "stage": 5,
                "id": "share_ready",
                "short_title": "Share & MCP",
                "title": "Share clean views and connect agents",
                "status": s5_status,
                "metric": f"L2 {'clean' if l2_audit['clean'] else 'needs review'} · L3 {l3_ready_count}/{len(episodes)} ready",
                "summary": "Export lightweight, zero-JavaScript HTML, Resume, Markdown, or JSON files—or connect hiring managers and external AI agents to a read-only, leak-checked L2 MCP endpoint.",
                "why": "Delivers 10× the context of a traditional resume while keeping your raw L0 vault and confidential specifics completely inaccessible.",
                "cta": "Preview & Export Shares",
                "target_tab": "sharing",
            },
        ]

        return {
            "depth_score": depth_score,
            "breakdown": {"coverage": cov, "depth": dep, "narrative": nar, "sharing": shr},
            "stages": stages,
            "summary": {
                "roles_total": len(roles),
                "empty_roles_count": len(empty_roles),
                "episodes_total": len(episodes),
                "unassigned_role_episodes": unassigned_role_eps,
                "flagship_count": flagship_count,
                "thin_episodes_count": len(thin_episodes),
                "sources_total": len(sources),
                "unlinked_sources_count": len(unlinked_sources),
                "substantive_unlinked_count": len(substantive_unlinked),
                "unwritten_clusters_count": len(triage["potential_new_clusters"]),
                "attach_candidates_count": len(triage["attach_candidates"]),
                "legalese_hits_count": len(legalese_hits),
                "unregistered_sensitive_count": len(unregistered_sensitive),
                "unscanned_channels_count": len(unscanned_channels),
            },
            "channel_scans": channel_scans,
            "unscanned_channels": unscanned_channels,
            "role_gaps": empty_roles[:max_examples],
            "substantive_unlinked": [
                {"source_id": s["id"], "title": s["title"], "channel": s["channel"], "event_date": s["event_date"], "chars": s["chars"]}
                for s in substantive_unlinked[:max_examples]
            ],
            "thin_episodes": thin_episodes[:max_examples],
            "channel_coverage": channel_groups,
            "missing_channels": missing_channels,
            "hierarchy_issue": hierarchy_issue,
            "legalese_hits": legalese_hits[:max_examples],
            "next_actions": next_actions,
            "deepening_prompt": "\n".join(prompt_lines),
        }

    # ── Tiered Export Snapshot Assembly ──────────────────────────────────────

    def build_tier_snapshot(
        self,
        tier: str = "L1",
        *,
        episode_ids: list[str] | None = None,
        approved_only: bool = False,
        strict_leaks: bool = True,
        embed_artifacts: bool = False,
    ) -> dict[str, Any]:
        if tier not in EXPORTABLE_TIERS:
            raise ValueError(f"Exportable tier must be one of {EXPORTABLE_TIERS}")
        person = self.get_person()
        episodes = self.list_episodes()
        if episode_ids:
            wanted = set(episode_ids)
            episodes = [e for e in episodes if e["id"] in wanted]

        if tier == "L1":
            return {
                "schema": "career-snapshot/v2",
                "tier": "L1",
                "privacy_notice": "PRIVATE FULL SYNTHESIS (L1). Contains confidential internal details.",
                "generated_at": now_iso(),
                "person": person,
                "roles": self.list_roles(),
                "episodes": episodes,
                "claims": self.list_claims(),
                "sensitive_terms_count": len(self.list_sensitive_terms()),
                "timeline": self.get_timeline(),
            }

        overview = person["overview_l2"] if tier == "L2" else person["overview_l3"]
        overview_leaks = self.scan_leaks(overview)
        if strict_leaks and overview_leaks:
            matched = sorted({f["matched"] for f in overview_leaks})
            raise ValueError(f"Blocked {tier} export: person overview contains sensitive terms: {matched}")

        share_key = "share_l2" if tier == "L2" else "share_l3"
        exported_episodes = []
        skipped_episodes = []
        for ep in episodes:
            proj = ep["tiers"].get(tier)
            if not proj:
                skipped_episodes.append({"id": ep["id"], "reason": f"no_{tier}_projection"})
                continue
            if approved_only and not proj["approved"]:
                skipped_episodes.append({"id": ep["id"], "reason": "not_approved"})
                continue
            if strict_leaks and proj["leaks"]:
                matched = sorted({f["matched"] for f in proj["leaks"]})
                raise ValueError(
                    f"Blocked {tier} export: episode '{ep['id']}' contains sensitive leaks: {matched}"
                )

            shared_artifacts = []
            for art in ep.get("artifacts", []):
                if not art.get(share_key):
                    continue
                item = {
                    "id": art["id"],
                    "title": art["title"],
                    "caption": art["caption"],
                    "media_type": art["media_type"],
                    "sha256": art["sha256"],
                }
                if embed_artifacts:
                    mt, raw_bytes = self.get_artifact_bytes(art["sha256"])
                    item["data_url"] = f"data:{mt};base64,{base64.b64encode(raw_bytes).decode('ascii')}"
                shared_artifacts.append(item)

            entry: dict[str, Any] = {
                "id": ep["id"],
                "period": ep["period_label"],
                "status": ep["status"],
                "importance": ep["importance"],
                "title": proj["title"],
                "summary": proj["summary"],
                "outcome": proj["outcome"],
                "public_links": proj["public_links"],
                "artifacts": shared_artifacts,
                "tags": [t for t in ep["tags"] if "confidential" not in t],
                "stale": proj["stale"],
            }
            if tier == "L2":
                entry["decisions"] = proj["decisions"]
                entry["shared_credit"] = proj["shared_credit"]
            exported_episodes.append(entry)

        roles_safe = [
            {
                "id": r["id"],
                "title": r["title"],
                "organization": r["organization"],
                "period": r["period_label"],
                "is_current": r["is_current"],
            }
            for r in self.list_roles()
        ]

        return {
            "schema": "career-snapshot/v2",
            "tier": tier,
            "privacy_notice": (
                "CONFIDENTIAL-SAFE OVERVIEW (L2). Raw sources, sensitive terms, and internal IDs excluded."
                if tier == "L2"
                else "PUBLIC SUMMARY (L3). Explicitly projected public facts and links only."
            ),
            "generated_at": now_iso(),
            "person": {
                "name": person["name"],
                "headline": person["headline"],
                "overview": overview,
            },
            "roles": roles_safe,
            "episodes": exported_episodes,
            "omitted_count": len(skipped_episodes),
            "leak_checked": True,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _validate_source_refs(self, refs: list[str]) -> list[str]:
        unique = list(dict.fromkeys(r.strip() for r in refs if r.strip()))
        for sid in unique:
            if not self.conn.execute("SELECT 1 FROM sources WHERE id = ?", (sid,)).fetchone():
                raise KeyError(f"Referenced source_id does not exist in vault: {sid}")
        return unique

    @staticmethod
    def _format_period(start: str, end: str, current: bool) -> str:
        if start and current:
            return f"{start}–Present"
        if start and end:
            return f"{start}–{end}"
        return start or end or ""

    def _log(self, action: str, detail: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO activity_log(timestamp, action, detail_json) VALUES (?,?,?)",
            (now_iso(), action, json.dumps(detail, ensure_ascii=False)),
        )
