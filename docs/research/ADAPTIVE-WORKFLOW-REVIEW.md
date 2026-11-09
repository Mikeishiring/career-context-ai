# Adaptive workflow review

26 October 2026. Local validation using fictional inputs; no live personal accounts were collected or published.

The previous release preserved work accounts, but did not complete the requested journey. Its standalone skill had no local database or executable resume path. Role adaptation depended on the agent improvising, and visuals were hidden inside a text disclosure.

## Critique and repairs

| Finding | Repair | Evidence |
|---|---|---|
| No standalone database | SQLite stores selected accounts, sources, links, images, coverage and revisions; search and recovery work without the repository | Extracted-skill journeys in [adaptive tests](../../tests/test_adaptive_workflow.py) |
| Resume creation was only a promise | A reference-aware projection and renderer produce a populated private resume with source review, print/PDF and text export; stale context is rejected | Adaptive tests and [resume browser checks](../../tests/check_resume.cjs) |
| No explicit role adaptation | Discovery guidance covers hiring, engineering, operations, growth, marketing, BD and hybrid work; free-text profile and themes travel with the context | [Adaptation guide](../../skills/career-context-sheet/references/adaptation-and-discovery.md), six independent raw-note agent trials |
| Visuals were difficult to find or read | Relevant images appear with the account; an enlargement dialog supports small-screen inspection | [Sheet browser checks](../../tests/check_sheet.cjs), a fictional diagram with disclosed reconstruction |
| Image paths escaped the selected folder; embedded hashes were ignored | Relative contained paths, saved-checksum verification and aggregate output-size limits | Adversarial image tests and round-trip tests |
| Failed first database setup blocked recovery | Failed initialization closes and removes only its newly created incomplete database; a new build can retry | Injected schema-write failure regression |
| Mobile profile labels overflowed; print lost fictional labels | Wrapping and print-specific state labels | Independent 320px and print-media checks |
| Default file creation failed in the Windows sandbox | Atomic no-clobber rename on Windows; exclusive hard links on POSIX | Race-preservation tests; six successful default-save retries in the normal Windows sandbox |
| Single-account drafts repeated the introduction | Scope/role overview guidance keeps the narrative in the account | Independent revised six-role drafts |

The review was independent and read-only. Confirmed findings were reproduced and repaired. The raw-note trials were authored independently of the prewritten test packets; neither test type proves universal model quality.

## Checks

- `python -m unittest discover -s tests -q`: 135 passing toolkit tests.
- `python -m unittest discover -s ai-search-mvp/tests -q`: 87 passing research regressions.
- `python tools/check_mcp.py`: offline handshake and six-tool contract passed; no model or real source called.
- `python tools/check_multisource.py`: selected-window/follow-up strategy recovered all 13 in-scope fictional records, with no out-of-scope reads. One task remained blocked; retrieval is not semantic completeness.
- Six independent raw-note trials produced role-appropriate context, SQLite archives and resumes; search and byte-identical recovery passed. After the Windows repair, all six default saves worked without replacement flags.
- Independent trials passed 48 context/resume layout checks across 320, 375, 768 and 1440px. Separate browser checks covered a real embedded test image, enlargement, copy fallback, keyboard access, downloads, saved-file reopening, print, reduced motion and no-JavaScript reading. No external requests or browser errors were observed.

## Remaining limits

The host agent discovers and reads authorized connectors or selected files. The skill does not connect accounts, import every vendor's raw export, refresh automatically or guarantee “all context.” The collection map records actual scope and missing access. These trials used supplied fictional notes; live connector ingestion, original visual retrieval, large real career histories and cross-model equivalence remain untested.

Drafted resume sentences still need a semantic comparison with their sources. Reference checks establish structure and freshness, not factual truth. SQLite is unencrypted and retains old revisions; the HTML contains selected private evidence. See [privacy](../PRIVACY.md) and [archive retention](../../skills/career-context-sheet/references/local-archive.md).

## 27 October revision

