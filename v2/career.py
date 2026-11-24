"""Unified CLI entrypoint for Career Context AI v2.

Usage:
  python -m v2.career init <db> --name "Maya Lin" --goal "..."
  python -m v2.career ingest <db> --channel folder|github|slack|notion|linkedin|x|substack|direct ...
  python -m v2.career search <db> "noisy neighbor" [--channel slack]
  python -m v2.career status <db>
  python -m v2.career timeline <db>
  python -m v2.career upsert-role <db> --title ... --org ...
  python -m v2.career upsert-episode <db> --title ... --summary ...
  python -m v2.career upsert-claim <db> --statement ... --quote source_id::"exact quote"
  python -m v2.career sensitive add|list|remove <db> ...
  python -m v2.career draft-tier <db> <episode_id> --tier L2|L3
  python -m v2.career set-tier <db> <episode_id> --tier L2|L3 --title ... --summary ...
  python -m v2.career leak-check <db> --tier L2|L3
  python -m v2.career export <db> --tier L1|L2|L3 --format html|json|markdown|resume --out FILE
  python -m v2.career serve <db> [--port 8765]
  python -m v2.career mcp <db> [--tier L2|L3|L1] [--rw]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .db import CareerVault
from .exporters import export_vault
from .importers import (
    import_folder,
    import_github,
    import_linkedin,
    import_notion,
    import_slack,
    import_substack,
    import_v1,
    import_x,
)
from .mcp_server import CareerMCPServer
from .semantic import hybrid_search, semantic_triage_unlinked, sync_embeddings
from .server import create_server


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def build_mcp_config(db_path: str | Path) -> dict[str, Any]:
    """Generate exact OS-aware MCP JSON configs for private L1 (--rw) and shareable L2 (read-only)."""
    resolved_db = str(Path(db_path).expanduser().absolute())
    repo_root = str(Path(__file__).absolute().parent.parent)
    py_exe = sys.executable
    return {
        "db_path": resolved_db,
        "python": py_exe,
        "cwd": repo_root,
        "private_mcp": {
            "mcpServers": {
                "career-context-private": {
                    "command": py_exe,
                    "args": ["-m", "v2.career", "mcp", resolved_db, "--tier", "L1", "--rw"],
                    "cwd": repo_root,
                }
            }
        },
        "share_mcp": {
            "mcpServers": {
                "career-context-shareable": {
                    "command": py_exe,
                    "args": ["-m", "v2.career", "mcp", resolved_db, "--tier", "L2"],
                    "cwd": repo_root,
                }
            }
        },
    }


def _parse_quote_args(items: list[str] | None) -> list[dict[str, str]]:
    out = []
    for raw in items or []:
        if "::" not in raw:
            raise ValueError(f"Expected 'source_id::exact quote', got: {raw}")
        sid, quote = raw.split("::", 1)
        out.append({"source_id": sid.strip(), "quote": quote.strip()})
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="career-v2", description="Career Context AI v2 local knowledge vault CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # init
    s = sub.add_parser("init", help="Initialize a new local SQLite career vault")
    s.add_argument("db")
    s.add_argument("--name", default="")
    s.add_argument("--headline", default="")
    s.add_argument("--goal", default="")

    # status / timeline / search
    s = sub.add_parser("status", help="Compact agent/human briefing of vault state")
    s.add_argument("db")

    s = sub.add_parser("timeline", help="Dynamic chronological timeline")
    s.add_argument("db")

    s = sub.add_parser("search", help="Instant SQLite FTS5 or cached hybrid semantic search")
    s.add_argument("db")
    s.add_argument("query")
    s.add_argument("--channel", default=None)
    s.add_argument("--limit", type=int, default=12)
    s.add_argument("--model-dir", default=None, help="Enable SQLite-cached ONNX hybrid semantic search")

    s = sub.add_parser("sync-embeddings", help="Precompute and cache local ONNX embeddings in SQLite")
    s.add_argument("db")
    s.add_argument("--model-dir", required=True)

    # ingest
    s = sub.add_parser("ingest", help="Ingest raw material into L0 vault (collect-first)")
    s.add_argument("db")
    s.add_argument("--channel", required=True, choices=["folder", "github", "slack", "notion", "linkedin", "x", "substack", "direct", "v1"])
    s.add_argument("--path", help="File or folder path to import")
    s.add_argument("--title", default="")
    s.add_argument("--text", default="")
    s.add_argument("--subchannel", default="doc", help="Channel label for folder/direct imports (e.g. resume, gdocs, voice_note)")
    s.add_argument("--author", default="")
    s.add_argument("--date", default="")
    s.add_argument("--url", default="")
    s.add_argument("--scope", default="")
    s.add_argument("--sensitivity", default="L0", choices=["L0", "L1", "L2", "L3"])
    s.add_argument("--handle", default="", help="X handle for URL construction")

    # upsert-role
    s = sub.add_parser("upsert-role", help="Create or update a role")
    s.add_argument("db")
    s.add_argument("--id", dest="role_id", default=None)
    s.add_argument("--title", required=True)
    s.add_argument("--org", default="")
    s.add_argument("--start", default="")
    s.add_argument("--end", default="")
    s.add_argument("--current", action="store_true")
    s.add_argument("--summary", default="")
    s.add_argument("--source", action="append", default=[])

    # upsert-episode
    s = sub.add_parser("upsert-episode", help="Create or update an L1 private episode")
    s.add_argument("db")
    s.add_argument("--id", dest="episode_id", default=None)
    s.add_argument("--role-id", default=None)
    s.add_argument("--title", required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--start", default="")
    s.add_argument("--end", default="")
    s.add_argument("--status", default="shipped")
    s.add_argument("--context", default="")
    s.add_argument("--contribution", default="")
    s.add_argument("--decision", action="append", default=[])
    s.add_argument("--credit", default="")
    s.add_argument("--outcome", default="")
    s.add_argument("--limit", action="append", default=[])
    s.add_argument("--question", action="append", default=[])
    s.add_argument("--tag", action="append", default=[])
    s.add_argument("--source", action="append", default=[])

    # upsert-claim
    s = sub.add_parser("upsert-claim", help="Create or update a claim with automatic quote anchoring")
    s.add_argument("db")
    s.add_argument("--id", dest="claim_id", default=None)
    s.add_argument("--episode-id", default=None)
    s.add_argument("--statement", required=True)
    s.add_argument("--kind", default="fact")
    s.add_argument("--status", default="candidate")
    s.add_argument("--actor", default="")
    s.add_argument("--action-state", default="unknown")
    s.add_argument("--rationale", default="")
    s.add_argument("--quote", action="append", default=[], help="Format: source_id::exact quote")
    s.add_argument("--counter-quote", action="append", default=[], help="Format: source_id::exact quote")

    # sensitive
    s = sub.add_parser("sensitive", help="Manage registered confidential terms for leak detection")
    s.add_argument("action", choices=["add", "list", "remove", "suggest"])
    s.add_argument("db")
    s.add_argument("--term", default="")
    s.add_argument("--replacement", default="[redacted]")
    s.add_argument("--category", default="other")
    s.add_argument("--limit", type=int, default=30)

    s = sub.add_parser("compact", help="Checkpoint WAL and VACUUM SQLite database")
    s.add_argument("db")

    s = sub.add_parser("knowledge", help="Aggregate capabilities, tools, themes, and decisions across episodes")
    s.add_argument("db")

    s = sub.add_parser("triage", help="Cluster unlinked L0 inbox sources into episode matches vs new stories")
    s.add_argument("db")
    s.add_argument("--model-dir", default=None, help="Use cached float16 ONNX embeddings for semantic triage")
    s.add_argument("--threshold", type=float, default=0.70)

    s = sub.add_parser("audit-gaps", help="Deterministically audit coverage, story depth, voice quality, and sharing gaps")
    s.add_argument("db")
    s.add_argument("--max-examples", type=int, default=8)

    s = sub.add_parser("channels", help="Track work/communication channels and MCP scan progress")
    s.add_argument("action", choices=["list", "set"])
    s.add_argument("db")
    s.add_argument("--channel", default="")
    s.add_argument("--label", default="")
    s.add_argument("--method", default="mcp", choices=["mcp", "connector", "export", "manual"])
    s.add_argument("--status", default="declared", choices=["declared", "scanning", "scanned", "skipped"])
    s.add_argument("--dates", default="")
    s.add_argument("--query", action="append", default=[])
    s.add_argument("--remaining", default="")

    # draft-tier / set-tier / leak-check
    s = sub.add_parser("draft-tier", help="Generate deterministic sanitized L2/L3 draft from L1")
    s.add_argument("db")
    s.add_argument("episode_id")
    s.add_argument("--tier", required=True, choices=["L2", "L3"])

    s = sub.add_parser("set-tier", help="Save a leak-checked L2 or L3 projection")
    s.add_argument("db")
    s.add_argument("episode_id")
    s.add_argument("--tier", required=True, choices=["L2", "L3"])
    s.add_argument("--title", required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--decision", action="append", default=[])
    s.add_argument("--outcome", default="")
    s.add_argument("--credit", default="")
    s.add_argument("--approved", action="store_true")

    s = sub.add_parser("leak-check", help="Audit L2 or L3 projections for confidential leaks and staleness")
    s.add_argument("db")
    s.add_argument("--tier", required=True, choices=["L2", "L3"])

    # export
    s = sub.add_parser("export", help="Export clean static HTML, Resume (succinct), or exhaustive AI Context Pack (agent_pack/agent_json)")
    s.add_argument("db")
    s.add_argument("--tier", default="L2", choices=["L1", "L2", "L3"])
    s.add_argument("--format", dest="fmt", default="html", choices=["html", "json", "markdown", "resume", "agent_pack", "agent_json"])
    s.add_argument("--out", required=True)
    s.add_argument("--approved-only", action="store_true")

    # serve
    s = sub.add_parser("serve", help="Run localhost Studio UI backed directly by SQLite")
    s.add_argument("db")
    s.add_argument("--port", type=int, default=8765)

    # mcp
    s = sub.add_parser("mcp", help="Run stdio MCP server (--tier L2|L3 RO or --tier L1 --rw)")
    s.add_argument("db")
    s.add_argument("--tier", default="L2", choices=["L1", "L2", "L3"])
    s.add_argument("--rw", action="store_true")

    # mcp-config
    s = sub.add_parser("mcp-config", help="Print ready-to-paste OS-aware MCP JSON config for Claude Desktop / Cursor")
    s.add_argument("db", nargs="?", default=str(Path.home() / ".career-context" / "career.sqlite"))
    s.add_argument("--mode", default="both", choices=["both", "private", "share"])

    # backup
    s = sub.add_parser("backup", help="Write a consistent live SQLite backup snapshot")
    s.add_argument("db")
    s.add_argument("--out", required=True)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "mcp-config":
            cfg = build_mcp_config(args.db)
            if args.mode == "private":
                _print(cfg["private_mcp"])
            elif args.mode == "share":
                _print(cfg["share_mcp"])
            else:
                _print(cfg)
            return 0

        if args.cmd == "mcp":
            srv = CareerMCPServer(args.db, tier=args.tier, read_write=args.rw)
            try:
                srv.serve_stdio()
            finally:
                srv.close()
            return 0

        if args.cmd == "serve":
            http_srv, _token, vault = create_server(args.db, port=args.port)
            host, port = http_srv.server_address
            print(f"Career Context Studio v2 running at http://{host}:{port}/  (Ctrl+C to stop)", flush=True)
            try:
                http_srv.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                http_srv.server_close()
                vault.close()
            return 0

        with CareerVault(args.db) as vault:
            if args.cmd == "init":
                _print(vault.init(name=args.name, headline=args.headline, goal=args.goal))
            elif args.cmd == "status":
                _print(vault.get_status())
            elif args.cmd == "timeline":
                _print(vault.get_timeline())
            elif args.cmd == "search":
                if args.model_dir:
                    _print(hybrid_search(vault, args.query, args.model_dir, channel=args.channel, limit=args.limit))
                else:
                    _print(vault.search(args.query, channel=args.channel, limit=args.limit))
            elif args.cmd == "sync-embeddings":
                _print(sync_embeddings(vault, args.model_dir))
            elif args.cmd == "ingest":
                ch = args.channel
                if ch == "v1":
                    _print(import_v1(vault, args.path))
                elif ch == "direct":
                    text = args.text if args.text else sys.stdin.read()
                    _print(vault.ingest_source(
                        title=args.title or "Direct capture",
                        raw_text=text,
                        channel=args.subchannel,
                        author=args.author,
                        event_date=args.date,
                        url=args.url,
                        scope=args.scope or "Direct capture",
                        sensitivity=args.sensitivity,
                    ))
                elif ch == "folder":
                    _print(import_folder(vault, args.path, channel=args.subchannel, sensitivity=args.sensitivity, scope=args.scope))
                elif ch == "github":
                    _print(import_github(vault, args.path, author_filter=args.author, sensitivity=args.sensitivity))
                elif ch == "slack":
                    _print(import_slack(vault, args.path, sensitivity=args.sensitivity))
                elif ch == "notion":
                    _print(import_notion(vault, args.path, sensitivity=args.sensitivity))
                elif ch == "linkedin":
                    _print(import_linkedin(vault, args.path))
                elif ch == "x":
                    _print(import_x(vault, args.path, handle=args.handle))
                elif ch == "substack":
                    _print(import_substack(vault, args.path, author=args.author))
            elif args.cmd == "upsert-role":
                _print(vault.upsert_role(
                    role_id=args.role_id, title=args.title, organization=args.org,
                    start_date=args.start, end_date=args.end, is_current=args.current,
                    summary_l1=args.summary, source_refs=args.source,
                ))
            elif args.cmd == "upsert-episode":
                _print(vault.upsert_episode(
                    episode_id=args.episode_id, role_id=args.role_id, title=args.title,
                    summary_l1=args.summary, start_date=args.start, end_date=args.end,
                    status=args.status, context_l1=args.context, contribution_l1=args.contribution,
                    decisions=args.decision, shared_credit_l1=args.credit, outcome_l1=args.outcome,
                    limits=args.limit, questions=args.question, tags=args.tag, source_refs=args.source,
                ))
            elif args.cmd == "upsert-claim":
                _print(vault.upsert_claim(
                    claim_id=args.claim_id, episode_id=args.episode_id, statement=args.statement,
                    kind=args.kind, status=args.status, actor=args.actor,
                    action_state=args.action_state, rationale=args.rationale,
                    evidence_quotes=_parse_quote_args(args.quote),
                    counter_quotes=_parse_quote_args(args.counter_quote),
                ))
            elif args.cmd == "sensitive":
                if args.action == "add":
                    _print(vault.add_sensitive_term(args.term, replacement=args.replacement, category=args.category))
                elif args.action == "list":
                    _print(vault.list_sensitive_terms())
                elif args.action == "remove":
                    _print({"deleted": vault.remove_sensitive_term(args.term)})
                elif args.action == "suggest":
                    _print(vault.suggest_sensitive_terms(limit=args.limit))
            elif args.cmd == "compact":
                _print({"bytes": vault.compact()})
            elif args.cmd == "backup":
                data = vault.export_backup_bytes()
                out = Path(args.out).expanduser().resolve()
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
                _print({"backup_path": str(out), "bytes": len(data)})
            elif args.cmd == "knowledge":
                _print(vault.get_knowledge_graph())
            elif args.cmd == "triage":
                if args.model_dir:
                    _print(semantic_triage_unlinked(vault, args.model_dir, attach_threshold=args.threshold))
                else:
                    _print(vault.triage_unlinked_sources())
            elif args.cmd == "audit-gaps":
                _print(vault.audit_gaps(max_examples=args.max_examples))
            elif args.cmd == "channels":
                if args.action == "list":
                    _print(vault.list_channel_scans())
                else:
                    _print(vault.upsert_channel_scan(
                        channel=args.channel,
                        label=args.label,
                        access_method=args.method,
                        status=args.status,
                        date_range_covered=args.dates,
                        queries_run=args.query,
                        remaining_notes=args.remaining,
                    ))
            elif args.cmd == "draft-tier":
                _print(vault.draft_sanitized_projection(args.episode_id, args.tier))
            elif args.cmd == "set-tier":
                _print(vault.set_tier_projection(
                    episode_id=args.episode_id, tier=args.tier, title=args.title,
                    summary=args.summary, decisions=args.decision, outcome=args.outcome,
                    shared_credit=args.credit, approved=args.approved,
                ))
            elif args.cmd == "leak-check":
                _print(vault.audit_tier_leaks(args.tier))
            elif args.cmd == "export":
                _print(export_vault(
                    vault, tier=args.tier, fmt=args.fmt, out_path=args.out,
                    approved_only=args.approved_only,
                ))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
