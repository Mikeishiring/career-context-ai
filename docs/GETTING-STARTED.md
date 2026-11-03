# Start with your assistant

Give your assistant [START-HERE.md](../START-HERE.md), the project files, and any latest saved private career-context file. Use an assistant approved for the records you select.

> Follow the career-context starter. Reuse what I have already supplied, check what you can read and save, and help me build one useful account from material I authorize. Preserve shared credit, uncertainty and my corrections. Save progress so we can continue later.

The assistant handles source discovery within permission, investigation, drafting and file operations. You choose access, correct the account and explain what mattered. Rough notes, a resume or one selected record are enough to begin. Missing dates, goals or visuals can stay unknown.

## Get the skill into the host

The complete `skills/career-context-sheet/` folder contains its own starter, instructions, references and tools. A file-capable assistant can package it for a host that accepts skill ZIPs:

```text
python tools/build_skill.py OUTPUT/career-context-sheet.zip
```

Use the host's supported installation or upload route; a project URL alone does not establish that it can read or execute these files. The assistant should check capabilities before asking you to do setup. No source connector, package installation or private-file access is implied by loading the skill.

Core tools need Python 3.11+ and no additional packages. From the extracted skill:

```text
python scripts/start_context.py check
python scripts/start_context.py check PRIVATE/CAREER-CONTEXT.html
```

The check reads only the selected input, makes no network requests and writes no career files. It reports runtime capability, saved continuation freshness and pending corrections. The assistant must separately inspect the host's tools and current permissions; this command cannot certify connector access or local-device saving.

If execution is unavailable, the assistant can still produce a provisional account and continuation in chat. It must say that no validated archive was saved. If a connector is unavailable, start from authorized supplied material. If the host can only offer downloads, those files must be downloaded before they exist on your device.

## A useful first result

The first result is a recognizable account of one piece of work, with shared contributions, known outcomes and meaningful uncertainty. The assistant follows consequential leads and asks only questions the available material cannot answer. A complete career inventory, North Star, writing guide or monthly collection plan is not required.

That first result starts the investigation. The assistant builds a context map, follows useful leads, and revisits the map as it learns more. A full challenge follows that research; factual conflicts are addressed as they appear. Findings, open questions and next reads stay in the same private packet. You should not have to repeatedly ask it to go deeper. Saved context opens on a private overview, with a timeline and the work behind it. At an actual host limit or a consequential missing answer, the assistant saves a qualified draft and an exact continuation. [How the investigation continues](../skills/career-context-sheet/references/investigation-loop.md).

For a new private archive, the assistant can run:

```text
python scripts/start_context.py start PRIVATE/my-context --name "Supplied name" --goal "Supplied purpose"
```

This creates one obvious `CAREER-CONTEXT.html` plus its private `career.sqlite`. It refuses a nonempty workspace. Keep them outside this public repository. This empty archive grants no source or processing permission.

## Read, correct and continue

Existing accounts open for review. Say what should change and choose **Record correction**; you do not need source IDs or replacement prose. The correction is saved as pending, not applied to the account or promoted to verified fact. Your assistant reconciles it with originals, preserves an authorized self-report where appropriate, and leaves unsupported external claims unresolved. Exact wording and source selection remain available in disclosure.

**Add context** lets you add a note or a new purpose. **Save for assistant** downloads one private HTML containing all notes, evidence, memory and resume instructions. Attach it to your approved assistant and say “Continue my career context.” No clipboard step is required. **Copy a continuation brief** is an optional fallback with manual copying when clipboard access is blocked. The offline sheet has no embedded model and does not send messages.

Browser changes are labelled until a private-file download is started. The page cannot confirm that you kept that download or recover edits that were never saved. The assistant records a compact `journey.continuation` in the same packet, including the purpose, next action, unresolved questions and scope notes. Saved authorization is not a grant to a different host.

The checker automatically compares the file's embedded resume metadata with its evidence fingerprint and saved review version. An optional copied brief can also be checked using `--expected-context` and `--expected-session`. A mismatch requires reconciliation or the matching save. A consistent file cannot prove that a later download does not exist; use the latest file you kept.

Investigation, connections, wording and systematic collection are optional activities. The monthly ledger lives under **Plan a systematic collection**. It retains actual read receipts and gaps, but never gates ordinary account use. Finishing an activity returns to private context; Profile is not a required destination.

## Updating and recovery

Give the assistant the latest saved private HTML. It keeps stable IDs, source bytes, review notes, rejected claims and existing views. It checks continuation freshness and reopens only evidence-dependent reviews. [Archive updates and recovery](../skills/career-context-sheet/references/local-archive.md).

```text
python scripts/archive_context.py build PRIVATE/latest-saved.html PRIVATE/my-context --update
python scripts/retrieve_context.py PRIVATE/my-context/career.sqlite --index
```

The database retains historical revisions; removing content from today's view does not erase its history. For research using the optional larger-workspace tools, keep the established workspace too: its tool cursors and research journal cannot be reconstructed from absent records. The continuation should identify that dependency. [Advanced local research](LOCAL-CONTEXT.md).

## Use or share context

Ask for a resume, interview preparation, comparison or introduction when useful. Those are selected uses of the private archive. Profile stays empty until a public draft is requested. Its explicit component selection controls the public download; completing review does not approve publication.

Full HTML, JSON and SQLite contain private evidence and working state. Public Profile and [selected-context exports](../skills/career-context-sheet/references/selected-context.md) exclude private sources, memory, continuation and notes. Selected prose can still be sensitive. Local storage does not make processing by an AI host local. [Storage and privacy](PRIVACY.md).

[First-use and host trial protocol](ONBOARDING-TRIAL.md) distinguishes automated checks, agent trials and observed human use.