The next critique found weak editorial selection, repetitive visible detail, unclear private exports and missing mobile navigation. The sheet now leads with concise connected accounts, keeps full fields in accessible disclosures, offers all-account or single-account text copying with source excerpts excluded by default, and retains a mobile index without JavaScript. Full HTML/JSON remain explicitly private. Optional sibling links connect separately delivered resumes and database files. Resume copy feedback appears beside its controls; chronology entries do not require invented bullets.

The workflow now begins with purpose and responsibilities before platform discovery, checks coverage across periods and less documented work, and records selection reasons. Its six discipline examples are explicitly non-exhaustive. A further cold synthetic hybrid trial began with raw theatre work, repair, booking, routine-check and rejected-proposal material plus another person's reference CV. It produced a broad archive and two differently targeted resumes from one unchanged evidence fingerprint. It retained contractor credit, a cancellation, sparse dates and unfinished work, and excluded the reference owner's qualifications. The review caught unnecessary metric disclaimers and a shortened phrase that lost the qualifier “some”; both were repaired.

Current checks: 136 toolkit tests and 87 research tests passed; MCP/multisource checks passed; public and private rendered checks covered 320, 375, 768 and 1440 pixels, copying, fallback, downloads, mobile navigation and no-script reading. The new cold trial added 12 layout checks and two visually reviewed one-page PDFs. These establish bounded behavior, not universal adaptation, exhaustive context collection or automatic factual validation. Every new person's synthesis still needs evidence review.


## Connected Work flow · 2026-11-02

The current flow was checked with four fictional raw accounts: a paper watering rota, a supervised chair repair, a display cancelled before construction, and unpaid background. No occupation, industry, target role, software tool or qualification was supplied. The notes are in `tests/fixtures/nontechnical-notes.md`; `tools/build_nontechnical_trial.py` authors the reproducible trial. This is a same-agent authored scenario and runtime test, not an independent fresh-model evaluation.

The browser checks covered year/period selection, related Work, visible-account copying, explicit all-account copying, search resetting copy scope, empty-result recovery, prepared Practice, unprepared-story handoff and return, background disclosure, 320px layout, full HTML download and reopening on a separate origin. Copying retained shared credit and unfinished outcomes without including other work or a global career narrative. Missing skills produced no empty Skills control. The saved file retained all records and restored its chosen year while resetting temporary Work filters.

The extracted standalone skill was also tested from a packet without journey or public-profile state. Guided rendering initialized the person's own-writing preference, kept Profile empty, preserved the supplied source boundary without fabricated monthly receipts, and survived SQLite archive recovery. The full Python suite passed 268 tests; 38 affected tests passed after final refinements. JavaScript scope, preparation, public-export and collection checks passed. These checks establish the tested behavior and evidence preservation, not universal research quality across people or models.


## Context-building flow — 2026-11-02

The main route is Build context → My context → Profile. Five activities collect, review, resolve consequential gaps, connect experiences and retain the person's voice. Practice is optional; existing preparation and notes survive. Private writing stays private when opening Profile. Profile selects its authored overview, examples and time periods; unselected components remain editable and recoverable.

A same-agent trial started from the existing fictional raw notes about a watering rota, supervised chair repair, cancelled display and unpaid contributions, with no target role, industry, software requirement or interview packet. Native browser checks followed year → filtered Work → review → the same Work selection, copied a context brief, kept a private writing draft, authored a separate profile and exported only a selected example. The actual public download omitted the withheld overview/year and private writing marker; the full private download retained them and all selection flags. Browser reload and archive round trips retained withheld drafts. Keyboard selection and 320/375/768/1440-width layouts were checked. No page-script errors were observed; browser-extension warnings were unrelated.

The Python suite ran 272 tests with one stale generated-example failure; after rebuilding that example, all 27 affected path, sharing and complete-document tests passed. Work scope, Profile projection, Timeline and coverage JavaScript checks passed. This is implementation and behavior verification, not an independent fresh-model research evaluation. The real personal file was checked structurally with unchanged evidence; its direct visual preview remained blocked.

## 2 November: responsibility check walkthroughs

