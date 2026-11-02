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

[Download the project](https://github.com/Mikeishiring/career-context-ai/archive/refs/heads/main.zip), extract it and open **[CAREER-CONTEXT.html](CAREER-CONTEXT.html)** to try the fictional example offline. GitHub shows HTML as source; open the downloaded file in a browser.

To build your own archive, give an agent the complete [career-context-sheet folder](skills/career-context-sheet/) and ask:

> Help me build a local archive of my work. Reuse the context I've already supplied, collect from sources I authorize, and keep evidence separate from interpretation. Preserve shared credit, uncertainty and my wording. Save a searchable database and one HTML file. We'll adapt it to a particular purpose when I need it.

The local tools need Python 3.11+ and no additional packages. Start with the material you have; the skill does not connect accounts by itself. [Setup and first archive](docs/GETTING-STARTED.md).

## Use it elsewhere

The archive is the reusable part. Resumes, profiles and interview preparation are selected views of it. A coach or job-search service can use a reviewed selection without needing your whole database.

Export a reviewed selection for another agent or tool. The optional local MCP connection exposes only that snapshot, with no archive writes or automatic uploads. [Selected context and local MCP](skills/career-context-sheet/references/selected-context.md).

**Build context** guides collection and review. **My context** connects Timeline to Work; Practice is optional. **Profile** controls which overview, progression periods, examples and visual evidence enter a selected public download. Full HTML and JSON remain private working files.

The experiments test parts of the research process on fictional cases. They do not establish complete career coverage or better results than other tools.

[Guides](docs/README.md) · [Contributing](CONTRIBUTING.md) · [Research experiments](ai-search-mvp/README.md) · [MIT license](LICENSE)
