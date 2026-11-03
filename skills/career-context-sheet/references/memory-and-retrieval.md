# Private evidence memory

Keep consequential assertions and rejected interpretations in the optional `memory` field of the private `career-context/v1` packet. It travels through full HTML/JSON and SQLite revisions. It is excluded from public Profile and selected-context exports, including the selected-context MCP server. No memory field grants access, retention or publication permission.

`memory` has `schema: career-memory/v1` and `claims` (at most 4096). Each claim requires:

| Field | Contract |
|---|---|
| `id` | Stable safe ID, distinct within memory. Preserve on correction. |
| `statement` | Exact assertion or proposed interpretation, up to 6000 characters. Keep material qualifications in this wording. |
| `kind` | `fact`, `self_report`, `interpretation`, `hypothesis` or `correction`. This is an authored classification, not a machine truth verdict. |
| `status` | `candidate`, `supported`, `qualified`, `disputed`, `rejected` or `withdrawn`. Supported/qualified claims require evidence. Hypotheses cannot be marked supported/qualified without explicit reclassification. |
| `accountIds` | Resolving account IDs, or an empty list for unassigned research. |
| `evidence` | Exact anchors to retained sources; may be empty for a candidate or rejected interpretation. |

Optional fields: `counterEvidence` (anchors), `aliases` (up to 30 search phrases), `rationale`, `nextQuestion`, and `relations` (`{claimId, type}`, where type is `supports`, `qualifies`, `contradicts` or `supersedes`). Interpretations, hypotheses, corrections and disputed/rejected/withdrawn claims require a rationale. Relations describe authored reasoning, not automatically established causal links. Read incoming corrections as well as outgoing references.

Optional `attributions` preserve distinct actors and action states. Each has `actor`, `action`, `state` (`offered`, `requested`, `planned`, `in_progress`, `completed`, `reported`, `unknown`) and nonempty exact `evidence`. Do not upgrade an offered action to completion while rewriting it. A valid anchor does not establish that the actor/state interpretation is sound.

An anchor is `{sourceId, sourceSha256, start, end, quote}`. The hash is SHA-256 of the retained source's UTF-8 `content`; offsets are zero-based Unicode code points, end exclusive. Validation checks both hash and exact substring. Use the helper to create anchors rather than inventing offsets or hashes. Source revisions that invalidate an existing anchor must be preserved as a distinct source ID if their original claims remain; link the later correction rather than erasing old evidence. A source referenced only by memory is valid. Unrelated, unreferenced source dumps remain invalid.

Keep source facts and interpretations separate from browser review notes. A chosen wording revision remains unverified until reconciled against evidence. A person's recollection can become a dated `person_account` source; it does not automatically establish every external result. Rejected claims stay searchable with their status and reason. Mark withdrawal explicitly rather than silently deleting memory. The explicit removal override remains available for deliberate retention changes; old archive revisions still retain their content.

For a first packet or an anchor repair, use the pure helper while authoring, before full-packet validation. For example, from the skill's `scripts` directory:

```python
from context_memory import anchor
source = {"id": "trial-note", "label": "Selected trial note", "kind": "source_excerpt",
          "content": "Two volunteers tried it with supervision.", "scope": "Fictional example."}
claim = {"id": "trial", "statement": source["content"], "kind": "fact", "status": "qualified",
         "accountIds": [], "evidence": [anchor(source, 0, len(source["content"]))]}
# Add source to packet["sources"] and claim to packet["memory"]["claims"], then validate.
```

Use the selected exact content in place of this fictional example. The retrieval CLI validates the whole packet before reading it; its `--anchor` action is convenient once the packet is valid. Do not invent temporary account links or silently refresh anchors to make a changed source pass: first inspect the change and reconcile the affected claim.

## Browse, search and expand

The same read-only helper accepts JSON, saved HTML or an existing SQLite archive. It makes no network calls and never copies the database. Resolve the script relative to the skill.

```text
python scripts/retrieve_context.py career.sqlite --index --limit 20
python scripts/retrieve_context.py career.sqlite --query "handling ambiguity" --query "unclear ownership"
python scripts/retrieve_context.py career.sqlite --layer claims --query "handoff" --offset 8
python scripts/retrieve_context.py career.sqlite --read claims:handoff --expand
python scripts/retrieve_context.py career.sqlite --read sources:original-decision
python scripts/retrieve_context.py career.sqlite --anchor original-decision --start 0 --end 34
python scripts/retrieve_context.py career.sqlite --revision SAVED_REVISION_HASH --index
```

