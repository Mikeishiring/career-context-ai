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

## Keep the database

Once the agent has prepared a context packet, it can build the archive:

```sh
python skills/career-context-sheet/scripts/archive_context.py build ../my-input/context.json ../my-context
python skills/career-context-sheet/scripts/archive_context.py search ../my-context/career.sqlite "project"
```

Open `../my-context/CAREER-CONTEXT.html`. Keep `career.sqlite` private: it retains selected sources, images and past revisions. Use `build --update` for later revisions. Removing something from the current view does not erase earlier revisions. [Archive updates and recovery](../skills/career-context-sheet/references/local-archive.md).

## Read and correct it

The HTML brings work accounts, a timeline and interview preparation into one file. Search for work or follow a skill to its supporting accounts. The optional guided path (`--guided`) supports review, deeper research, writing in your voice and practice.

Give the agent your corrections and the latest saved HTML when updating it. Preserve account IDs, original excerpts, shared credit and unknowns. Use **Save full HTML** to carry browser edits into the next session; unsaved changes are not available to another agent.

For interrupted research, also supply the saved private research state and ask it to resume from the next-read queue. Without that state, it can use the HTML's selected evidence but cannot recover every earlier research step.

## Adapt and share a selection

Supply your purpose, audience and a writing sample or style guide. The skill includes guides for [resumes](../skills/career-context-sheet/references/resume.md), [introductions](../skills/career-context-sheet/references/introductions.md), [interviews](../skills/career-context-sheet/references/interview-prep.md) and [role comparisons](../skills/career-context-sheet/references/role-comparison.md).

- **Preview text** shows what **Copy for an agent** will copy. Choose all accounts, visible results or one account. Source excerpts are optional; attribution and limits remain.
- **Save full HTML** and **Download full JSON** retain the complete context packet, including selected sources. Selected image bytes remain in the HTML. Treat these as private working files.
- **Export public HTML** exports the separately authored Profile draft. Review that draft for confidential details before sharing. A label does not anonymize real work.

The archive and rendering tools run locally. An AI host may receive the material you supply to it. [Privacy and storage](PRIVACY.md).

## Render an existing packet

From the full repository:

```sh
python career_context.py demo ../career-context-demo.html
python career_context.py render ../my-context/context.json ../my-context/career-context.html
```

From the extracted skill folder:

```sh
python scripts/render_context.py ../my-context/context.json ../my-context/career-context.html
```

Existing HTML is also valid input. Both render commands preserve existing output unless you add `--force`; malformed input leaves the old file intact. Follow the [context format](../skills/career-context-sheet/references/format.md). Replace fictional content completely and omit `synthetic` or set it to `false` for real material.

For larger selected exports, the optional [local research tools](LOCAL-CONTEXT.md) add scoped source access and resumable research. They are separate from the standalone skill.
