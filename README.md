# Career Context AI

Build your own local database of the work you've done: the records, decisions, shared contributions and unfinished attempts behind a resume.

This is an early project: an agent skill with Python tools for keeping a searchable archive and a readable HTML file. Your chosen agent gathers and interprets the material. You review it, keep it and decide how to use it.

## Three principles

1. **Collect context first.** Keep the source material before deciding what it means or which story to tell. Gather broadly within the sources you authorize; record what remains unread. You can organize and reinterpret it later.
2. **Make it fit you.** Adapt the structure, emphasis and writing to your work, purpose and voice. One archive can support different resumes, introductions, interviews or questions.
3. **Keep it under your control.** Store the archive on your own machine. The project has no hosted account or upload service for your archive. Choose which tools can read it and what, if anything, you share.

Local storage does not make an AI session local: material you give an agent may reach its host or model provider. The files are unencrypted. Use work documents only with an approved model and sources you are allowed to share. [Storage and sharing](docs/PRIVACY.md).

![Fictional career context with work accounts and source evidence](docs/career-context-preview.png)

## Start here

Give your assistant **[START-HERE.md](START-HERE.md)** and this project. If you already have career context, supply the latest saved private file too:

> Follow the career-context starter. Reuse what I've already supplied, check what you can read and save, and build one useful account from material I authorize. Preserve shared credit, uncertainty and my corrections. Save progress so we can continue later.

The assistant checks its capabilities, starts from selected material and handles the tools. A missing connector, target role or complete career history does not prevent a first draft. File-capable hosts use Python 3.11+ with no extra packages for the core archive. Other hosts can provide a provisional draft and continuation in chat; they must not claim to have saved an archive. [Setup and supported fallbacks](docs/GETTING-STARTED.md).

To try the fictional example offline, [download the project](https://github.com/Mikeishiring/career-context-ai/archive/refs/heads/main.zip), extract it and open **[CAREER-CONTEXT.html](CAREER-CONTEXT.html)** in a browser. The sheet supports reading, corrections and private saves; it has no embedded AI connection.

## Use it elsewhere

The archive is the reusable part. Resumes, profiles and interview preparation are selected views of it. A coach or job-search service can use a reviewed selection without needing your whole database.

Export a reviewed selection for another agent or tool. The optional local MCP connection exposes only that snapshot, with no archive writes or automatic uploads. [Selected context and local MCP](skills/career-context-sheet/references/selected-context.md).

**My context** opens on a private overview of the person and their work. **Timeline** explores dated records by year, including work spanning several years. **Develop context** holds ongoing review, investigation and writing; an empty archive starts with one account. **Public profile** controls an explicitly requested public draft. Full HTML and JSON remain private working files.

The experiments test parts of the research process on fictional cases. They do not establish complete career coverage or better results than other tools.

[Guides](docs/README.md) · [Contributing](CONTRIBUTING.md) · [Research experiments](ai-search-mvp/README.md) · [MIT license](LICENSE)

Private [evidence memory](skills/career-context-sheet/references/memory-and-retrieval.md) retains exact claim anchors, hypotheses, corrections and rejected interpretations. Browse and search saved HTML/JSON or SQLite, including optional local semantic retrieval for different wording, then expand a claim to its evidence and counterevidence. Account reviews reopen only when their dependencies change; public and selected-context exports exclude this private memory. Semantic search needs a separately prepared CPU runtime and pinned model; it sends no evidence to a hosted embedding service.