The index lists compact summaries, periods, aliases, claim states and links with pagination. Default search requires all whitespace-separated terms of one query somewhere in a record's searchable fields; repeated queries are alternatives. Matching title/label/alias terms rank higher; this is lexical ranking, not semantic confidence. `--mode literal` preserves exact phrase/substring search. Terms and literal modes cannot infer synonyms. Use the optional local semantic mode below for different wording. A missed query does not prove missing experience. Rejected/disputed claims remain in search results, with explicit states.

`--read` returns the complete record. `--expand` follows connected claims in both directions and includes their sources, counterevidence and related accounts. Each related layer is paginated independently through `--limit` and `--offset`; check `nextOffset`. Broader linked accounts provide context and are not proof for every claim. Retained source content contains only the selected original or excerpt; expansion never retrieves an unselected original, follows a URL or widens permissions. Exact sources, attribution evidence and hypothesis states survive expansion.

Default SQLite reads use the current revision. `--revision` deliberately inspects historical context; keep that distinction when answering. Full private HTML is a memory carrier, while ordinary Work copies and selected-context snapshots contain their chosen narrative only. Attach the full private file only within authorized processing scope.

For conversational questions, separate distinct intents into concise queries, including the person's original wording where useful. A comparison may need two account searches; a claim about improvement needs the outcome record and its baseline or correction. Follow `accountIds` to the account and inspect its relevant `sourceRefs` when a claim expansion does not cover the whole question. Read pagination markers before treating a linked set as complete. Choose the reads that could change the answer; do not automatically dump every connected record or impose a fixed research-pass count. A search result about a budget trade-off cannot establish an absent savings amount.

## Local semantic retrieval

Use `--mode hybrid` to combine exact vocabulary with embedding-based reading leads, or `--mode semantic` for embedding ranking alone. Both require an explicitly prepared local model directory. They search only the supplied packet/revision and selected `--layer` values; no connector, URL, original file or neighbouring archive is followed. Source text, queries and embeddings stay in this process. The model has no tools and cannot change permissions or act on instructions in the evidence.

