"""Automated 6-dimension quality, retrieval, security, and scaling assessment for Career Context AI v2."""
from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from .db import CareerVault
from .exporters import export_vault
from .importers import import_v1
from .mcp_server import CareerMCPServer
from .server import StudioApp, build_provider_request, extract_provider_text


def run_holdout_assessment(repo_root: Path, model_dir: Path | None) -> dict[str, Any]:
    """Dimension 1: 12-query retrieval holdout on a fictional career history (FTS5 and optional hybrid search)."""
    hist_path = repo_root / "tests/fixtures/realistic-career-history.json"
    holdout_path = repo_root / "tests/fixtures/retrieval-holdout.json"
    if not hist_path.is_file() or not holdout_path.is_file():
        return {"skipped": True, "reason": "Holdout fixtures not found"}

    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    queries = [q for q in holdout["queries"] if q.get("requiredSources")]

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "holdout.sqlite"
        with CareerVault(db_path) as vault:
            mig = import_v1(vault, hist_path)
            fts_rec5, fts_rec10, fts_mrr, fts_ms = [], [], [], []
            for q in queries:
                req = set(q["requiredSources"])
                t0 = time.perf_counter()
                res = vault.search(q["query"], limit=10)
                fts_ms.append((time.perf_counter() - t0) * 1000)
                # Expand top matched episodes' source_refs + direct source hits
                ranked_sids = [s["source_id"] for s in res["sources"]]
                for ep in res["episodes"][:3]:
                    for sid in vault.get_episode(ep["episode_id"])["source_refs"]:
                        if sid not in ranked_sids:
                            ranked_sids.append(sid)
                hit5 = len(req & set(ranked_sids[:5])) / len(req)
                hit10 = len(req & set(ranked_sids[:10])) / len(req)
                rr = next((1.0 / (i + 1) for i, sid in enumerate(ranked_sids) if sid in req), 0.0)
                fts_rec5.append(hit5)
                fts_rec10.append(hit10)
                fts_mrr.append(rr)

            hyb_summary: dict[str, Any] | None = None
            if model_dir and (model_dir / "model.onnx").is_file():
                try:
                    from .semantic import hybrid_search, sync_embeddings
                    sync_res = sync_embeddings(vault, model_dir)
                    h_rec5, h_rec10, h_mrr, h_ms = [], [], [], []
                    per_q = []
                    for q in queries:
                        req = set(q["requiredSources"])
                        res = hybrid_search(vault, q["query"], model_dir, limit=10, min_similarity=0.35)
                        h_ms.append(res["total_ms"])
                        ranked_sids = [s["source_id"] for s in res["sources"]]
                        for ep in res["episodes"][:3]:
                            for sid in vault.get_episode(ep["episode_id"])["source_refs"]:
                                if sid not in ranked_sids:
                                    ranked_sids.append(sid)
                        hit5 = len(req & set(ranked_sids[:5])) / len(req)
                        hit10 = len(req & set(ranked_sids[:10])) / len(req)
                        rr = next((1.0 / (i + 1) for i, sid in enumerate(ranked_sids) if sid in req), 0.0)
                        h_rec5.append(hit5)
                        h_rec10.append(hit10)
                        h_mrr.append(rr)
                        per_q.append({"id": q["id"], "recall_at_5": round(hit5, 3), "recall_at_10": round(hit10, 3), "mrr": round(rr, 3)})
                    hyb_summary = {
                        "sync_ms": sync_res["elapsed_ms"],
                        "recall_at_5": round(sum(h_rec5) / len(h_rec5), 3),
                        "recall_at_10": round(sum(h_rec10) / len(h_rec10), 3),
                        "mrr": round(sum(h_mrr) / len(h_mrr), 3),
                        "avg_ms": round(sum(h_ms) / len(h_ms), 1),
                        "per_query": per_q,
                    }
                except Exception as exc:
                    hyb_summary = {"error": str(exc)}

    return {
        "queries_evaluated": len(queries),
        "migrated_sources": mig["sources_imported"],
        "v2_fts5": {
            "recall_at_5": round(sum(fts_rec5) / len(fts_rec5), 3),
            "recall_at_10": round(sum(fts_rec10) / len(fts_rec10), 3),
            "mrr": round(sum(fts_mrr) / len(fts_mrr), 3),
            "avg_inproc_ms": round(sum(fts_ms) / len(fts_ms), 2),
        },
        "v2_hybrid_float16": hyb_summary,
    }


