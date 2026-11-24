"""Comprehensive automated test suite for Career Context AI v2."""
from __future__ import annotations

import base64
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from v2.db import CareerVault
from v2.exporters import export_vault
from v2.importers import (
    import_folder,
    import_github,
    import_linkedin,
    import_notion,
    import_slack,
    import_substack,
    import_x,
)
from v2.mcp_server import CareerMCPServer
from v2.server import StudioApp, build_provider_request, extract_provider_text


class TestCareerVaultV2(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "career.sqlite"
        self.vault = CareerVault(self.db_path)
        self.vault.init(
            name="Maya Lin",
            headline="Staff Product Engineer — Payments & Distributed Systems",
            goal="Private career knowledge base with L0-L3 tiered sharing",
        )

    def tearDown(self) -> None:
        self.vault.close()
        self.tmp.cleanup()

    def test_collect_first_unreferenced_sources_and_fts5_search(self) -> None:
        # Principle #1: collect raw material BEFORE creating any role or episode!
        r1 = self.vault.ingest_source(
            title="ClearLedger Offer Letter",
            raw_text="Title: Staff Product Engineer. Start Date: 2023-07-01. Base + Equity.",
            channel="doc",
            event_date="2023-06-15",
            sensitivity="L0",
        )
        r2 = self.vault.ingest_source(
            title="Webhook Queue Essay",
            raw_text="Noisy neighbor endpoints starved our shared webhook queue until we added per-tenant circuit breakers.",
            channel="substack",
            event_date="2024-03-14",
            url="https://mayalin.substack.com/p/webhooks",
            sensitivity="L3",
        )
        # Deduplication on identical raw text
        r2_dup = self.vault.ingest_source(
            title="Duplicate Essay",
            raw_text="Noisy neighbor endpoints starved our shared webhook queue until we added per-tenant circuit breakers.",
            channel="substack",
        )
        self.assertTrue(r2_dup["deduplicated"])
        self.assertEqual(r2_dup["id"], r2["id"])

        status = self.vault.get_status()
        self.assertEqual(status["counts"]["sources"], 2)
        self.assertEqual(status["counts"]["unlinked_sources"], 2)

        hits = self.vault.search("circuit breakers")
        self.assertEqual(len(hits["sources"]), 1)
        self.assertEqual(hits["sources"][0]["source_id"], r2["id"])

        # Dynamic timeline includes unlinked dated sources automatically
        timeline = self.vault.get_timeline()
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["id"], r2["id"])  # 2024-03-14 before 2023-06-15
        self.assertEqual(timeline[1]["id"], r1["id"])

    def test_all_channel_importers(self) -> None:
        # 1. Folder (resume + Google Docs HTML export)
        docs_dir = self.root / "docs"
        docs_dir.mkdir()
        (docs_dir / "resume_2025.md").write_text("ClearLedger Staff Engineer. Reduced fraud by 60%.", encoding="utf-8")
        (docs_dir / "gdoc_design.html").write_text("<html><body><h1>Design</h1><p>Shadow evaluator notes</p></body></html>", encoding="utf-8")
        res_folder = import_folder(self.vault, docs_dir, channel="doc")
        self.assertEqual(res_folder["count"], 2)

        # 2. GitHub PR JSON + local git repo
        gh_json = self.root / "prs.json"
        gh_json.write_text(json.dumps([
            {
                "number": 418,
                "title": "RFC #418: Multi-currency ledger v2",
                "body": "Partitioned Postgres double-entry FX sub-ledger prototype hitting 10k TPS.",
                "state": "closed",
                "user": {"login": "mayalin"},
                "created_at": "2025-04-02T10:00:00Z",
                "comments": [{"author": "priya-vp", "body": "Shelving for H2 to prioritize US instant payouts."}],
            }
        ]), encoding="utf-8")
        res_gh = import_github(self.vault, gh_json)
        self.assertEqual(res_gh["count"], 1)

        repo_dir = self.root / "sample-repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "Maya Lin"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "maya@example.com"], cwd=repo_dir, check=True)
        (repo_dir / "worker.go").write_text("package main\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Add per-tenant circuit breaker to webhook worker"], cwd=repo_dir, check=True, stdout=subprocess.DEVNULL)
        res_git = import_github(self.vault, repo_dir, author_filter="Maya")
        self.assertEqual(res_git["count"], 1)

        # 3. Slack export
        slack_dir = self.root / "slack"
        (slack_dir / "risk-checkout").mkdir(parents=True)
        (slack_dir / "users.json").write_text(json.dumps([
            {"id": "U1", "profile": {"real_name": "Maya Lin"}},
            {"id": "U2", "profile": {"real_name": "Devon Risk"}},
        ]), encoding="utf-8")
        (slack_dir / "risk-checkout" / "2024-09-18.json").write_text(json.dumps([
            {"ts": "1726675200.000100", "thread_ts": "1726675200.000100", "user": "U1",
             "text": "AcmeBank ($14.2M ARR) hit 11.4% false declines on BIN retry >4/10m. Shadow evaluator dropped it 38%."},
            {"ts": "1726675500.000200", "thread_ts": "1726675200.000100", "user": "U2",
             "text": "Also note Risk Ops shipped 3DS v2 in week 4."},
        ]), encoding="utf-8")
        res_slack = import_slack(self.vault, slack_dir)
        self.assertEqual(res_slack["count"], 1)

        # 4. Notion export (strips 32-char UUID suffix)
        notion_dir = self.root / "notion"
        notion_dir.mkdir()
        (notion_dir / "Q3 Checkout Reliability 0123456789abcdef0123456789abcdef.md").write_text(
            "Date: 2024-08-01\nNotes on shadow traffic replay architecture.", encoding="utf-8"
        )
        res_notion = import_notion(self.vault, notion_dir)
        self.assertEqual(res_notion["count"], 1)
        self.assertEqual(res_notion["items"][0]["title"], "Q3 Checkout Reliability")

        # 5. LinkedIn export (Positions + Shares)
        li_dir = self.root / "linkedin"
        li_dir.mkdir()
        (li_dir / "Positions.csv").write_text(
            "Company Name,Title,Description,Started On,Finished On\n"
            "ClearLedger,Staff Product Engineer,Payments and risk infrastructure,Jul 2023,\n"
            "RelayGrid,Founding Engineer,Webhook delivery infrastructure,Jan 2020,Jun 2023\n",
            encoding="utf-8",
        )
        (li_dir / "Shares.csv").write_text(
            "Date,ShareLink,ShareCommentary\n"
            "2025-01-10,https://linkedin.com/posts/1,Why shadow-mode rollouts save enterprise deals.\n",
            encoding="utf-8",
        )
        res_li = import_linkedin(self.vault, li_dir)
        self.assertEqual(res_li["count"], 3)
        self.assertEqual(res_li["roles_created"], 2)

        # 6. X / Twitter archive (tweets.js)
        tweets_js = self.root / "tweets.js"
        tweets_js.write_text(
            'window.YTD.tweets.part0 = [{"tweet": {"id_str": "189234567890", '
            '"created_at": "Thu Feb 20 14:22:00 +0000 2025", '
            '"full_text": "In 2022 I managed 6 engineers at RelayGrid for 8 months before intentionally returning to Staff IC."}}, '
            '{"tweet": {"id_str": "2", "created_at": "Thu Feb 20 14:25:00 +0000 2025", "full_text": "RT @other: skip me please because this is a long retweet"}}];',
            encoding="utf-8",
        )
        res_x = import_x(self.vault, tweets_js, handle="mayalin_dev")
        self.assertEqual(res_x["count"], 1)

        # 7. Substack RSS XML
        rss = self.root / "substack.xml"
        rss.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
              <channel><item>
                <title>Why Your Webhook Queue Fails at 2am</title>
                <link>https://mayalin.substack.com/p/why-your-webhook-queue-fails</link>
                <pubDate>Thu, 14 Mar 2024 12:00:00 GMT</pubDate>
                <content:encoded><![CDATA[<p>Splitting dead-letter lanes by tenant tier saved our on-call rotation.</p>]]></content:encoded>
              </item></channel>
            </rss>""",
            encoding="utf-8",
        )
        res_sub = import_substack(self.vault, rss, author="Maya Lin")
        self.assertEqual(res_sub["count"], 1)

        # Verify all 7 channels are indexed and instantly searchable in FTS5
        self.assertGreaterEqual(self.vault.get_status()["counts"]["sources"], 10)
        self.assertEqual(len(self.vault.search("AcmeBank")["sources"]), 1)
        self.assertEqual(len(self.vault.search("dead-letter lanes")["sources"]), 1)

    def test_auto_anchoring_granularity_tiers_staleness_and_leak_blocking(self) -> None:
        s_slack = self.vault.ingest_source(
            title="Internal #risk-checkout Slack",
            raw_text=(
                "AcmeBank ($14.2M ARR prospect) hit 11.4% false declines from our >4 retries/10m per BIN rule. "
                "I prototyped the shadow-mode rule evaluator with Devon. EU cohort false declines dropped 38%."
            ),
            channel="slack",
            event_date="2024-09-18",
            sensitivity="L0",
        )
        role = self.vault.upsert_role(
            role_id="clearledger",
            title="Staff Product Engineer",
            organization="ClearLedger",
            start_date="2023-07",
            is_current=True,
            source_refs=[s_slack["id"]],
        )
        ep = self.vault.upsert_episode(
            episode_id="shadow-eval",
            role_id=role["id"],
            title="Shadow-mode risk rule evaluator for AcmeBank checkout",
            start_date="2024-07",
            end_date="2024-10",
            status="pilot",
            summary_l1=(
                "AcmeBank ($14.2M ARR) suffered 11.4% false declines under our >4 retries/10m per BIN velocity check. "
                "I prototyped a shadow-mode evaluator with Devon, reducing EU cohort false declines by 38%."
            ),
            decisions=["Ran new rule logic in shadow mode on live traffic before gating checkout."],
            shared_credit_l1="Paired with Devon (Risk Eng) on fallback queue.",
            outcome_l1="EU cohort false declines dropped 38% over 6 weeks for AcmeBank.",
            source_refs=[s_slack["id"]],
        )

        # Automatic quote anchoring computes exact start, end, and sha256 without LLM math!
        claim = self.vault.upsert_claim(
            claim_id="c-false-declines",
            episode_id=ep["id"],
            statement="EU cohort false declines dropped 38%.",
            kind="fact",
            status="qualified",
            actor="Maya Lin",
            action_state="completed",
            evidence_quotes=[{"source_id": s_slack["id"], "quote": "EU cohort false declines dropped 38%."}],
        )
        self.assertEqual(len(claim["anchors"]), 1)
        anchor = claim["anchors"][0]
        raw = self.vault.get_source(s_slack["id"])["raw_text"]
        self.assertEqual(raw[anchor["start"]:anchor["end"]], "EU cohort false declines dropped 38%.")

        # Register confidential terms
        self.vault.add_sensitive_term("AcmeBank", replacement="a Tier-1 European bank", category="customer")
        self.vault.add_sensitive_term("$14.2M", replacement="an eight-figure enterprise deal", category="metric")
        self.vault.add_sensitive_term(">4 retries/10m per BIN", replacement="legacy velocity thresholds", category="proprietary")
        self.vault.add_sensitive_term("Devon", replacement="a Risk Engineering partner", category="person")

        # Attempting to save L2 with confidential leak MUST BE BLOCKED!
        with self.assertRaises(ValueError) as ctx:
            self.vault.set_tier_projection(
                episode_id=ep["id"],
                tier="L2",
                title="Shadow evaluator for AcmeBank",
                summary="Unblocked AcmeBank ($14.2M) checkout with shadow evaluator.",
            )
        self.assertIn("AcmeBank", str(ctx.exception))

        # Auto-sanitize draft produces a clean starting point
        draft = self.vault.draft_sanitized_projection(ep["id"], "L2")
        self.assertEqual(draft["remaining_leaks"], [])
        self.assertNotIn("AcmeBank", draft["summary"])
        self.assertIn("Tier-1 European bank", draft["summary"])

        # Saving clean L2 succeeds
        proj = self.vault.set_tier_projection(
            episode_id=ep["id"],
            tier="L2",
            title=draft["title"],
            summary=draft["summary"],
            decisions=draft["decisions"],
            outcome=draft["outcome"],
            shared_credit=draft["shared_credit"],
            approved=True,
        )
        self.assertFalse(proj["stale"])
        self.assertEqual(proj["leaks"], [])

        # Updating L1 automatically marks L2 as STALE without deleting it!
        self.vault.upsert_episode(
            episode_id=ep["id"],
            role_id=role["id"],
            title=ep["title"],
            summary_l1=ep["summary_l1"] + " Later rolled out to 3 more EU enterprise accounts.",
            decisions=ep["decisions"],
            shared_credit_l1=ep["shared_credit_l1"],
            outcome_l1=ep["outcome_l1"],
            source_refs=[s_slack["id"]],
        )
        ep_after = self.vault.get_episode(ep["id"])
        self.assertTrue(ep_after["tiers"]["L2"]["stale"])

        # Static HTML export for L2 is tiny, CSP-protected, and contains ZERO confidential terms
        out_html = self.root / "l2.html"
        exp = export_vault(self.vault, tier="L2", fmt="html", out_path=out_html)
        html_text = out_html.read_text(encoding="utf-8")
        self.assertTrue(exp["leak_checked"])
        self.assertLess(exp["bytes"], 10_000)
        self.assertNotIn("AcmeBank", html_text)
        self.assertNotIn("$14.2M", html_text)
        self.assertNotIn("<script", html_text)

    def test_mcp_server_shareable_and_private_modes(self) -> None:
        s = self.vault.ingest_source(
            title="Secret Doc",
            raw_text="Project Titan with AcmeBank earned $14.2M ARR.",
            channel="doc",
        )
        self.vault.add_sensitive_term("AcmeBank", replacement="enterprise bank", category="customer")
        self.vault.add_sensitive_term("Project Titan", replacement="checkout modernization", category="proprietary")
        self.vault.upsert_episode(
            episode_id="titan",
            title="Project Titan for AcmeBank",
            summary_l1="Built Project Titan for AcmeBank ($14.2M ARR).",
            source_refs=[s["id"]],
        )
        self.vault.set_tier_projection(
            episode_id="titan",
            tier="L2",
            title="Enterprise checkout modernization",
            summary="Designed shadow-mode checkout modernization for an enterprise bank.",
            approved=True,
        )

        # Read-only L2 MCP server cannot read raw sources or leak AcmeBank
        mcp_l2 = CareerMCPServer(self.db_path, tier="L2", read_write=False)
        try:
            tools = [t["name"] for t in mcp_l2.tools()]
            self.assertNotIn("career_read_source", tools)
            resp = mcp_l2.handle_request({
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "career_list_episodes", "arguments": {}},
            })
            payload_text = resp["result"]["content"][0]["text"]
            self.assertIn("Enterprise checkout modernization", payload_text)
            self.assertNotIn("AcmeBank", payload_text)
            self.assertNotIn("Project Titan", payload_text)
        finally:
            mcp_l2.close()

        # Private L1 RW MCP server can ingest & upsert atomically
        mcp_l1 = CareerMCPServer(self.db_path, tier="L1", read_write=True)
        try:
            resp = mcp_l1.handle_request({
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "career_ingest_source", "arguments": {
                    "title": "Voice memo", "raw_text": "I prefer Staff IC over management.", "channel": "voice_note"
                }},
            })
            self.assertIn("structuredContent", resp["result"])
            self.assertEqual(resp["result"]["structuredContent"]["channel"], "voice_note")
        finally:
            mcp_l1.close()

    def test_localhost_studio_server_csrf_and_live_persistence(self) -> None:
        app = StudioApp(self.db_path)
        try:
            # GET UI injects ephemeral CSRF token
            status, _, body = app.dispatch("GET", "/")
            self.assertEqual(status, 200)
            self.assertIn(app.token, body.decode("utf-8"))

            # POST without CSRF token must fail with 403
            status, _, _ = app.dispatch(
                "POST", "/api/sources", {"Content-Type": "application/json"},
                json.dumps({"title": "X", "raw_text": "Hello"}).encode(),
            )
            self.assertEqual(status, 403)

            # POST with valid CSRF token persists directly to SQLite!
            status, _, body = app.dispatch(
                "POST", "/api/sources",
                {"Content-Type": "application/json", "X-Career-Token": app.token},
                json.dumps({"title": "Live Studio Note", "raw_text": "Persisted straight to SQLite!", "channel": "voice_note"}).encode(),
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["channel"], "voice_note")

            # Live state reflects immediate persistence without any HTML download
            status, _, body = app.dispatch("GET", "/api/state")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["status"]["counts"]["sources"], 1)

            # Live leak-checked L2 export endpoint returns clean HTML
            status, hdrs, body = app.dispatch("GET", "/api/export?tier=L2&format=html")
            self.assertEqual(status, 200)
            self.assertIn("text/html", hdrs["Content-Type"])
            self.assertNotIn("<script", body.decode("utf-8"))

            # Sensitive entity suggester endpoint works
            status, _, body = app.dispatch("GET", "/api/sensitive/suggest?limit=10")
            self.assertEqual(status, 200)
            self.assertIn("suggestions", json.loads(body))
        finally:
            app.close()

    def test_deduplicated_artifacts_and_sensitive_entity_suggester(self) -> None:
        s = self.vault.ingest_source(
            title="Checkout note",
            raw_text="Unblocked AcmeBank ($14.2M ARR) with shadow evaluation.",
            channel="slack",
        )
        ep = self.vault.upsert_episode(
            episode_id="ep-art",
            title="Checkout overhaul for AcmeBank",
            summary_l1="Resolved false declines for AcmeBank ($14.2M ARR) alongside Devon Park.",
            source_refs=[s["id"]],
        )
        # Sensitive term suggester catches AcmeBank, $14.2M, and Devon Park automatically
        sug = self.vault.suggest_sensitive_terms(limit=20)
        terms = [x["term"] for x in sug]
        self.assertIn("AcmeBank", terms)
        self.assertIn("$14.2M", terms)

        # Deduplicated binary artifact storage (same bytes stored once)
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfake"
        a1 = self.vault.add_artifact(episode_id=ep["id"], data=png_bytes, media_type="image/png", title="UI Shot", share_l2=False, share_l3=False)
        a2 = self.vault.add_artifact(episode_id=ep["id"], data=png_bytes, media_type="image/png", title="UI Shot Dup", artifact_link_id="art-2", share_l2=True, share_l3=False)
        self.assertEqual(a1["sha256"], a2["sha256"])
        self.assertEqual(self.vault.conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)

        # Clean L2 export embeds ONLY share_l2=True artifact
        self.vault.set_tier_projection(episode_id=ep["id"], tier="L2", title="Enterprise Checkout", summary="Resolved false declines safely.", approved=True)
        out = export_vault(self.vault, tier="L2", fmt="html")
        self.assertIn("data:image/png;base64,", out["content"])
        self.assertIn("UI Shot Dup", out["content"])
        self.assertNotIn("UI Shot<", out["content"])

        # Studio serves artifact bytes over /api/artifact/<sha256>
        app = StudioApp(self.db_path)
        try:
            st, hdrs, raw = app.dispatch("GET", f"/api/artifact/{a1['sha256']}")
            self.assertEqual(st, 200)
            self.assertEqual(hdrs["Content-Type"], "image/png")
            self.assertEqual(raw, png_bytes)
        finally:
            app.close()

    def test_browser_docx_upload_triage_knowledge_graph_and_multi_provider_api(self) -> None:
        # 1. Build a minimal valid .docx in memory (pure stdlib)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>Built multi-tenant webhook circuit breaker in Go.</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>Eliminated noisy-neighbor outages across customer tiers.</w:t></w:r></w:p>'
                '</w:body></w:document>',
            )
        docx_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        app = StudioApp(self.db_path)
        try:
            hdrs = {"Content-Type": "application/json", "X-Career-Token": app.token}
            st, _, body = app.dispatch("POST", "/api/ingest/upload", hdrs, json.dumps({
                "filename": "maya_resume.docx", "content_base64": docx_b64, "channel_hint": "auto",
            }).encode())
            self.assertEqual(st, 200)
            up = json.loads(body)
            self.assertEqual(up["importer"], "docx_upload")
            src_id = up["items"][0]["id"]
            self.assertEqual(up["items"][0]["channel"], "resume")

            # Create episode with capability & tags (not yet linked to docx source)
            self.vault.upsert_episode(
                episode_id="webhooks",
                title="Multi-tenant webhook circuit breaker in Go",
                summary_l1="Built multi-tenant webhook circuit breaker eliminating noisy-neighbor outages across customer tiers.",
                decisions=["Capped per-destination concurrency."],
                tags=["distributed-systems", "go"],
                capabilities=[{"name": "Go", "kind": "tool", "application": "Webhook worker rewrite"}],
            )

            # Triage matches unlinked docx to 'webhooks' episode
            st, _, body = app.dispatch("GET", "/api/inbox/triage")
            self.assertEqual(st, 200)
            triage = json.loads(body)
            self.assertEqual(triage["attach_candidates"][0]["source_id"], src_id)
            self.assertEqual(triage["attach_candidates"][0]["suggested_episode_id"], "webhooks")

            # 1-click link attaches source to episode
            st, _, body = app.dispatch("POST", "/api/episodes/link", hdrs, json.dumps({
                "episode_id": "webhooks", "source_ids": [src_id],
            }).encode())
            self.assertEqual(st, 200)
            self.assertIn(src_id, json.loads(body)["source_refs"])

            # Knowledge graph aggregates capabilities, themes, and decisions
            st, _, body = app.dispatch("GET", "/api/knowledge")
            self.assertEqual(st, 200)
            kg = json.loads(body)
            self.assertEqual(kg["totals"]["capabilities"], 1)
            self.assertEqual(kg["capabilities"][0]["name"], "Go")
            self.assertEqual(kg["totals"]["decisions"], 1)

            # Proxy rejects insecure non-localhost HTTP URLs
            st, _, body = app.dispatch(
                "POST", "/api/llm/proxy", {**hdrs, "X-LLM-Key": "test"},
                json.dumps({"provider": "openai", "base_url": "http://evil.example.com/v1", "user_prompt": "hi"}).encode(),
            )
            self.assertEqual(st, 400)
            self.assertIn("https://", json.loads(body)["error"])

            # Anchored claim via browser API
            st, _, body = app.dispatch("POST", "/api/claims", hdrs, json.dumps({
                "statement": "Eliminated noisy-neighbor outages",
                "episode_id": "webhooks",
                "kind": "fact",
                "status": "supported",
                "evidence_quotes": [{"source_id": src_id, "quote": "Eliminated noisy-neighbor outages"}],
            }).encode())
            self.assertEqual(st, 200)
            self.assertEqual(len(json.loads(body)["anchors"]), 1)

            # Batch sanitize L2 + inline static preview
            st, _, body = app.dispatch("POST", "/api/tier/batch-sanitize", hdrs, json.dumps({"tier": "L2"}).encode())
            self.assertEqual(st, 200)
            self.assertIn("webhooks", json.loads(body)["saved"])

            st, resp_hdrs, html_bytes = app.dispatch("GET", "/api/export?tier=L2&format=html&inline=true")
            self.assertEqual(st, 200)
            self.assertNotIn("Content-Disposition", resp_hdrs)
            self.assertIn("Multi-tenant webhook", html_bytes.decode("utf-8"))
        finally:
            app.close()

        # 2. Verify multi-provider payload building & response parsing
        u1, h1, p1 = build_provider_request(provider="anthropic", model="claude-3-5-sonnet", api_key="k", system_prompt="sys", user_prompt="hi")
        self.assertIn("anthropic.com", u1)
        self.assertEqual(h1["x-api-key"], "k")
        self.assertEqual(extract_provider_text("anthropic", {"content": [{"type": "text", "text": "hello"}]}), "hello")

        u2, _, p2 = build_provider_request(provider="gemini", model="gemini-2.5-flash", api_key="gkey", system_prompt="sys", user_prompt="hi")
        self.assertIn("gemini-2.5-flash:generateContent?key=gkey", u2)
        self.assertEqual(extract_provider_text("gemini", {"candidates": [{"content": {"parts": [{"text": "gem"}]}}]}), "gem")

        u3, h3, _ = build_provider_request(provider="openai", model="gpt-4o-mini", api_key="okey", system_prompt="sys", user_prompt="hi")
        self.assertEqual(h3["Authorization"], "Bearer okey")
        self.assertEqual(extract_provider_text("openai", {"choices": [{"message": {"content": "oa"}}]}), "oa")

    def test_deterministic_gap_audit_and_self_deepening_signals(self) -> None:
        # 1. Declare 2 MCP work channels (1 unscanned!) + 2 roles (1 empty!), 1 long unlinked doc, and 1 thin episode with legalese in L2
        self.vault.upsert_channel_scan(
            channel="slack", label="Slack", access_method="mcp", status="scanning",
            date_range_covered="2025-2026", queries_run=["from:@me"], remaining_notes="Still need 2023-2024 threads",
        )
        self.vault.upsert_channel_scan(
            channel="notion", label="Notion", access_method="mcp", status="declared",
        )
        r1 = self.vault.upsert_role(role_id="r-curr", title="Staff Engineer", organization="ClearLedger", start_date="2023-07", is_current=True)
        self.vault.upsert_role(role_id="r-prev", title="Senior Engineer", organization="RelayGrid", start_date="2020-01", end_date="2023-06")
        self.vault.ingest_source(
            title="Long Unlinked Postmortem",
            raw_text=("Detailed production postmortem covering queue partitioning, tail latency, and incident recovery. " * 18),
            channel="doc",
            event_date="2024-11-02",
        )
        ep = self.vault.upsert_episode(
            episode_id="ep-thin",
            role_id=r1["id"],
            title="Short thin story",
            summary_l1="Built a thing.",
            importance=2,
        )
        self.vault.set_tier_projection(
            episode_id=ep["id"],
            tier="L2",
            title="Short thin story",
            summary="The selected record establishes that a system was built, though this does not constitute verification.",
            approved=True,
        )

        gaps = self.vault.audit_gaps()
        self.assertEqual(len(gaps["stages"]), 5)
        self.assertIn("calendar_and_transcripts", gaps["channel_coverage"])
        self.assertEqual(gaps["summary"]["unscanned_channels_count"], 2)
        self.assertEqual(gaps["next_actions"][0]["id"], "unscanned_channels")
        self.assertEqual(gaps["summary"]["empty_roles_count"], 1)
        self.assertEqual(gaps["role_gaps"][0]["id"], "r-prev")
        self.assertEqual(gaps["summary"]["substantive_unlinked_count"], 1)
        self.assertEqual(gaps["summary"]["thin_episodes_count"], 1)
        self.assertIn("decisions", gaps["thin_episodes"][0]["missing"])
        self.assertIn("outcome", gaps["thin_episodes"][0]["missing"])
        self.assertEqual(gaps["summary"]["legalese_hits_count"], 1)
        self.assertIn("selected record establishes", gaps["legalese_hits"][0]["phrases"])
        self.assertTrue(gaps["deepening_prompt"])
        initial_score = gaps["depth_score"]

        # 2. Verify Studio /api/gaps + /api/channels and MCP career_audit_gaps + career_log_channel_scan
        app = StudioApp(self.db_path)
        try:
            st, _, body = app.dispatch("GET", "/api/gaps")
            self.assertEqual(st, 200)
            self.assertEqual(json.loads(body)["depth_score"], initial_score)
            st, _, body = app.dispatch(
                "POST", "/api/channels", {"Content-Type": "application/json", "X-Career-Token": app.token},
                json.dumps({"channel": "github", "label": "GitHub", "access_method": "mcp", "status": "scanned"}).encode(),
            )
            self.assertEqual(st, 200)
            self.assertEqual(json.loads(body)["status"], "scanned")
        finally:
            app.close()

        mcp_l1 = CareerMCPServer(self.db_path, tier="L1", read_write=True)
        try:
            resp = mcp_l1.handle_request({
                "jsonrpc": "2.0", "id": 9, "method": "tools/call",
                "params": {"name": "career_audit_gaps", "arguments": {}},
            })
            self.assertEqual(resp["result"]["structuredContent"]["depth_score"], initial_score)
            resp_ch = mcp_l1.handle_request({
                "jsonrpc": "2.0", "id": 10, "method": "tools/call",
                "params": {"name": "career_list_channels", "arguments": {}},
            })
            self.assertEqual(len(resp_ch["result"]["structuredContent"]["channels"]), 3)
        finally:
            mcp_l1.close()

        # 3. Closing legalese + enriching the thin story increases the objective depth score
        self.vault.upsert_episode(
            episode_id=ep["id"],
            role_id=r1["id"],
            title="Multi-tenant webhook isolation",
            summary_l1="When noisy-neighbor bursts stalled checkout webhooks across enterprise tenants, I redesigned worker scheduling with per-tenant circuit breakers and dead-letter lanes, cutting p99 delay by 68%.",
            decisions=["Capped per-tenant concurrency before scaling fleet size."],
            shared_credit_l1="Paired with SRE on alert routing.",
            outcome_l1="Cut p99 webhook delay 68% and eliminated noisy-neighbor pages.",
            importance=3,
        )
        self.vault.set_tier_projection(
            episode_id=ep["id"],
            tier="L2",
            title="Multi-tenant webhook isolation",
            summary="Redesigned webhook scheduling with per-tenant circuit breakers alongside SRE, cutting p99 delay 68% and eliminating noisy-neighbor outages.",
            approved=True,
        )
        gaps_after = self.vault.audit_gaps()
        self.assertEqual(gaps_after["summary"]["legalese_hits_count"], 0)
        self.assertGreater(gaps_after["depth_score"], initial_score)


if __name__ == "__main__":
    unittest.main()
