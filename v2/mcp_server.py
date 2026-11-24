"""Zero-dependency stdio MCP server (JSON-RPC 2.0, protocol 2025-11-25) for Career Context AI v2.

Two explicit boundary modes:
1. Read-Only Shareable Mode (--tier L2 or --tier L3):
   For external agents (hiring, coaching, job-search). Exposes ONLY leak-checked L2/L3 projections.
   Raw L0 sources, L1 private notes, and sensitive terms are completely unreachable.
2. Private Career-Agent Mode (--tier L1 --rw):
   For the user's own local BYO-LLM assistant to ingest, search, synthesize, anchor claims,
   register sensitive terms, and draft/save L2/L3 projections atomically against SQLite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .db import CareerVault

PROTOCOL_VERSION = "2025-11-25"
MAX_LINE_BYTES = 262_144  # 256 KiB


def _tool_def(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


SHAREABLE_TOOLS = [
    _tool_def("career_overview", "Read the person's leak-checked career overview, roles, and tier metadata.", {}),
    _tool_def("career_list_episodes", "List leak-checked work episodes available at this sharing tier.", {}),
    _tool_def("career_search", "Search leak-checked episodes available at this sharing tier.", {
        "query": {"type": "string", "description": "Search terms."},
    }, ["query"]),
]

PRIVATE_RW_TOOLS = [
    _tool_def("career_status", "Get compact vault status: counts, unlinked sources inbox, contradictions, open questions, and L2/L3 staleness.", {}),
    _tool_def("career_timeline", "Get dynamic chronological timeline across roles, episodes, and unlinked dated sources.", {}),
    _tool_def("career_search", "Instant SQLite FTS5 search across raw L0 sources and L1 episodes.", {
        "query": {"type": "string"},
        "channel": {"type": "string"},
        "limit": {"type": "integer"},
    }, ["query"]),
    _tool_def("career_read_source", "Read a full raw L0 source record by source_id.", {
        "source_id": {"type": "string"},
    }, ["source_id"]),
    _tool_def("career_ingest_source", "Store raw source material immediately (collect-first) into the L0 vault.", {
        "title": {"type": "string"},
        "raw_text": {"type": "string"},
        "channel": {"type": "string"},
        "author": {"type": "string"},
        "event_date": {"type": "string"},
        "url": {"type": "string"},
        "scope": {"type": "string"},
        "sensitivity": {"type": "string", "enum": ["L0", "L1", "L2", "L3"]},
    }, ["title", "raw_text"]),
    _tool_def("career_upsert_role", "Create or update a career role/engagement.", {
        "role_id": {"type": "string"},
        "title": {"type": "string"},
        "organization": {"type": "string"},
        "start_date": {"type": "string"},
        "end_date": {"type": "string"},
        "is_current": {"type": "boolean"},
        "summary_l1": {"type": "string"},
        "source_refs": {"type": "array", "items": {"type": "string"}},
    }, ["title"]),
    _tool_def("career_upsert_episode", "Create or update an L1 private career episode/project.", {
        "episode_id": {"type": "string"},
        "role_id": {"type": "string"},
        "title": {"type": "string"},
        "summary_l1": {"type": "string"},
        "start_date": {"type": "string"},
        "end_date": {"type": "string"},
        "status": {"type": "string"},
        "context_l1": {"type": "string"},
        "contribution_l1": {"type": "string"},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "shared_credit_l1": {"type": "string"},
        "outcome_l1": {"type": "string"},
        "limits": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "source_refs": {"type": "array", "items": {"type": "string"}},
    }, ["title", "summary_l1"]),
    _tool_def("career_upsert_claim", "Create or update an evidence-anchored claim (Python computes exact quote offsets and SHA-256 automatically).", {
        "claim_id": {"type": "string"},
        "episode_id": {"type": "string"},
        "statement": {"type": "string"},
        "kind": {"type": "string", "enum": ["fact", "self_report", "interpretation", "hypothesis", "correction"]},
        "status": {"type": "string", "enum": ["candidate", "supported", "qualified", "disputed", "rejected", "withdrawn"]},
        "actor": {"type": "string"},
        "action_state": {"type": "string"},
        "rationale": {"type": "string"},
        "evidence_quotes": {"type": "array", "items": {"type": "object", "properties": {"source_id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["source_id", "quote"]}},
        "counter_quotes": {"type": "array", "items": {"type": "object", "properties": {"source_id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["source_id", "quote"]}},
    }, ["statement"]),
    _tool_def("career_add_sensitive_term", "Register a confidential term (customer name, ARR, proprietary threshold) to block from L2/L3.", {
        "term": {"type": "string"},
        "replacement": {"type": "string"},
        "category": {"type": "string"},
    }, ["term"]),
    _tool_def("career_draft_tier", "Deterministically apply sensitive_terms replacements to L1 to get a starting L2/L3 draft.", {
        "episode_id": {"type": "string"},
        "tier": {"type": "string", "enum": ["L2", "L3"]},
    }, ["episode_id", "tier"]),
    _tool_def("career_set_tier", "Save a leak-checked L2 (confidential-safe) or L3 (public) summary for an episode.", {
        "episode_id": {"type": "string"},
        "tier": {"type": "string", "enum": ["L2", "L3"]},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "outcome": {"type": "string"},
        "shared_credit": {"type": "string"},
        "approved": {"type": "boolean"},
    }, ["episode_id", "tier", "title", "summary"]),
    _tool_def("career_leak_check", "Audit all projections for a shareable tier (L2 or L3) for confidential leaks or staleness.", {
        "tier": {"type": "string", "enum": ["L2", "L3"]},
    }, ["tier"]),
    _tool_def("career_audit_gaps", "Deterministically audit what is still missing across the vault (empty roles, unlinked long docs, thin stories, legalese voice, unregistered sensitive terms) and return prioritized next deepening actions.", {
        "max_examples": {"type": "integer"},
    }),
    _tool_def("career_triage_unlinked", "Cluster unlinked L0 inbox sources into likely episode matches vs potential unwritten stories.", {
        "limit": {"type": "integer"},
    }),
]


class CareerMCPServer:
    def __init__(self, db_path: str | Path, *, tier: str = "L2", read_write: bool = False):
        if tier in ("L2", "L3") and read_write:
            raise ValueError("Shareable tiers (L2/L3) are strictly read-only")
        if tier not in ("L1", "L2", "L3"):
            raise ValueError(f"Unsupported MCP tier: {tier}")
        self.tier = tier
        self.read_write = read_write
        self.vault = CareerVault(db_path, readonly=not read_write)

    def close(self) -> None:
        self.vault.close()

    def tools(self) -> list[dict[str, Any]]:
        return PRIVATE_RW_TOOLS if (self.tier == "L1" and self.read_write) else SHAREABLE_TOOLS

    def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.tier in ("L2", "L3"):
            return self._call_shareable(name, args)
        return self._call_private(name, args)

    def _call_shareable(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.vault.build_tier_snapshot(tier=self.tier, strict_leaks=True)
        if name == "career_overview":
            return {
                "tier": snapshot["tier"],
                "privacy_notice": snapshot["privacy_notice"],
                "person": snapshot["person"],
                "roles": snapshot["roles"],
                "episode_count": len(snapshot["episodes"]),
            }
        if name == "career_list_episodes":
            return {"tier": snapshot["tier"], "episodes": snapshot["episodes"]}
        if name == "career_search":
            q = str(args.get("query", "")).lower().strip()
            tokens = [t for t in q.split() if t]
            hits = []
            for ep in snapshot["episodes"]:
                hay = " ".join([
                    ep.get("title", ""), ep.get("summary", ""), ep.get("outcome", ""),
                    " ".join(ep.get("decisions", [])), " ".join(ep.get("tags", [])),
                ]).lower()
                score = sum(1 for t in tokens if t in hay)
                if score:
                    hits.append({"score": score, **ep})
            hits.sort(key=lambda x: x["score"], reverse=True)
            return {"tier": snapshot["tier"], "query": q, "hits": hits}
        raise ValueError(f"Tool '{name}' is not available in read-only {self.tier} mode")

    def _call_private(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        v = self.vault
        if name == "career_status":
            return v.get_status()
        if name == "career_timeline":
            return {"timeline": v.get_timeline()}
        if name == "career_search":
            return v.search(args["query"], channel=args.get("channel"), limit=int(args.get("limit", 12)))
        if name == "career_read_source":
            return v.get_source(args["source_id"])
        if name == "career_ingest_source":
            return v.ingest_source(**args)
        if name == "career_upsert_role":
            return v.upsert_role(**args)
        if name == "career_upsert_episode":
            return v.upsert_episode(**args)
        if name == "career_upsert_claim":
            return v.upsert_claim(**args)
        if name == "career_add_sensitive_term":
            return v.add_sensitive_term(**args)
        if name == "career_draft_tier":
            return v.draft_sanitized_projection(args["episode_id"], args["tier"])
        if name == "career_set_tier":
            return v.set_tier_projection(**args)
        if name == "career_leak_check":
            return v.audit_tier_leaks(args["tier"])
        if name == "career_audit_gaps":
            return v.audit_gaps(max_examples=int(args.get("max_examples", 8)))
        if name == "career_triage_unlinked":
            return v.triage_unlinked_sources(limit=int(args.get("limit", 80)))
        raise ValueError(f"Unknown tool: {name}")

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        rid = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}
        if method == "notifications/initialized":
            return None
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": f"career-context-v2-{self.tier.lower()}",
                        "version": "2.0.0",
                    },
                }
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                payload = self.call_tool(params["name"], params.get("arguments") or {})
                result = {
                    "content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}],
                    "structuredContent": payload,
                }
            elif method == "ping":
                result = {}
            else:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(exc)}}

    def serve_stdio(self) -> None:
        for raw_line in sys.stdin.buffer:
            if len(raw_line) > MAX_LINE_BYTES:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
