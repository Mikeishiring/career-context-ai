# Career Context AI

> **[Try the 30-second playable experiment](https://mikeishiring.github.io/career-context-ai/)**: see how real work records and a local L2 privacy shutter beat a 1-page resume.

**Build your own local career database with your own AI—then export a clean brief for humans or an exhaustive, leak-checked Context Pack for someone else's AI.**

A standard resume squeezes years of decisions, projects, and trade-offs into twenty bullets. Career Context AI gives you a local SQLite vault, a dual-mode MCP server, and a clean browser front end so you can organize your own career history on your own machine—without connecting to our servers or paying for a hosted service.

---

## Security & Privacy (Plain English)

- **Self-hosted & Bring Your Own AI:** Everything runs locally on your machine. Nothing connects to our servers, anyone else's career vault, or anyone else's API key. You use your own AI assistant (Claude, ChatGPT/Codex, Cursor, Gemini, Antigravity, or local Ollama) and your own workspace tools.
- **Local storage vs. LLM inference:** Your SQLite file (`career.sqlite`) stays strictly on your disk (`.gitignore` blocks `*.sqlite*`, `private/`, `sources/`, `.env`). However, whatever your assistant reads from Slack, Notion, or Docs is sent to your chosen LLM provider during the session—so **use an LLM provider and plan you trust with model training disabled / zero-data-retention**, and only scan channels you are authorized to read.
- **Hard local leak blocking on `L2` and `L3`:** Before any `L2` or `L3` projection is saved, exported, or served over read-only MCP, local Python checks block any registered sensitive term (client names, internal revenue/metrics, coworker names, proprietary rules), emails, `sk-`/`ghp_` tokens, Slack `#channels`, and unapproved screenshots.
- **Zero-JavaScript static exports:** Exported HTML files ship with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:;` and contain zero JavaScript.

---

## Confidentiality Tiers (`L0`–`L3`) + Reader Depth (Succinct vs. Exhaustive)

Confidentiality (**what is safe to share**) and depth (**human skim vs. AI reader**) are separate choices:

| Tier | What lives here | Exported? |
|---|---|---|
| **L0 — Raw Vault** | Verbatim Slack threads, Notion pages, Calendar events, meeting transcripts, Google Docs, GitHub PRs, and emails indexed locally in SQLite. | **Never** |
| **L1 — Private Working Copy** *(default)* | Your candid roles, stories, real client/coworker names, exact internal figures, shelved prototypes, screenshots, and verbatim quotes. | Private backup only |
| **L2 — Confidential-Safe** | Real problems, decisions, trade-offs, shared credit, and outcomes—with sensitive names and internal numbers generalized and leak-checked. | **Hard leak-checked** |
| **L3 — Public (Open Web)** | Short public summaries and links you are comfortable posting openly. | **Hard leak-checked** |

When exporting **`L2`** or **`L3`**, choose the format for who is reading it:
- **For Humans (Succinct):** `L2 Visual Brief (HTML)`, `L3 Public Page (HTML)`, or `1-Page Resume (MD)`.
- **For Someone Else's AI (Exhaustive, Leak-Checked):** **`L2 AI Context Pack (Markdown or JSON)`**—built specifically to hand directly to a recruiter's or hiring manager's AI (or expose via a read-only `L2` MCP server). Unlike a 1-page resume, an AI reader benefits from complete, well-structured detail across all leak-checked stories, decisions, shared credit, roles, and skills so it can answer nuanced questions without guessing or hallucinating.

---

## The 5 Stages

1. **Scan Channels (`L0`):** Connect your own AI assistant and MCP servers (**Slack, Notion, Google Calendar, Meeting Transcripts like Granola/Gong/Fireflies/Zoom, Google Docs, GitHub, Linear/Jira, Gmail, LinkedIn, X, Substack**) and pull authorized history into local `career.sqlite`.
2. **Roles & Private Stories (`L1`):** Group raw material under your actual roles and write private `L1` stories with concrete decisions, who helped, honest outcomes, visuals, and verbatim source quotes.
3. **Check Gaps (`audit-gaps`):** Run the local gap check (`python -m v2.career audit-gaps` or MCP `career_audit_gaps`) to see half-scanned channels, roles with zero stories, long unlinked docs, and thin stories—so you don't have to keep asking your AI *"what else did I miss?"*.
4. **Set `L2` / `L3` & Block Sensitive Terms:** Register client names, internal metrics, and coworker names to block; mark your top 4–6 stories as Flagship; write clean `L2` and `L3` versions.
5. **Export & Hand Off:** Export a succinct brief for a human, download an exhaustive **L2 AI Context Pack** (`.md` / `.json`) to drop into someone else's AI, or run a local read-only `L2` MCP server.

---

## Quick Start

You need **Python 3.11 or newer** and nothing else: no packages to install, no account, no API key.

### 1. Look around with sample data
```powershell
git clone https://github.com/Mikeishiring/career-context-ai.git
cd career-context-ai
python -m v2.launch --demo --open
```
This opens the Studio in your browser on a fictional sample vault. Nothing is saved to your own vault.

### 2. Start your own vault
```powershell
python -m v2.launch --open
```
The first run creates `career.sqlite` in a `.career-context` folder in your home directory, outside any git repository, and opens the Studio. Pass a path instead (for example `python -m v2.launch private/career.sqlite --open`) if you want the file somewhere else; `private/` is gitignored here.

Open the address the launcher prints rather than the `v2/ui.html` file itself: the page reads your vault through that local server.

### 3. Let your own AI fill it
In the Studio, **Overview → Work channels → Copy MCP JSON** gives you a ready-made MCP entry for your assistant, with the right paths for your machine. Or start the private read/write MCP server yourself:
```powershell
python -m v2.career mcp private/career.sqlite --tier L1 --rw
```
Give your assistant [`SKILL.md`](SKILL.md) (or [`v2/SKILL.md`](v2/SKILL.md)) alongside your existing Slack / Notion / Calendar / Transcripts / Docs / GitHub MCP servers:
> *"Follow `SKILL.md`. First ask what channels I work on, check which MCP connectors are active, log them in `career_log_channel_scan`, scan my work into my career vault, and run `career_audit_gaps` to close gaps before stopping."*

### 4. Review, edit and export in the Studio
Opens **`http://127.0.0.1:8765/`** directly over your local SQLite file:
- **Overview:** A stage strip with your vault's live counts, the `L0 → L3` tier scene (one record read at four distances), and the work-channel ledger.
- **Studio:** Flagship stories, readiness progress, and the depth score with its four parts and open gaps.
- **Experience:** Editorial profile, Master-Detail Roles workbench (see stories per role and `0`-story gaps), Timeline, and Skills.
- **Stories:** Master-Detail `L1` workbench (`Overview` / `Edit Story` / `+ Claim`, sliding `Flagship / Core / Proof / Background` selector, visual lightbox).
- **Share:** Sensitive terms registry, `L2 / L3` Tier Studio, succinct human exports (`HTML` / `Resume`), and exhaustive **AI Context Packs** (`agent_pack` Markdown / `agent_json` + read-only `L2` MCP command).
- **Vault:** MCP scan ledger, FTS5/hybrid search, inbox triage, source reader, and offline file upload drawer.
- **AI:** Optional direct BYO-API helper (keys stay strictly in tab `sessionStorage`, never written to disk).

### 5. CLI exports and a read-only MCP server for someone else's agent
```powershell
# Succinct human brief (zero-JS static HTML)
python -m v2.career export private/career.sqlite --tier L2 --format html --out career-l2.html

# Exhaustive leak-checked AI Context Pack for someone else's AI
python -m v2.career export private/career.sqlite --tier L2 --format agent_pack --out career-l2-ai-pack.md

# Read-only leak-checked MCP server for an external agent
python -m v2.career mcp private/career.sqlite --tier L2
```

---

## Verify Locally

```powershell
python -m unittest v2/test_v2.py -v
python -m v2.assess
```
