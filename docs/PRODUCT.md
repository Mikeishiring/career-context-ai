# Product contract

Career Context AI helps a person preserve the context behind their work and carry it into a new agent conversation. The reusable product is a skill, a stable context format, a local SQLite archive and deterministic HTML renderers for context, resumes and interview preparation. The full repository also maintains optional research tools and their test evidence.

## Guiding principles

1. Collect context before choosing a story. Retain selected source material separately from interpretation, including unfinished work and contrary evidence. Broad collection stays within the person's authorized scope; unread material remains a gap.
2. Adapt to the person. Purpose, work and voice determine the organization and writing. A resume or interview draft is a view of the archive, not a replacement for it.
3. Keep the archive under the person's control. The core tools store it locally, with no hosted account or archive upload service. AI hosts and source connectors have their own data boundaries; local storage alone does not make model processing local.

## Collection and use

The archive owns source collection, retained evidence, working accounts and rough presentation. A receiving tool owns the purpose-specific use: a search, coaching conversation, resume, comparison or other output. Existing resume and interview helpers remain optional ways to use the archive.

A person-selected `career-context-selection/v1` snapshot is the handoff. It preserves attribution, uncertainty and capability assistance while excluding source bodies, images, broad personal summaries and private working state. A local read-only MCP server can expose that snapshot to the person's agent. It accepts no paths through tool calls and does not refresh a running session from the archive.

A receiving tool must distinguish working accounts from original sources and current preferences. It must not treat review status as independent verification or turn fictional examples into personal evidence. Its existing review and action controls still apply. Reading a selection does not authorize remote retention or any external action.

The full archive stays local. Selected prose may still be sensitive, and the chosen AI host may process it remotely. Each receiving service owns its data policy. See the [handoff contract](../skills/career-context-sheet/references/selected-context.md).

## The experience

Start with selected material, establish missing scope, investigate consequential questions, draft connected work accounts, challenge them, ask for the person's corrections and create one portable HTML sheet. A useful first result can cover one project. A larger archive must not become an intake requirement.

For new context, the first account, focused deepening and challenge/consolidation have distinct purposes. The agent continues between them without repeated user prompts, saves a compact checkpoint and stops when no consequential accessible lead remains or the run is genuinely blocked or limited. Later passes reuse checked evidence; narrow corrections do not restart the whole process. Pass counts and source counts are not completeness scores.

Keep the recognizable parts of the person: voice, personal meaning, decisions, shared contributions, concurrent work, setbacks, corrections and unfinished outcomes. Support the person's own organization and presentation preferences. Simplification removes repeated steps and implementation detail; it must not flatten those accounts into generic achievement bullets.

The supplied visual template is the starting point. Meaningful content is available offline and without JavaScript. Sources, optional detail and exports stay accessible on keyboard and small screens.

The optional guided path keeps six small review activities visible: gather, review, deepen, connect, write and practise. Review starts from retained first wording and collects bullet feedback; completion is not factual approval. Writing uses the person's own style guide or sample through a bounded copy-and-paste brief. Its candidate stays separate from career evidence. The final Profile tab is an explicitly authored public projection with its own allowlisted HTML export. It never exports the private packet, style guide, notes or images, and never treats relabelled confidential data as synthetic.

## Responsibilities

| Part | Owns |
|---|---|
| Agent and skill | Source selection within authorization, research decisions, interpretation, writing and factual follow-up |
| Renderer and format | Valid structure, resolving references, inert source text, self-contained assets and faithful exports |
| Optional research server | Selected-export boundaries, saved evidence, resumable research and process checks |
| Person | Source authorization, personal meaning, corrections and approval to share |

Structural and process checks cannot certify semantic completeness. Keep that limitation in research documentation rather than repeating it throughout the interface.

## Release criteria

- A recipient can extract the skill and render a sheet without the repository, installed packages, an account connection or a network request.
- Updating a sheet preserves IDs, evidence, images, corrections and review state; replacement is explicit.
- Visible prose, copied text and structured context retain the same ownership, chronology, outcomes and uncertainty.
- Source text stays inert in the rendered HTML, and the skill treats it as data. Only named package inputs enter the shareable bundle.
- The core path is concise, with optional research detail disclosed when needed and one succinct work-document trust notice.
- Fresh research trials preserve meaningful decisions, shared credit, contrary evidence and the person's corrections. Compare first results before coaching; report misses, case scope and host separately.
- Rendered checks cover mobile and desktop layout, keyboard access, copy fallback, downloads, reduced motion and offline reading.
- Interview preparation opens as a context-derived draft, with supported initial answers and only consequential gaps for the person. Blank worksheets cannot satisfy this path.
- Supported-platform tests and release checks pass on the revision being released.
- The extracted skill creates, searches, updates and recovers a local SQLite archive without repository imports or network access. Revisions retain selected evidence and images without duplicating database files.
- Fresh role trials cover hiring, engineering, operations, growth, marketing and business development. Source selection, useful artifacts, vocabulary and emphasis follow the person's work; unavailable sources remain explicit gaps.
- Resume drafts use current context fingerprints and selected account references, preserve supplied reference preferences, and offer usable print and plain-text output. Structured validation is not semantic verification of resume claims.

- GitHub/social research discovers substantial work beyond the existing resume, inspects selected implementation and original threads, preserves authorship and prototype limits, and records inventory versus read coverage separately.

## Boundaries

Live connectors, continuous synchronization, hosted storage, automatic publication and an additional agent framework are not required for the core product. Add them only when a demonstrated user need outweighs their maintenance cost. Resume and interview outputs reuse the context; they do not silently replace it. When interview preparation is requested, the model gathers the already-authorized context, selects relevant evidence and drafts interviewer takeaways, core stories, an introduction with follow-up flags, question-to-story answers, story chapters and real timelines. These six principles organize the model's output. The person reviews the draft and answers genuine evidence gaps; they do not re-enter known facts or author the initial preparation. Preserve source references, shared credit, uncertainty and personal language in that projection. It does not change the source sheet's evidence or review state.

Use work documents only with an approved model and sources you are allowed to share.