The optional CPU backend uses the pinned [BGE small English v1.5 model](https://huggingface.co/BAAI/bge-small-en-v1.5), with its documented query instruction and CLS pooling. Model and tokenizer hashes are verified before loading. The loader reads verified data bytes, uses no remote model code or hub fallback, and disables ONNX Runtime telemetry. Missing or changed files fail explicitly; the tool never substitutes lexical results while labelling them semantic. This English model is not a validated multilingual search system.

Setup is separate from searching. Installation and the explicit preparation command use the network for packages and approximately 134 MB of public model files; preparation accepts no career input. Reuse a prepared runtime and model where available. From the project root on Windows:

```text
python -m venv .venv-semantic
.venv-semantic/Scripts/python -m pip install -r skills/career-context-sheet/scripts/semantic-requirements.txt
.venv-semantic/Scripts/python skills/career-context-sheet/scripts/semantic_context.py prepare .semantic-model --download
.venv-semantic/Scripts/python skills/career-context-sheet/scripts/retrieve_context.py PRIVATE/career.sqlite --query "outage recovery" --mode hybrid --model-dir .semantic-model
```

For an installed standalone skill, use its `scripts` directory and keep the runtime and model in a separate local tools directory. On macOS/Linux use the environment's `bin/python`. Neither dependencies nor model weights enter the skill bundle. `.venv-semantic` and `.semantic-model` are ignored in this checkout. Ordinary lexical, archive and renderer commands still need no extra packages.

Search embeds source content and selected narrative fields. Generic scope labels, locators, image bytes, dates, isolated actor names and tag lists do not become semantic candidates. Their exact wording remains searchable lexically where already allowed. Every semantic hit gives the actual matched field, Unicode offsets, exact quote and field hash; source-content hits also give a validated evidence anchor. Claim kind/status and links survive ranking, including rejected claims and counterevidence. A match to a claim's rationale or open question is labelled with that field and does not establish the claim.

Text is split into overlapping 224-token windows, so content beyond the first window remains searchable. Each record gets its strongest passage score. Hybrid ranking uses reciprocal rank fusion (`k=60`), preserving lexical hits and paginating only after combination. The default cosine cutoff is `0.5`; `--min-similarity` can adjust it. It is a reading filter, not a probability, support verdict or calibrated relevance guarantee. Similarity can miss negation, ownership or action state; inspect the original and linked counterevidence before using a result.

Vectors exist only in memory and are recomputed from the selected revision. Search writes no cache, archive, HTML or review state, so stale indexes cannot return removed evidence. Repeated queries in one invocation reuse document embeddings. Above 32768 passages the request fails with a narrower-scope instruction rather than silently omitting records. Large archives can therefore be slower than a persistent vector index; such an index is not implemented here.

The fixed fictional five-query check in `tests/fixtures/semantic-retrieval.json` found zero lexical matches, four intended records at rank 1 and all five within rank 3. The intended record for “clarifying authority” ranked third. An initial test demanding rank 1 for every query failed; the quality check now records both measures and requires discovery within three results. This is a small development check, not a general accuracy estimate. The same real-model suite checks late Unicode evidence, current versus historical saved inputs, unchanged files and no Python socket access. Run it with the optional environment and `CAREER_SEMANTIC_MODEL` pointing to the prepared model directory.

The larger `tests/fixtures/realistic-career-history.json` covers eight fictional years, six accounts and 26 initial records. Its 14 queries and intended records were fixed before retrieval. Hybrid search found an intended record within five results in either the source or claim layer for all 14 queries; lexical search did so for one. This means inspecting up to ten candidates across the two layers, not a combined top-five result. Some intended claims rank poorly even when their sources rank first, and generic rationales can outrank specific statements. Excluding rationales and questions reduced discovery to 12 of 14, so they remain searchable. These are development observations, not a career-search accuracy estimate.

Replay the fixture from the project root with the prepared model and Node's `playwright` package available (the browser test uses installed Edge):

```text
.venv-semantic/Scripts/python tools/check_career_workflow.py --model-dir .semantic-model --output OUTSIDE_CHECKOUT/realistic-career-workflow
```

The runner blocks Python sockets and browser HTTP requests, exercises browser review/save/reopen and explicit public selection, and reconciles a later correction through a temporary SQLite archive. It checks rejected claims, original and counterevidence anchors, offered versus completed work, selective review resets, historical revisions and private export boundaries. It retains the first retrieval receipt alongside current results and a portable `CAREER-CONTEXT.html`; its synthetic database is removed afterward. Accounts and corrections in this replay are authored fixture data, so it tests the workflow rather than autonomous extraction from raw records.

A later independent reviewer wrote twelve conversational queries from the packet without seeing the implementation or earlier query results (`tests/fixtures/retrieval-holdout.json`). Of ten answerable questions, the first five source leads contained any required source for nine, but all required sources for only three. Expanding the first three claim leads, with at most eight sources each, provided all required sources for six. Two questions deliberately lack an answer; related hits are not an answerability verdict. These stricter results expose incomplete context in single-pass retrieval. The targets were frozen before evaluation, no ranking parameters were changed, and answer generation was not part of this metric.

Run `tools/check_retrieval_holdout.py --model-dir PREPARED_MODEL --output OUTSIDE_CHECKOUT/holdout.json` from the prepared local Python environment. The report keeps every miss, returned claim status, reading budget and expected caveat. A follow-up assistant can use judgment to reformulate and read linked context; that separate workflow needs its own evidence and must not replace these first-pass results.

## Updates and review dependencies

The private journey stores `reviewBasis.accounts` and `reviewBasis.sources`, maps of IDs to dependency hashes. A rendered page carries the current basis separately. On opening, the page compares each account and its supporting sources/connected claims with its saved basis, including any extra sources cited by a proposed correction. It reopens only affected reviews, preserving drafts, reasons, notes, first wording and coverage receipts.

Changing a global overview or target role can reopen synthesis without resetting account decisions. Retrieval-only aliases do not change account evidence. Current older documents acquire a baseline when rendered; a stale older document without one must reopen its reviews once because the earlier evidence cannot be reconstructed safely. Never refresh stored fingerprints manually to suppress a real change. Global fingerprints for derived resume/interview projections remain conservative; reconcile those outputs when their canonical evidence changes.

The research-server compiler also carries its selected claims, qualifications, saved actor/action states and rejected conclusions into memory. These remain researcher interpretations, with provenance rather than automatic factual certification. Substantive memory changes invalidate the canonical evidence fingerprint; retrieval-only aliases do not. Standalone resume/interview file fingerprints remain conservative and can change on any saved-file edit. Reconcile dependent output before refreshing its fingerprint. Compiler rejections retain their evidence without inventing relations from shared sources; add explicit supported relations when reconciling them with existing accounts.