def run_security_audit() -> dict[str, Any]:
    """Dimension 2: 10-vector adversarial confidentiality & leak-blocking audit."""
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "sec.sqlite"
        with CareerVault(db) as v:
            v.init(name="Test Person")
            s = v.ingest_source(title="Internal", raw_text="Secret AcmeBank $14.2M >4 retries/10m per BIN", channel="slack")
            ep = v.upsert_episode(episode_id="ep1", title="Checkout", summary_l1="AcmeBank $14.2M", source_refs=[s["id"]])
            v.add_sensitive_term("AcmeBank", replacement="Tier-1 bank", category="customer")
            v.add_sensitive_term("$14.2M", replacement="eight-figure deal", category="metric")
            v.add_sensitive_term(">4 retries/10m per BIN", replacement="velocity threshold", category="proprietary")
            png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRsecret"
            v.add_artifact(episode_id="ep1", data=png, media_type="image/png", title="PrivateShot", share_l2=False, share_l3=False)

            vectors = {
                "exact_customer_blocked": "Built checkout for AcmeBank.",
                "lowercase_customer_blocked": "Built checkout for acmebank.",
                "uppercase_customer_blocked": "Built checkout for ACMEBANK.",
                "currency_metric_blocked": "Saved $14.2M ARR on onboarding.",
                "proprietary_rule_blocked": "Replaced >4 retries/10m per BIN.",
                "email_heuristic_blocked": "Contact sarah@acmepartner.io for details.",
                "openai_key_heuristic_blocked": "Used key sk-abc1234567890XYZ in test.",
                "github_token_heuristic_blocked": "Used ghp_1234567890abcdefghijklmno.",
                "slack_channel_heuristic_blocked": "Discussed in #risk-checkout yesterday.",
            }
            for name, bad_text in vectors.items():
                try:
                    v.set_tier_projection(episode_id="ep1", tier="L2", title="Checkout", summary=bad_text)
                    checks[name] = False
                except ValueError:
                    checks[name] = True

            # Clean save + verify unapproved screenshot omitted + L2 MCP isolation
            v.set_tier_projection(episode_id="ep1", tier="L2", title="Enterprise checkout", summary="Improved checkout for a Tier-1 bank.", approved=True)
            exp = export_vault(v, tier="L2", fmt="html")
            checks["unapproved_visual_excluded"] = ("PrivateShot" not in exp["content"]) and ("<script" not in exp["content"])

        mcp = CareerMCPServer(db, tier="L2", read_write=False)
        try:
            tools = {t["name"] for t in mcp.tools()}
            resp = mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "career_list_episodes", "arguments": {}}})
            txt = resp["result"]["content"][0]["text"]
            checks["mcp_l2_blocks_raw_and_secrets"] = ("career_read_source" not in tools) and ("AcmeBank" not in txt) and ("$14.2M" not in txt)
        finally:
            mcp.close()

    passed = sum(1 for ok in checks.values() if ok)
    return {"passed": passed, "total": len(checks), "all_passed": passed == len(checks), "checks": checks}


def run_integrity_and_browser_audit(repo_root: Path) -> dict[str, Any]:
    """Dimension 3 & 5: Data integrity, FTS5 sync on delete, browser upload/CRUD, multi-provider API, JS check."""
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "int.sqlite"
        with CareerVault(db) as v:
            v.init(name="Integrity Test")
            s1 = v.ingest_source(title="S1", raw_text="UniqueTokenAlpha in raw source text.", channel="doc")
            checks["fts5_finds_unlinked"] = len(v.search("UniqueTokenAlpha")["sources"]) == 1
            v.delete_source(s1["id"])
            checks["fts5_removes_deleted"] = len(v.search("UniqueTokenAlpha")["sources"]) == 0

            s2 = v.ingest_source(title="S2", raw_text="Exact quote verification line here.", channel="doc")
            cl = v.upsert_claim(statement="Verified", evidence_quotes=[{"source_id": s2["id"], "quote": "Exact quote verification"}])
            a = cl["anchors"][0]
            checks["auto_anchor_exact_slice"] = v.get_source(s2["id"])["raw_text"][a["start"]:a["end"]] == "Exact quote verification"

        app = StudioApp(db)
        try:
            st_no_csrf, _, _ = app.dispatch("POST", "/api/person", {}, b'{"name":"Hack"}')
            checks["csrf_blocks_unauthenticated_post"] = (st_no_csrf == 403)
            hdrs = {"Content-Type": "application/json", "X-Career-Token": app.token}
            st_http, _, _ = app.dispatch("POST", "/api/llm/proxy", hdrs, b'{"provider":"openai","base_url":"http://bad.example/v1","user_prompt":"x"}')
            checks["proxy_blocks_plain_http"] = (st_http == 400)
        finally:
            app.close()

    # Multi-provider adapters
    u_a, h_a, _ = build_provider_request(provider="anthropic", model="claude", api_key="k", system_prompt="s", user_prompt="u")
    u_g, _, _ = build_provider_request(provider="gemini", model="gem", api_key="k", system_prompt="s", user_prompt="u")
    checks["multi_provider_adapters"] = ("anthropic.com" in u_a and h_a["x-api-key"] == "k" and "generativelanguage" in u_g and extract_provider_text("gemini", {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}) == "ok")

    # JS syntax check on v2/ui.html
    html = (repo_root / "v2/ui.html").read_text(encoding="utf-8")
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        tmp_js = f.name
    try:
        p = subprocess.run(["node", "--check", tmp_js], capture_output=True)
        checks["ui_js_syntax_valid"] = (p.returncode == 0)
    finally:
        Path(tmp_js).unlink(missing_ok=True)

    passed = sum(1 for ok in checks.values() if ok)
    return {"passed": passed, "total": len(checks), "all_passed": passed == len(checks), "checks": checks}


def run_context_efficiency_audit(repo_root: Path) -> dict[str, Any]:
    """Dimension 6: how much instruction text an assistant has to read."""
    return {"instruction_words": len((repo_root / "SKILL.md").read_text(encoding="utf-8").split())}


def main(argv: list[str] | None = None) -> int:
    repo_root = Path.cwd()
    model_dir = repo_root / ".semantic-model"
    report = {
        "dimension_1_retrieval_holdout": run_holdout_assessment(repo_root, model_dir if model_dir.is_dir() else None),
        "dimension_2_security_leak_audit": run_security_audit(),
        "dimension_3_and_5_integrity_browser": run_integrity_and_browser_audit(repo_root),
        "dimension_6_llm_context_efficiency": run_context_efficiency_audit(repo_root),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
