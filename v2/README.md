# Career Context AI v2

**Replace the low-throughput resume bottleneck with a local-first career knowledge database built by your own AI agent across your live work channels.**

Resumes compress years of real decisions, trade-offs, prototypes, and cross-functional work into 20 generic bullets—losing almost all signal while still making it awkward to share context without leaking confidential company details.

**Career Context AI v2** is designed around how people actually work today:
1. **Map your real work channels & scan via your own MCP connectors:** Connect your AI agent (Claude, ChatGPT/Codex, Cursor, Antigravity, etc.) to the MCP servers for the channels where your work actually lives—**Slack, Notion, Google Docs/Drive, GitHub, Linear/Jira, Gmail, Calendar**, plus **LinkedIn, X, Substack**, and local files. Your agent maps every channel you work on into a **Channel Scan Ledger**, runs systematic time-sliced sweeps into a local SQLite vault (`L0`/`L1`), and tracks what date ranges and channels remain unscanned. *(Manual drag-and-drop file upload in the browser Studio is included as an offline fallback for resumes and local exports.)*
2. **Drive depth automatically (`audit-gaps`) instead of nagging your AI *"what else did I miss?"*:** A deterministic coverage & quality engine scores your vault (`0–100`) and flags unscanned MCP channels, empty career roles, long unlinked docs, unwritten evidence clusters, thin stories, flat story hierarchies, and courtroom-style AI phrasing—feeding an explicit self-deepening loop back to both you and your agent.
3. **Share at the exact granularity you choose (`L2` / `L3`):** Keep your full candid reality privately in `L0`/`L1`, and project **confidential-safe overviews (`L2`)** or **public summaries (`L3`)** that are deterministically leak-checked against your sensitive terms registry, exported as tiny zero-JS static HTML/Markdown/Resume/JSON files, or exposed to another agent via a read-only MCP endpoint.

---

## Trust & Privacy Model (Read Before Connecting Work Channels)

- **100% local vault, BYO-LLM inference:** Your SQLite database (`career.sqlite`) stays strictly on your own machine—there are zero hosted Career Context servers and zero telemetry. However, **local storage does not make an LLM session local**: whatever your agent reads from Slack/Notion/Docs is sent to your chosen LLM provider during the session.
- **Use an LLM you trust with training disabled:** Ideally run Career Context AI with an LLM provider and plan that **does not train on your data** (e.g., zero-data-retention API, Team/Enterprise plans with training turned off, or local models), and only connect channels and workspaces you are authorized to access.
- **Hard deterministic leak protection on sharing:** Every `L2`/`L3` save, static export, and read-only MCP call is deterministically checked for registered sensitive terms (exact + case variants), emails, `sk-`/`ghp_` tokens, Slack `#channels`, and unapproved visuals. Exported static HTML contains **zero JavaScript** and enforces `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:;`.

---

## How the Process Works End-to-End

```text
1. Channel Discovery ("What are all the channels you communicate & work on?")
        │  Log Slack, Notion, Google Docs, GitHub, Linear, LinkedIn, X, Substack...
        ▼
2. Systematic Live MCP Sweep  ──►  L0 Raw Vault (local career.sqlite + FTS5/semantic)
        │  Time-sliced queries logged in Channel Scan Ledger (offline uploads as fallback)
        ▼
3. L1 Private Synthesis + Mandatory `audit-gaps` Self-Deepening Loop
        │  Catches unscanned channels, empty roles, long unlinked docs, thin stories,
        │  flat Flagship ranking & courtroom legalese BEFORE asking "anything else?"
        ▼
4. Granularity & Leak-Checked Sharing (L2 Confidential-Safe / L3 Public)
        │  Static zero-JS HTML / Resume / Markdown / JSON  OR  Read-only L2 MCP server
        ▼
5. Live Local Tempo Studio (`http://127.0.0.1:8765/`)
           Review, edit stories, inspect Deepening Radar & Channel Ledger, preview shares
