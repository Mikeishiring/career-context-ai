"""Localhost-only HTTP server for Career Context AI v2 Studio.

Binds strictly to 127.0.0.1 with an ephemeral CSRF token injected into the served UI.
All edits, uploads, triage links, and sharing toggles persist directly to career.sqlite.
Includes a stateless, key-never-persisted BYO-LLM proxy solving browser CORS for
OpenAI-compatible, Anthropic Claude, and Google Gemini APIs.
"""
from __future__ import annotations

import base64
import json
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .db import CareerVault
from .exporters import export_vault
from .importers import import_uploaded_file

UI_PATH = Path(__file__).with_name("ui.html")
MAX_UPLOAD_BYTES = 24 * 1024 * 1024  # 24 MiB


def build_provider_request(
    *,
    provider: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str = "",
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Build exact HTTP URL, headers, and JSON body for OpenAI, Anthropic, or Gemini."""
    provider = (provider or "openai").lower().strip()
    if provider == "anthropic":
        url = (base_url.strip() or "https://api.anthropic.com/v1/messages")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model or "claude-3-5-sonnet-latest",
            "max_tokens": 1800,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        return url, headers, payload

    if provider == "gemini":
        mdl = model or "gemini-2.5-flash"
        root = (base_url.strip().rstrip("/") or "https://generativelanguage.googleapis.com/v1beta")
        url = f"{root}/models/{mdl}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        }
        return url, headers, payload

    # Default: OpenAI / OpenRouter / Local Ollama compatible
    url = (base_url.strip() or "https://api.openai.com/v1/chat/completions")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    return url, headers, payload


def extract_provider_text(provider: str, data: dict[str, Any]) -> str:
    provider = (provider or "openai").lower().strip()
    if provider == "anthropic":
        parts = [b.get("text", "") for b in (data.get("content") or []) if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(parts).strip()
    if provider == "gemini":
        cands = data.get("candidates") or []
        if not cands:
            return ""
        parts = [p.get("text", "") for p in ((cands[0].get("content") or {}).get("parts") or []) if isinstance(p, dict)]
        return "\n".join(parts).strip()
    choices = data.get("choices") or []
    return ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""


def _validate_llm_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and host in ("127.0.0.1", "localhost"):
        return
    raise ValueError("LLM endpoint must use https:// or http://localhost / http://127.0.0.1")


class StudioApp:
    """Transport-agnostic HTTP router for Career Context Studio v2."""

    def __init__(self, db_path: str | Path, *, model_dir: str | Path | None = None) -> None:
        self.vault = CareerVault(db_path, readonly=False)
        self.token = secrets.token_hex(24)
        self.ui_template = UI_PATH.read_text(encoding="utf-8")
        default_model = Path(".semantic-model")
        self.model_dir = Path(model_dir) if model_dir else (default_model if default_model.is_dir() else None)

    def close(self) -> None:
        self.vault.close()

    def _json(self, payload: Any, status: int = 200) -> tuple[int, dict[str, str], bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return status, {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, body

    def dispatch(
        self,
        method: str,
        raw_path: str,
        headers: dict[str, str] | None = None,
        raw_body: bytes = b"",
    ) -> tuple[int, dict[str, str], bytes]:
        hdrs = {k.lower(): v for k, v in (headers or {}).items()}
        parsed = urlparse(raw_path)
        qs = parse_qs(parsed.query)
        method = method.upper()

        try:
            if method == "GET":
                if parsed.path in ("/", "/index.html"):
                    html_doc = self.ui_template.replace("@@CSRF_TOKEN@@", self.token).encode("utf-8")
                    return 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}, html_doc

                if parsed.path == "/api/state":
                    return self._json({
                        "status": self.vault.get_status(),
                        "person": self.vault.get_person(),
                        "roles": self.vault.list_roles(),
                        "episodes": self.vault.list_episodes(),
                        "timeline": self.vault.get_timeline(),
                        "knowledge": self.vault.get_knowledge_graph(),
                        "sources": self.vault.list_sources(limit=400),
                        "claims": self.vault.list_claims(),
                        "sensitive_terms": self.vault.list_sensitive_terms(),
                        "channel_scans": self.vault.list_channel_scans(),
                        "semantic_available": bool(self.model_dir and (self.model_dir / "model.onnx").is_file()),
                        "audit": {
                            "L2": self.vault.audit_tier_leaks("L2"),
                            "L3": self.vault.audit_tier_leaks("L3"),
                        },
                        "gaps": self.vault.audit_gaps(),
                    })

                if parsed.path == "/api/gaps":
                    return self._json(self.vault.audit_gaps())

                if parsed.path == "/api/knowledge":
                    return self._json(self.vault.get_knowledge_graph())

                if parsed.path == "/api/inbox/triage":
                    if self.model_dir and (self.model_dir / "model.onnx").is_file():
                        try:
                            from .semantic import semantic_triage_unlinked
                            return self._json(semantic_triage_unlinked(self.vault, self.model_dir))
                        except Exception:
                            pass
                    return self._json(self.vault.triage_unlinked_sources())

                if parsed.path == "/api/search":
                    q = (qs.get("q") or [""])[0]
                    ch = (qs.get("channel") or [""])[0] or None
                    mode = (qs.get("mode") or ["auto"])[0]
                    if mode in ("hybrid", "auto") and self.model_dir and (self.model_dir / "model.onnx").is_file():
                        try:
                            from .semantic import hybrid_search
                            return self._json(hybrid_search(self.vault, q, self.model_dir, channel=ch, limit=20))
                        except Exception:
                            pass
                    return self._json(self.vault.search(q, channel=ch, limit=25))

                if parsed.path == "/api/sensitive/suggest":
                    lim = int((qs.get("limit") or ["25"])[0])
                    return self._json({"suggestions": self.vault.suggest_sensitive_terms(limit=lim)})

                if parsed.path.startswith("/api/source/"):
                    sid = parsed.path.removeprefix("/api/source/")
                    return self._json(self.vault.get_source(sid))

                if parsed.path.startswith("/api/artifact/"):
                    digest = parsed.path.removeprefix("/api/artifact/")
                    mt, data = self.vault.get_artifact_bytes(digest)
                    return 200, {"Content-Type": mt, "Cache-Control": "private, max-age=3600"}, data

                if parsed.path == "/api/backup":
                    snap = self.vault.export_backup_bytes()
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
                    return 200, {
                        "Content-Type": "application/octet-stream",
                        "Content-Disposition": f'attachment; filename="career-vault-backup-{stamp}.sqlite"',
                        "Cache-Control": "no-store",
                    }, snap

                if parsed.path == "/api/mcp-config":
                    resolved_db = str(Path(self.vault.path).expanduser().absolute())
                    repo_root = str(Path(__file__).absolute().parent.parent)
                    py_exe = sys.executable
                    return self._json({
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
                    })

                if parsed.path == "/api/export":
                    tier = (qs.get("tier") or ["L2"])[0]
                    fmt = (qs.get("format") or ["html"])[0]
                    strict = (qs.get("strict") or ["true"])[0].lower() != "false"
                    inline = (qs.get("inline") or ["false"])[0].lower() == "true"
                    res = export_vault(self.vault, tier=tier, fmt=fmt, strict_leaks=strict)
                    content = res["content"].encode("utf-8")
                    ct = {
                        "html": "text/html; charset=utf-8",
                        "json": "application/json; charset=utf-8",
                        "agent_json": "application/json; charset=utf-8",
                        "markdown": "text/markdown; charset=utf-8",
                        "agent_pack": "text/markdown; charset=utf-8",
                        "resume": "text/markdown; charset=utf-8",
                    }.get(fmt, "text/plain; charset=utf-8")
                    ext = "json" if fmt in ("json", "agent_json") else ("md" if fmt in ("markdown", "resume", "agent_pack") else fmt)
                    suffix = "-ai-pack" if fmt in ("agent_pack", "agent_json") else ("-resume" if fmt == "resume" else "")
                    resp_hdrs = {"Content-Type": ct, "Cache-Control": "no-store"}
                    if not inline:
                        resp_hdrs["Content-Disposition"] = f'attachment; filename="career-{tier.lower()}{suffix}.{ext}"'
                    return 200, resp_hdrs, content

                return self._json({"error": "Not found"}, int(HTTPStatus.NOT_FOUND))

            if method == "POST":
                if hdrs.get("x-career-token") != self.token:
                    return self._json({"error": "Invalid or missing CSRF token"}, int(HTTPStatus.FORBIDDEN))
                if not raw_body or len(raw_body) > MAX_UPLOAD_BYTES:
                    raise ValueError("Invalid request body length")
                body = json.loads(raw_body.decode("utf-8"))

                if parsed.path == "/api/person":
                    return self._json(self.vault.update_person(**body))
                if parsed.path == "/api/channels":
                    return self._json(self.vault.upsert_channel_scan(**body))
                if parsed.path == "/api/roles":
                    return self._json(self.vault.upsert_role(**body))
                if parsed.path == "/api/roles/delete":
                    return self._json({"deleted": self.vault.delete_role(body["id"])})
                if parsed.path == "/api/sources":
                    return self._json(self.vault.ingest_source(**body))
                if parsed.path == "/api/sources/delete":
                    return self._json({"deleted": self.vault.delete_source(body["id"])})
                if parsed.path == "/api/ingest/upload":
                    raw_bytes = base64.b64decode(body["content_base64"])
                    return self._json(import_uploaded_file(
                        self.vault,
                        body.get("filename", "upload.txt"),
                        raw_bytes,
                        channel_hint=body.get("channel_hint", "auto"),
                        sensitivity=body.get("sensitivity", "L0"),
                    ))
                if parsed.path == "/api/episodes":
                    return self._json(self.vault.upsert_episode(**body))
                if parsed.path == "/api/episodes/delete":
                    return self._json({"deleted": self.vault.delete_episode(body["id"])})
                if parsed.path == "/api/episodes/link":
                    return self._json(self.vault.link_sources_to_episode(
                        body["episode_id"], list(body.get("source_ids") or [])
                    ))
                if parsed.path == "/api/episodes/unlink":
                    return self._json(self.vault.unlink_source_from_episode(body["episode_id"], body["source_id"]))
                if parsed.path == "/api/episodes/batch-link":
                    grouped: dict[str, list[str]] = {}
                    for item in body.get("links") or []:
                        grouped.setdefault(item["episode_id"], []).append(item["source_id"])
                    linked_total = 0
                    for eid, sids in grouped.items():
                        self.vault.link_sources_to_episode(eid, sids)
                        linked_total += len(sids)
                    return self._json({"episodes_updated": len(grouped), "sources_linked": linked_total})
                if parsed.path == "/api/claims":
                    return self._json(self.vault.upsert_claim(**body))
                if parsed.path == "/api/claims/delete":
                    return self._json({"deleted": self.vault.delete_claim(body["id"])})
                if parsed.path == "/api/sensitive":
                    return self._json(self.vault.add_sensitive_term(**body))
                if parsed.path == "/api/sensitive/delete":
                    return self._json({"deleted": self.vault.remove_sensitive_term(body["id"])})
                if parsed.path == "/api/artifact/share":
                    return self._json(self.vault.set_artifact_sharing(
                        body["id"], share_l2=body.get("share_l2"), share_l3=body.get("share_l3")
                    ))
                if parsed.path == "/api/tier/draft":
                    return self._json(self.vault.draft_sanitized_projection(body["episode_id"], body.get("tier", "L2")))
                if parsed.path == "/api/tier":
                    return self._json(self.vault.set_tier_projection(**body))
                if parsed.path == "/api/tier/batch-sanitize":
                    tier = body.get("tier", "L2")
                    overwrite = bool(body.get("overwrite", False))
                    saved, skipped, blocked = [], [], []
                    for ep in self.vault.list_episodes():
                        existing = ep["tiers"].get(tier)
                        if existing and not existing["stale"] and not overwrite:
                            skipped.append(ep["id"])
                            continue
                        draft = self.vault.draft_sanitized_projection(ep["id"], tier)
                        try:
                            self.vault.set_tier_projection(
                                episode_id=ep["id"], tier=tier, title=draft["title"], summary=draft["summary"],
                                decisions=draft["decisions"], outcome=draft["outcome"],
                                shared_credit=draft["shared_credit"], public_links=draft["public_links"],
                                approved=False,
                            )
                            saved.append(ep["id"])
                        except ValueError as err:
                            blocked.append({"episode_id": ep["id"], "error": str(err)})
                    return self._json({"tier": tier, "saved": saved, "skipped": skipped, "blocked": blocked})
                if parsed.path == "/api/demo/load":
                    return self._json(self.vault.seed_demo_vault(force=False))
                if parsed.path == "/api/embeddings/sync":
                    if not (self.model_dir and (self.model_dir / "model.onnx").is_file()):
                        return self._json({
                            "available": False,
                            "message": "Instant FTS5 keyword search is active. Optional semantic vectors require downloading .semantic-model.",
                        })
                    try:
                        from .semantic import sync_embeddings
                        res = sync_embeddings(self.vault, self.model_dir)
                        res["available"] = True
                        return self._json(res)
                    except (RuntimeError, ImportError) as err:
                        return self._json({
                            "available": False,
                            "message": f"Instant FTS5 keyword search is active ({err})",
                        })
                if parsed.path == "/api/llm/proxy":
                    # Stateless BYO-API proxy: never writes API key to disk or logs
                    provider = body.get("provider", "openai")
                    api_key = hdrs.get("x-llm-key", "")
                    url, req_hdrs, payload = build_provider_request(
                        provider=provider,
                        model=body.get("model", ""),
                        api_key=api_key,
                        system_prompt=body.get("system_prompt", ""),
                        user_prompt=body.get("user_prompt", ""),
                        base_url=body.get("base_url", ""),
                    )
                    _validate_llm_url(url)
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers=req_hdrs,
                        method="POST",
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=60) as resp:
                            resp_data = json.loads(resp.read().decode("utf-8"))
                    except urllib.error.HTTPError as err:
                        detail = err.read().decode("utf-8", errors="replace")[:500]
                        return self._json({"error": f"Provider HTTP {err.code}: {detail}"}, int(HTTPStatus.BAD_GATEWAY))
                    return self._json({
                        "provider": provider,
                        "text": extract_provider_text(provider, resp_data),
                    })
                return self._json({"error": "Not found"}, int(HTTPStatus.NOT_FOUND))

            return self._json({"error": "Method not allowed"}, int(HTTPStatus.METHOD_NOT_ALLOWED))
        except Exception as exc:
            return self._json({"error": str(exc)}, int(HTTPStatus.BAD_REQUEST))


def create_server(db_path: str | Path, *, port: int = 0, model_dir: str | Path | None = None) -> tuple[ThreadingHTTPServer, str, CareerVault]:
    app = StudioApp(db_path, model_dir=model_dir)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            pass

        def _handle(self, method: str) -> None:
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            status, headers, payload = app.dispatch(method, self.path, dict(self.headers.items()), body)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server, app.token, app.vault
