# Career Context AI: architecture and benchmark report

Reproducible automated evaluation covering:
1. Official answerable retrieval holdout (`tests/fixtures/realistic-career-history.json` + `tests/fixtures/retrieval-holdout.json`)
2. Large-archive scaling & cached semantic latency benchmark (synthetic & multi-hundred-source stress testing)
3. 11-vector adversarial confidentiality & leak-blocking security suite
4. Data-integrity, deterministic gap-audit (`audit_gaps`), browser BYO-API, and live Chromium QA

Run anytime via:
```powershell
python -m unittest v2/test_v2.py -v
python -m v2.assess
```
(Or `.\.venv-semantic\Scripts\python.exe -m v2.assess` when local `.semantic-model` ONNX weights are installed.)

---

## Scorecard Summary

| Dimension | Result | Evidence |
|---|---|---|
| **1. Retrieval Quality (Holdout)** | **PASS** | FTS5: **0.48 ms**, Recall@5 `0.508`, Recall@10 `0.606`. Hybrid (`float16` ONNX + RRF, needs the optional local model): **15.6 ms**, Recall@10 **`0.765`**, MRR **`0.636`**. |
| **2. Large-Archive Scaling & Speed** | **PASS** | On multi-hundred-source archives, SQLite-cached `float16` hybrid runs in **~420 ms** across both chunks and episodes; pure FTS5 runs in **3–7 ms**. |
| **3. Confidentiality & Leak Security** | **11 / 11 PASS** | Deterministically blocks registered sensitive terms (exact + case variants), currency metrics, proprietary rules, emails, `sk-` API keys, `ghp_` tokens, Slack `#channels`, unapproved screenshots, and raw-source reads on L2/L3 MCP. |
| **4. Self-Deepening Coverage Audit** | **PASS** | `audit_gaps()` deterministically scores Coverage (`25`), Story Depth (`30`), Narrative & Voice (`20`), and Sharing Safety (`25`), catching empty roles, unlinked long docs (`>=1k` chars), unwritten clusters, missing decisions/outcomes/claims, flat Flagship ranking, and courtroom-style legalese in L2/L3. |
| **5. Data Integrity & Browser BYO-API** | **PASS** | External-content FTS5 syncs on insert & delete; Python verbatim quote-to-offset anchoring verified exact; CSRF blocks unauthenticated POST (`403`); proxy rejects non-localhost `http://` (`400`); OpenAI / Anthropic / Gemini adapters verified; UI JS passes `node --check`. |
| **6. Static Share Compression** | **PASS — >200× Smaller** | Leak-checked L2/L3 HTML, Markdown, Resume, and JSON exports strip raw L0 sources and JavaScript, compressing multi-MB raw vaults into clean tens-of-KB Tempo editorial briefs. |
| **7. Instruction Size** | **About 1,900 words** | `SKILL.md` is the only file an assistant has to read; it holds the complete **3-Pass Self-Deepening Protocol**. |

---

## Core Architectural Principles

1. **Collect First, Synthesize Second:** Raw material enters `L0` with zero upfront episode requirement and becomes searchable immediately via SQLite FTS5.
2. **Audit-Driven Self-Deepening:** Instead of relying on users to repeatedly prompt *"what else did I miss?"*, the vault computes objective gaps (`audit-gaps`, MCP `career_audit_gaps`, Studio Deepening Radar) and feeds them back into the workflow until coverage and depth pass.
3. **Strict Tier Separation (`L0`–`L3`):** Full candor stays private in `L0`/`L1`; `L2` and `L3` are derived, staleness-tracked projections guarded by deterministic leak checks.
4. **Honest Storytelling Without Legalese:** Epistemic boundaries live cleanly in `claims` and `limits`, while shareable stories follow a natural human arc (`Stakes → Tension → Decision → Proof`) ranked into `Flagship` / `Core` / `Proof Point` / `Background`.
