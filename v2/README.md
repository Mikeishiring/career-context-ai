# Career Context AI v2

**Replace the low-throughput resume bottleneck with a local-first, BYO-LLM career knowledge database.**

Resumes compress years of real decisions, trade-offs, prototypes, and cross-functional work into 20 generic bullets—losing almost all signal while still making it awkward to share context without leaking confidential company details.

**Career Context AI v2** flips the workflow:
1. **Collect everything privately first (`L0` / `L1`)** across docs, resumes, Slack, Notion, GitHub, LinkedIn, X, Substack, and voice notes—stored locally in a single SQLite vault (`career.sqlite`) with instant FTS5 + optional cached `float16` local semantic search.
2. **Drive depth automatically (`audit-gaps`)** instead of forcing you to repeatedly prompt an LLM *"go deeper, what else did I miss?"*—a deterministic coverage & story-depth engine surfaces uncovered roles, long unlinked docs, unwritten clusters, thin stories, flat story hierarchies, and courtroom-style AI phrasing.
3. **Share cleanly at the exact granularity you choose (`L2` / `L3`)**—deterministically leak-checked against your registered sensitive terms, emails, tokens, and internal `#channels`, exported as tiny zero-JS static HTML/Markdown/Resume/JSON files or served via a read-only MCP endpoint.

Zero hosted servers. Zero telemetry. Zero mandatory pip dependencies (Python 3.11+ stdlib only; optional local ONNX embeddings use `.semantic-model`).

---

## Why This Architecture Works

| Old Failure Mode | How v2 Solves It Foundationally |
|---|---|
| **LLMs stop shallow on pass 1** and make you keep asking *"what else did I miss?"* | **Deterministic Deepening Engine (`audit-gaps` + Studio Deepening Radar)** scores Coverage, Story Depth, Voice Quality, and Sharing Safety (`0–100`), pinpoints exact uncovered roles, long unlinked docs, thin stories, and legalese prose, and powers a mandatory **3-Pass Self-Deepening Protocol** in [`SKILL.md`](SKILL.md). |
| **Resumes flatten everything & hide confidential work** | **4 Explicit Granularity Tiers (`L0`–`L3`)** keep your full candid reality privately in `L0`/`L1`, while `L2` (confidential-safe overview) and `L3` (public summary) generalize sensitive specifics and track `derived_from_sha256` staleness whenever `L1` changes. |
| **Honest AI synthesis turns into robotic legal disclaimers** | **Narrative Hierarchy (`Flagship` / `Core` / `Proof` / `Background`) + Voice Audit** separates epistemic caveats into `claims`/`limits` while keeping L2/L3 stories confident, human, and evidence-backed (`Stakes → Tension → Decision → Proof`). |
| **Download-per-edit HTML fatigue & bloated multi-MB archives** | **Live Localhost Studio (`127.0.0.1`) backed directly by SQLite** with ephemeral CSRF protection, content-addressed deduplicated visual artifacts, Master-Detail workbenches, and tiny leak-checked static exports (tens of KB, zero JS, strict CSP). |
| **Fragile manual hashing/offsets & slow uncached semantic search** | **Strict LLM / Python division of labor:** Python handles SHA-256 hashing, automatic verbatim quote-to-offset anchoring, external-content FTS5 indexing, and SQLite-cached `float16` embeddings. |

---

## Granularity Tiers (`L0`–`L3`)

| Tier | Audience | What Lives Here | Exported? |
|---|---|---|---|
| **L0 — Raw Vault** | Only you & your private local assistant | Verbatim ingested files, threads, transcripts, git logs, CSVs, RSS exports. | **Never** |
| **L1 — Private Synthesis** *(default)* | Your private career DB | Candid stories, real customer/coworker names, exact metrics, shelved prototypes, failures, contradictions, screenshots. | Private backup only |
| **L2 — Confidential-Safe Overview** | Hiring managers, advisors, external AI agents | Concrete problems, trade-offs, decisions, shared credit, generalized scope/metrics, approved visuals. | **Hard leak-checked** |
| **L3 — Public Summary** | Public profile, resume, intro bio | Crisp public highlights and explicitly approved public links. | **Hard leak-checked** |

