# Build your context archive

Keep personal inputs and outputs outside this public repository. Start with notes or records from one piece of work; missing dates and outcomes can stay unknown.

## Give your agent the skill

Use the complete `skills/career-context-sheet/` folder. It contains the instructions, references, renderers and templates. Your agent needs file access and Python 3.11 or later; no additional Python packages are required.

To package that folder for a host that accepts skill ZIPs:

```sh
python tools/build_skill.py ../career-context-sheet.zip
```

Follow your host's skill installation instructions, or give the agent the extracted folder and ask it to follow `SKILL.md`. On macOS/Linux, use `python3` if needed; on Windows, `py -3` may be available.

> Use this skill to build my local context archive. Reuse what I've already told you. Collect from the sources I authorize, preserve original evidence, and distinguish it from interpretation. Keep my decisions, shared credit and uncertainty. Save a searchable database and one HTML file outside this repository.

The agent should draft an account, investigate consequential gaps, then challenge and consolidate it. It should save the evidence and next step when interrupted. You supply corrections and personal meaning; the agent follows up on questions the records can answer. [Research flow and stopping rules](FROM-EVIDENCE-TO-STORY.md).

The first complete run connects your stated purpose, meaningful changes and specific examples, then selects the strongest useful visual evidence. Goals stay distinct from results; an older image cannot prove newer capabilities. Unknown direction and missing visuals can stay open. No role, industry, promotion or digital work sample is required. [Longer starting prompt](../prompts/START-HERE.md).

## Keep the database

Once the agent has rendered the complete HTML, build the archive from that file to retain its review state and images:

```sh
python skills/career-context-sheet/scripts/archive_context.py build ../my-input/career-context.html ../my-context
python skills/career-context-sheet/scripts/archive_context.py search ../my-context/career.sqlite "project"
```

Open `../my-context/CAREER-CONTEXT.html`. Keep `career.sqlite` private: it retains selected sources, images and past revisions. Use `build --update` for later revisions. Removing something from the current view does not erase earlier revisions. [Archive updates and recovery](../skills/career-context-sheet/references/local-archive.md).

## Read and correct it

Fresh complete documents use `--guided` by default. **Build context** is the main flow: plan collection by source location and month, review accounts, resolve meaningful gaps and retain your voice. The coach saves read receipts and checkpoints; existing excerpts do not mark a whole month checked. Blocked periods remain visible.

**My context** contains Timeline, Work and optional Skills. Select a year or period, open related Work, then review an account or investigate a gap. Copying follows the visible Work selection. Optional **Practice** sits in the footer and returns to its source account.

**Review this account** preserves the original, a supported revision or an unresolved correction. Progress counts accounts reviewed. **Your voice** carries those annotations into a bounded writing brief; use your own writing skill or supply a guide or sample. Returned wording stays a private draft.

Give the agent your corrections and the latest saved HTML when updating it. Preserve account IDs, original excerpts, shared credit and unknowns. Use **Save full HTML** to carry browser edits into the next session; unsaved changes are not available to another agent.

For interrupted research, also supply the saved private research state and ask it to resume from the next-read queue. Without that state, it can use the HTML's selected evidence but cannot recover every earlier research step.

## Adapt and share a selection

Supply your purpose, audience and a writing sample or style guide. The skill includes guides for [resumes](../skills/career-context-sheet/references/resume.md), [introductions](../skills/career-context-sheet/references/introductions.md), [interviews](../skills/career-context-sheet/references/interview-prep.md) and [role comparisons](../skills/career-context-sheet/references/role-comparison.md).

- **Preview text** shows what **Copy work** will copy. Choose all accounts, visible results or one account. Source excerpts are optional; attribution and limits remain.
- **Save full HTML** and **Download full JSON** retain the complete context packet, including selected sources. Selected image bytes remain in the HTML. Treat these as private working files.
- In Profile, **Choose what to share** controls the overview, North Star, direction, examples, deeper details, progression periods and work samples. **Download selected profile** includes only the selected content. Collapsed details are still included; this is a local download, not revocable access.

In **Edit → Work samples**, add screenshots or HTTPS video links with useful descriptions, captions and credit. New components start unselected. Selected screenshots are embedded; video links open the external site on click. Withheld media stays in the private file. Review the selected preview and download for confidential details. General accounts of real work are not synthetic; that label belongs to newly made demonstrations without confidential data.

For a structured handoff, [export selected accounts or connect the local MCP server](../skills/career-context-sheet/references/selected-context.md). This keeps the archive separate from the tool using it.

The archive and rendering tools run locally. An AI host may receive the material you supply to it. [Privacy and storage](PRIVACY.md).

## Render an existing packet

From the full repository:

```sh
python career_context.py demo ../career-context-demo.html
python career_context.py render ../my-context/context.json ../my-context/career-context.html --guided
```

From the extracted skill folder:

```sh
python scripts/render_context.py ../my-context/context.json ../my-context/career-context.html --guided
```

Existing HTML is also valid input. Both render commands preserve existing output unless you add `--force`; malformed input leaves the old file intact. Follow the [context format](../skills/career-context-sheet/references/format.md). Replace fictional content completely and omit `synthetic` or set it to `false` for real material.

For larger selected exports, the optional [local research tools](LOCAL-CONTEXT.md) add scoped source access and resumable research. They are separate from the standalone skill.