Two fictional cases explore whether a title and working scope improve follow-up questions. Each is considered for a broad archive and a supplied interview target. These are same-author qualitative walkthroughs, not blind model trials or a measured improvement over the prior skill. No personal career records were used. The title expectations below are test assumptions, not claims about the labour market.

### Operations coordinator

Raw inputs:

- Self-report: “Operations coordinator, 2024–25. I followed up supplier orders and arranged venue bookings. Finance approved spending; I did not manage a budget or staff.”
- Handover note: “Two volunteers practised taking bookings with me in August. I still handled cancellations when the venue closed.”
- Draft: “Proposed a shared supplier tracker.” A later note says the manager chose to keep the existing process; there is no launch or time-saving record.

From the work alone: “What happened after the volunteers practised taking bookings?” The responsibility check suggests a more specific follow-up: “Which booking decisions, if any, could they make without you, and which still came back?” Neither version presumes a completed handoff. The second question is also available from the raw notes; the title supplies no new fact here.

The onboarding reflection is: “Your title was operations coordinator. The examples cover supplier follow-up, bookings and volunteer training, with spending approval elsewhere. What have I missed or misunderstood?”

For the broad archive, retain routine follow-up, training, cancellation handling and the unused proposal. For the supplied operations-manager interview target, use the training and exception-handling examples to explore coordination and judgment. The person's account explicitly excludes staff management and budget authority. An independent handoff and measured savings remain unestablished. The target does not change the recorded title.

### Staff software engineer

Raw inputs:

- Self-report: “Staff software engineer, 2025. I joined an established service team and implemented a retry component in an existing design. I rotated through on-call. I also helped at a community repair bench outside work.”
- Review note: “The maintainer selected the service architecture; the contributor supplied the component and tests.”
- Release note: “Merged behind a disabled flag. No rollout date recorded.”
- Paper repair log: “Helped diagnose a lamp fault with another volunteer.” No further result or exact date is recorded.

From the work alone: “Was the retry component subsequently enabled?” Adding the role context suggests a separate coverage question: “Do these examples cover the responsibilities you held under the staff title, or are other areas missing?” It does not assume architecture ownership, mentoring or cross-team leadership. The rollout question remains for authorized release records before asking the person.

The onboarding reflection is: “Your recorded title was staff software engineer. These examples show component implementation, tests and an on-call rotation. Do they cover the remit, or is something missing? There is also repair work outside the job.”

For the broad archive, retain both the software and repair accounts with their separate timing and attribution limits. For the supplied backend-engineer interview target, lead with the component's implementation and review; keep the disabled rollout beside the claim. The repair account may receive less emphasis in that preparation, but remains in the archive. Neither the title nor a merge establishes production impact or technical leadership.

### What this supports

The check supplies a reminder to examine ownership and coverage. In the coordinator case it asks how much responsibility transferred; in the engineer case it asks whether the examples cover the role. Neither question requires assuming duties from the title. Keep the check optional and revisable. These authored examples do not establish an advantage over careful evidence-only questioning or reliable improvement across users or models.

The guided **Your work** step stores this input in its existing private review notes. The host must reconcile it before updating accounts, the timeline or interview preparation. Browser and round-trip checks cover optional completion, retention, unchanged evidence and exclusion from public export; they cannot validate the meaning of a role interpretation.

Validation: 257 toolkit tests, 87 research regressions and 49 guided browser checks passed. Browser checks covered 320, 375, 768 and 1440px, save/reopen, optional completion and private-export boundaries, with no script errors or external requests. The standalone skill passed validation and built successfully. The sandboxed browser and full-suite attempts did not complete; these passing runs used the normal host environment.


## 9 November: integration with the current starter

The earlier responsibility note is now carried by the existing Build context starting note. Its role prompts are optional; saving a note does not approve evidence. The current navigation, per-account reviews, investigation memory and selected public exports remain in place. Contribution selection and evidence-first challenge guide the reading layer, with narrow updates restricted to affected accounts. The archive supplies material for reflection and preparation; it does not rate overall performance or infer other people’s views. Earlier validation counts above describe those historical versions, not this integration.