```

---

## Granularity Tiers (`L0`–`L3`)

| Tier | Audience | What Lives Here | Exported? |
|---|---|---|---|
| **L0 — Raw Vault** | Only you & your private local assistant | Verbatim items scanned via MCP or uploaded offline (Slack threads, Notion pages, Docs, PRs, CSVs, transcripts). | **Never** |
| **L1 — Private Synthesis** *(default)* | Your private career DB | Candid stories, real customer/coworker names, exact metrics, shelved prototypes, failures, contradictions, screenshots. | Private backup only |
| **L2 — Confidential-Safe Overview** | Hiring managers, advisors, external AI agents | Concrete problems, trade-offs, decisions, shared credit, generalized scope/metrics, approved visuals. | **Hard leak-checked** |
| **L3 — Public Summary** | Public profile, resume, intro bio | Crisp public highlights and explicitly approved public links. | **Hard leak-checked** |

---

## Quick Start

Zero mandatory pip dependencies (Python 3.11+ stdlib only; optional local cached `float16` ONNX semantic search uses `.semantic-model`).

### 1. Run With Your Trusted Agent + Connected MCP Servers (Primary Workflow)
1. Connect your local Career Context vault as a private read/write MCP server (keeping `career.sqlite` in an untracked folder like `private/`):
   ```powershell
   python -m v2.career mcp private/career.sqlite --tier L1 --rw
   ```
   *(Or let any shell-capable agent invoke `python -m v2.career ...` directly.)*
2. Point your agent (alongside your existing Slack / Notion / Google Drive / GitHub / Linear MCP servers) at **[`v2/SKILL.md`](SKILL.md)** and start with:
   > *"Follow `v2/SKILL.md`. First ask me what channels I communicate and work on, check which MCP connectors we have available, log them in the scan ledger, and systematically scan my work into `private/career.sqlite`—running `audit-gaps` to deepen before stopping."*

### 2. Review, Edit & Share in the Local Browser Studio
```powershell
python -m v2.launch private/career.sqlite --open
```
*(Or with optional local cached semantic search: `.\.venv-semantic\Scripts\python.exe -m v2.launch private/career.sqlite --open`.)*

Inside **`http://127.0.0.1:8765/`**:
- **Studio:** Readiness hero deck, Context Library, Flagship story cards, read-first editorial Portrait & Roles, live **Deepening Radar ("what else have you missed?")**, Knowledge & Skills graph, and Dynamic Career Timeline.
- **My Stories (L1):** Master-Detail Story Workbench with live search/filtering, `Overview` / `Edit Story` / `+ Claim` modes, sliding `Flagship / Core / Proof / Background` prominence picker, and lightbox visual artifacts.
- **Share & Tiers (L2/L3):** Sensitive terms registry (`Scan & suggest`), Master-Detail Tier Studio (`L1 Reference` → side-by-side `L2` & `L3` with `← Prev / Next →` stepping), inline zero-JS HTML preview, and one-click Resume copy / downloads.
- **Vault & Triage (L0):** **Work Channels & MCP Scan Ledger**, instant FTS5 / cached hybrid search, **Triage Unlinked Inbox**, side-by-side Source Reader, and a collapsible `+ Upload / Capture` drawer for offline files.
- **Browser AI (BYO-API):** Optional direct browser connection to OpenAI-compatible / Anthropic / Gemini / Ollama APIs (keys stay strictly in tab `sessionStorage`, never written to SQLite) with one-click **`Deepen what I missed`** RAG prompting.

### 3. Share Read-Only With Another Agent via MCP
```powershell
python -m v2.career mcp private/career.sqlite --tier L2
```
Exposes **only** `career_overview`, `career_list_episodes`, and `career_search` over strictly leak-checked L2 projections—raw L0 sources and sensitive terms are completely inaccessible.

---

## Verify Locally

```powershell
python -m unittest v2/test_v2.py -v
python -m v2.assess
```
