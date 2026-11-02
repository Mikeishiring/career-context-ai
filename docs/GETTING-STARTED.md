# Your first career-context sheet

Start with one piece of work: what was happening, what you did, who else contributed and what happened next. Rough notes are enough. Missing dates, metrics and outcomes can stay unknown.

## Use the complete skill

The `skills/career-context-sheet/` folder contains the instructions, research references, renderer and HTML template. Keep those files together.

From the downloaded project, create the standalone bundle:

```sh
python tools/build_skill.py ../career-context-sheet.zip
```

You need Python 3.11 or later. No packages are required. On macOS/Linux, use `python3` if needed; on Windows, `py -3` may be available.

| Host | Setup |
|---|---|
| Codex | Place the extracted `career-context-sheet` folder under `~/.agents/skills/` or a project's `.agents/skills/`, then invoke `$career-context-sheet`. [Official setup](https://learn.chatgpt.com/docs/build-skills). |
| Claude | Upload the ZIP through **Customize > Skills**. Code execution and file creation must be enabled. [Official setup](https://support.claude.com/en/articles/12512180-use-skills-in-claude). |
| Another agent | Give it the extracted folder and ask it to follow `SKILL.md`. It needs file access and Python to render the supplied template. A text-only model can help prepare the account, but cannot run the renderer. |

Host support is separate from output quality. The tests check the extracted renderer and portable file; they do not establish equivalent research quality across models.

## Make your first account

Give the agent selected notes and ask:

> Use the career-context-sheet skill to make one private HTML file from this material. Preserve my decisions, shared credit and uncertainty. Reuse what I have already told you; ask only about missing scope or facts that change the account.

The opening establishes the work, permitted source locations and privacy boundaries once. Keep inputs, working notes and outputs outside the public checkout. Expect a first account, a focused deepening pass and a challenge/consolidation pass. The agent should continue through these in the same session where possible, then ask what the records miss about your experience. The first draft is useful, but it is not a complete account of your career.

The [longer starting prompt](../prompts/START-HERE.md) is available for broader research. Existing material and corrections should carry forward, including your wording when it is selected as an exact account. Review the result before changing its state from draft to reviewed.

The first complete run should connect your stated purpose, meaningful changes and specific work examples, then select the visual evidence that helps explain them. Goals remain distinct from results; an older image cannot prove newer capabilities. Unknown purpose or direction and missing visuals can stay open. No role, industry, promotion or digital work sample is required. A public draft is created only when requested, and its selected content should make sense on its own.

If a session ends early, give the next agent the existing HTML and saved private research state:

> Resume my career context from the saved draft and next-read queue. Reuse checked evidence and my corrections. Follow the highest-value unresolved question, challenge the affected claims, and update the same complete document. Tell me what changed and what remains blocked.

Without saved research state, the agent can resume from the HTML's selected evidence and questions, but should say which earlier research it cannot recover. Missing access should leave a specific next step, not prevent a draft from the material already available. [Flow and stopping rules](FROM-EVIDENCE-TO-STORY.md).

## Read, reuse and update

Open the HTML in a browser. Build context is the main flow. My context contains Timeline, Work and optional Skills; Profile controls what you share. Select a year or period, open related Work, then review the account or investigate a meaningful gap. Practice remains an optional use in the footer. Search for work or choose a skill to narrow the accounts. The **Skills & tools** index opens the related work with its contribution, assistance and limits.

A fresh complete document uses `--guided` by default. Open Build context for the five-step path. **Collect context** maps source locations against months. Set dates and locations, including work email when useful, then give the copied collection task and saved HTML to your coach. The coach reads authorized records in batches and saves receipts and checkpoints. Existing excerpts do not mark a whole month checked; blocked periods remain visible.

**Review this account** opens the matching work account. Keep the original, choose a supported revision for the next update, or leave a correction awaiting evidence. Progress counts accounts reviewed. **Your voice** includes review and deepening annotations and accepts a writing `SKILL.md`, pasted instructions or a sample. Copy the brief to your preferred assistant and paste the result; narrow large briefs to one account. Original wording stays available.

**Profile** is the final tab for a separate public draft. Use **Export public HTML** for that draft alone; check for confidential details before sharing. General accounts of real work should not be labelled synthetic. That label is for newly made demonstrations with no confidential data.

Copying defaults to the visible work. Entering from Timeline or changing a Work filter resets that scope. The export panel shows the current copy scope. Expand it to choose all accounts, visible results or one account, and whether to include source excerpts. **Preview text** shows exactly what **Copy work** copies. If clipboard access fails, the text is selected for manual copying. **Save full HTML** always downloads the complete portable file with filters reset; **Download full JSON** exports the complete packet while selected image bytes remain in the HTML.

Attach the HTML to another agent with a separate request, such as: "Use this context to help me prepare for an interview." The file includes selected source excerpts as well as the visible account; review it before sharing.

To update it, give the existing HTML and corrections to the skill. Keep account IDs, original excerpts, shared credit and uncertainty. Re-rendering the complete file preserves work, timeline, interview preparation, rehearsal notes and embedded images. Reconcile older notebooks before refreshing; do not replace a complete file with an earlier work-only packet.

## Prepare for an interview

Ask the agent to [prepare an interview](../skills/career-context-sheet/references/interview-prep.md) from your career context and any target you have supplied. It gathers authorized context, selects the strongest stories and drafts all six parts, including an introduction, answers, chapters and timelines. Review the result and practise; answer only the important gaps the available material cannot resolve.

**Copy practice prompt** carries one prepared story into your assistant. **Copy preparation prompt** starts from an account that has no prepared story yet. **Copy all preparation** carries the complete prepared draft. Shared credit and limits remain attached. Rehearsal notes save in the browser; use **Save full HTML** to keep a portable copy. Correct the career-context source and ask the agent to regenerate the preparation when facts change. Copy the HTML file itself to move it between devices.

## Render without an agent

From the full project:

```sh
python career_context.py demo ../career-context-demo.html
python career_context.py render ../my-context/context.json ../my-context/career-context.html --guided
```

Prepare personal JSON using [the format](../skills/career-context-sheet/references/format.md). Replace fictional content completely; omit `synthetic` or set it to `false`. That label does not anonymize data.

From a standalone skill, run its renderer directly:

```sh
python scripts/render_context.py ../my-context/context.json ../my-context/career-context.html --guided
```

Resolve that script from the extracted skill folder. Existing HTML is also valid input. Both entrypoints preserve an existing output unless you add `--force`; malformed input leaves the old file intact.

## Keep a local database

The agent can create the database and HTML together from the context it has prepared:

```sh
python skills/career-context-sheet/scripts/archive_context.py build ../my-context/career-context.html ../my-context
python skills/career-context-sheet/scripts/archive_context.py search ../my-context/career.sqlite "project"
```

Open `../my-context/CAREER-CONTEXT.html`. Keep `career.sqlite` private; it contains selected sources, images and historical revisions. Use `build --update` to retain corrections in the same database. The [archive guide](../skills/career-context-sheet/references/local-archive.md) explains recovery and retention.

## Create a resume

Give the agent your context plus any target and reference resume. Ask it to follow the [resume guide](../skills/career-context-sheet/references/resume.md) and produce the populated draft. It adapts section order and wording to your experience, preserves evidence links, and does not invent missing titles or dates. The HTML includes a private evidence review, print/PDF layout and plain-text download. Review the printed/text version before using it; those exports omit the underlying evidence.

## Larger source collections

The full repository also provides [local context setup](LOCAL-CONTEXT.md) and an optional research MCP server for selected exports. It adds saved source boundaries, research state and a depth review. These components are not needed to create or read a sheet and are not included in the standalone bundle.

[Privacy and storage](PRIVACY.md) explains what is retained and what your chosen model receives.

Copy all accounts or select one; private source excerpts are excluded from copied text unless selected. Attribution and limits remain. Full HTML and JSON always include all selected sources. Optional links lead to separately delivered local files.

In Profile, use **Choose what to share** to include or withhold your overview, North Star, direction, work examples, deeper context, progression periods and work samples. **Download selected profile** exports that selection. Included details remain in the file when collapsed; this creates a local file, not revocable access. Unselected drafts survive full private saves; opening Profile does not copy your private context overview. Newly added components start unselected.

In **Edit → Work samples**, add screenshots or HTTPS video links. New media starts unselected. Add a useful image description and any needed caption or credit, then select it in **Choose what to share**. Selected screenshots are embedded in the download; video links open the external site when clicked. Unselected media stays in your private working file.