---

## Quick Start (Browser Studio — No Terminal Workflow Needed)

Launch the local Studio against any private vault path (keep your `.sqlite` file outside any public git repo, e.g. inside `private/` which is gitignored):

```powershell
python -m v2.launch private/career.sqlite --open
```

With optional local cached hybrid semantic search (`.venv-semantic` + `.semantic-model`):
```powershell
.\.venv-semantic\Scripts\python.exe -m v2.launch private/career.sqlite --open
```

Inside the browser Studio (`http://127.0.0.1:8765/`):
1. **Studio:** Hero readiness deck, clickable Context Library, Flagship story cards, read-first editorial Portrait & Roles, **Deepening Radar ("What Else Have You Missed?")**, Knowledge & Skills graph, and Dynamic Career Timeline.
2. **My Stories (L1):** Master-Detail Story Workbench — filterable left story index + focused right sheet with `Overview`, `Edit Story` (with sliding `Flagship / Core / Proof / Background` selector), and `+ Claim` (auto-anchored verbatim quotes).
3. **Share & Tiers (L2/L3):** Sensitive terms registry (`Scan & suggest`), `Auto-Sanitize` or `AI Polish`, focused side-by-side L2/L3 Tier Studio with `← Prev / Next →` stepping, inline zero-JS HTML preview, and one-click Resume copy / downloads.
4. **Vault & Triage (L0):** Drag-and-drop upload (`.docx`, `.md`, `.txt`, LinkedIn CSVs, X `tweets.js`, Substack RSS, Slack/GitHub JSON, or v1 HTML), instant FTS5 / hybrid search, **Triage Unlinked Inbox**, and side-by-side Source Reader.
5. **Browser AI (BYO-API):** Connect OpenAI / OpenRouter / Ollama, Anthropic Claude, or Google Gemini directly from the browser (keys stay strictly in tab `sessionStorage`, never written to SQLite). Includes one-click **`Deepen what I missed`** RAG prompting.

---

## Using With Any Coding Agent or MCP Client

- **Agent Skill:** Point Claude Code, Codex, Cursor, Gemini CLI, or Antigravity at [`v2/SKILL.md`](SKILL.md) — it encodes the full **3-Pass Self-Deepening Protocol** in ~1,100 words.
- **Private Read/Write MCP Server (for your own assistant):**
  ```powershell
  python -m v2.career mcp private/career.sqlite --tier L1 --rw
  ```
  Exposes `career_status`, `career_audit_gaps`, `career_triage_unlinked`, `career_search`, `career_read_source`, `career_ingest_source`, `career_upsert_role`, `career_upsert_episode`, `career_upsert_claim`, `career_add_sensitive_term`, `career_draft_tier`, `career_set_tier`, and `career_leak_check`.
- **External Read-Only MCP Server (for hiring managers or external agents):**
  ```powershell
  python -m v2.career mcp private/career.sqlite --tier L2
  ```
  Exposes **only** `career_overview`, `career_list_episodes`, and `career_search` over strictly leak-checked L2/L3 projections. Raw L0 sources are inaccessible.

---

## Privacy & Safety Guarantees

- **100% local storage:** Your vault lives in a single SQLite file on disk (`.gitignore` blocks `*.sqlite*`, `private/`, `sources/`, `personal/`, `.env`).
- **Deterministic leak blocking:** Every `set-tier`, static export, and L2/L3 MCP call runs the deterministic leak scanner (registered sensitive terms, case variants, emails, `sk-`/`ghp_` tokens, Slack `#channels`, and unapproved visuals).
- **Zero-JS static shares:** Exported L2/L3 HTML files include `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:;` and contain zero JavaScript.
- **Stateless BYO-API proxy:** Local Studio binds strictly to `127.0.0.1`, enforces an ephemeral per-run CSRF token (`X-Career-Token`), rejects insecure non-localhost HTTP proxy URLs, and never persists API keys to disk.

---

## Verify Locally

```powershell
python -m unittest v2/test_v2.py -v
python -m v2.assess
```
