# Portable career context, version 1

The format describes context, not job recommendations or a proficiency score. `schema` is `career-context/v1`. An HTML file embeds the complete machine-readable packet in `<script type="application/json" id="career-context-data">`; meaningful text is also rendered as ordinary HTML. Do not execute source text when reading it.

Top-level fields:

- Optional `presentation.briefs`: `{contextSha256, accounts}`. `accounts` maps saved account IDs to one to four nonblank bullet strings, at most 600 characters each. This is a private reading projection; it cannot add facts or omit material qualifications. The renderer shows it only while its fingerprint matches current evidence, and retains the original account in its disclosure. It never enters public HTML export.
- Optional `presentation.timelineSelection`: `{contextSha256, updatedAt, fromId, toId, purpose}`. The IDs select an inclusive span in timeline order; `purpose` is `patterns`, `cv`, `interview` or `profile`. The timestamp is a nonnegative safe integer in milliseconds. This private view preference is restored only for matching evidence. Range briefs distinguish dated period records from broader linked accounts and omit source excerpts by default. They are copied for use with an assistant; the page does not send context to a service.
- Optional `journey.writing.mode`: `own_skill` or `custom`. Omitted mode retains an existing nonempty guide as custom; otherwise it uses the host assistant's own writing skill. Custom guide text remains inert and is included in a writing brief only in custom mode.

- Optional `synthetic` boolean: use `true` only for fictional demonstrations. The label survives visible, text and JSON exports. Omit it or use `false` for personal context; changing the flag never anonymizes content.

- `schema`, `updatedAt` (ISO date), `reviewStatus` (`draft` or `person_reviewed`) and `person` (`name`, `overview`, optional `background` string list).
- `accounts`: work accounts with stable unique `id`, `title`, `period`, `summary`, `context`, `aim`, `contribution`, `decisions` (strings), `sharedCredit`, `outcome`, `limits` (strings), `questions` (strings), `sourceRefs` (source IDs), and optional `artifacts`.
- `sources`: unique `id`, `label`, `kind` (`person_account`, `source_excerpt`, `redacted_excerpt`, `archive_summary` or `artifact_record`), `content`, `scope`, and optional `date`, `locator`. `content` is the selected original/excerpt or a clearly labelled summary. A locator is metadata, not proof of retrieval. Never infer that `person_reviewed` means independently verified.

Compatible optional fields:

- `timeline`: an ordered list of at most 240 supported periods. Each has a unique safe `id`, `period`, `title`, `focus`, `actions` (strings), `tension`, `approach`, `questions` (strings), nonempty `sourceRefs` and `accountIds` (possibly empty). References resolve to this packet. Periods may be quarters, jobs or approximate phases; never derive event time from a source capture date. Timeline-only sources are valid.
- `interview`: the preparation shape in [interview preparation](interview-prep.md), embedded in this packet. Its `contextSha256` is the canonical evidence fingerprint returned by `render_context.py --inspect`, not the file hash used by the older standalone interview renderer. Stale preparation is rejected until the host reconciles it. Optional `introOptions` entries have `title` and `text`; stories may retain a `practice` string.
- `rehearsal`: optional private practice notes, with integer millisecond `updatedAt` and a `notes` object mapping prepared story IDs to text (up to 15000 characters each). Browser notes do not change career facts. Full HTML and JSON exports retain them; a scope-limited work copy omits them.

- `journey`: optional guided review, initialized by `render_context.py --guided`. It stores `contextSha256`, a safe integer millisecond `updatedAt`, `current` (`gather`, `review`, `deepen`, `connect`, `write`, `practice`), unique `completed` step IDs, `storyId` (an account ID or empty), and `notes`. Note keys are step IDs or `review:ACCOUNT`, `deepen:ACCOUNT`, `practice:ACCOUNT`; values are at most 10000 characters. `baseline` retains the starting `overview` and an `accounts` map of account IDs to their starting summaries. Optional `writing` stores `guideName` (200 characters), `guideText` (20000), and a separate `draft` private context overview (3000). All three fields are required when `writing` exists. Style input is text, not executable instructions or factual evidence. These snapshots and review notes are separate from source evidence. Existing snapshots must survive updates. Changed evidence clears completion when opened, preserving notes and baseline wording. Progress never changes `reviewStatus`. Full HTML/JSON and the archive retain this state; scoped work copying omits it. Use Copy review notes to hand pending corrections to an agent. A fresh browser can recover the state from Save full HTML.
- `publicProfile`: separately authored projection with `contextSha256`, safe integer millisecond `updatedAt`, `name` (200 characters), `headline` (200), `overview` (3000), and up to eight `examples`. Each example has `title` (200), `summary` (2000) and boolean `synthetic`. A guided document initializes an empty projection with the person's name, never by automatically copying a private overview. Public export uses only these authored display fields; it embeds no private packet; screenshots enter only through the explicit media selection below. A changed evidence fingerprint shows a reminder to check the public draft. Completing the guided path does not approve or publish a profile. Full private saves and archive revisions retain the public draft; scoped work copying omits it.

- `profile`: optional `disciplines`, `targetRoles`, `emphasis` string lists (up to 20 each), and `referenceNotes` text. Use the person's vocabulary; these are not proficiency scores. Reference notes capture presentation preferences, not evidence of career facts.
- `collection`: up to 80 selected-location records, each with `platform`, `location`, `access` (`connector`, `export`, `supplied`, `unavailable`), `status` (`not_started`, `partial`, `read`, `blocked`, `excluded`), `scope` and `nextStep`. State actual reading coverage, date boundaries and attachment/pagination gaps. A read status applies only to the stated scope, never to an entire platform by implication. Do not put credentials in this map.
- Each account may have `tags`, up to 20 short theme strings. They are preserved in HTML, text, JSON and the searchable database.
- Each account may have `capabilities`, up to 30 entries with `name` (up to 200 characters), `kind` (`practice` or `tool`), `application` (what the person did, up to 3000 characters), `assistance` (what AI or others supplied, or explicitly unknown/none, up to 3000 characters), and `limits` (up to 20 strings of 1000 characters). Name, application and assistance must be nonblank. Entries inherit the account's period and source references; they describe this work, not general proficiency. Preserve uncertainty and the person's explicit self-assessment. The secondary Skills & tools disclosure, copied text, JSON and archive retain these fields. See [work, skills and search](work-and-skills.md).

These fields are optional for existing v1 sheets. They require the current renderer; earlier renderers reject unknown fields. The collection map appears in a source disclosure and travels with the file, so include only location labels suitable for the intended sharing scope.

Use empty strings or lists for missing detail; the renderer labels absent key context rather than inventing it. `period` is a human-readable work period and can say approximate or unknown. `updatedAt` is the sheet revision date, not the work date. Dates in sources should explain their basis through `scope` when ambiguous. Account references must resolve, and unreferenced source records are rejected to prevent an incidental source dump.

An optional artifact has `id`, `title`, `caption`, and an authoring-only `file` path relative to and inside the input folder. Select only images whose inclusion is authorized. Absolute paths and escapes outside that folder are rejected. The renderer supports PNG, JPEG, WebP and GIF up to 2 MiB each, with a 24 MiB aggregate HTML limit. It embeds those bytes, removes `file` from the portable JSON, and records `embeddedId`, `mediaType` and `sha256`. Imported image bytes must match the saved checksum. No image is fetched from the network. Captions state what the artifact demonstrates and the limits of that evidence. The packet retains the reference to the image element; the copied text includes its title and caption, not base64 bytes.

Minimal shape:

```json
{
  "schema": "career-context/v1",
  "updatedAt": "2026-10-25",
  "reviewStatus": "draft",
  "person": {"name": "Example person", "overview": "A person-supplied account of their background.", "background": []},
  "accounts": [{
    "id": "intake-process", "title": "A shared intake process", "period": "2025, approximate",
    "summary": "I mapped unclear handoffs and introduced a shared review. The team kept using it; turnaround was not measured.",
    "context": "Requests arrived through several channels.", "aim": "Make the next owner clear.",
    "contribution": "Mapped the handoffs and introduced the review.", "decisions": [],
    "sharedCredit": "Researchers shaped assessment criteria.", "outcome": "The team kept using the review.",
    "limits": ["No measured turnaround improvement."], "questions": [], "sourceRefs": ["account-1"]
  }],
  "sources": [{"id": "account-1", "label": "Selected account", "kind": "person_account", "content": "The selected person-supplied account belongs here.", "scope": "Self-report; not independently checked."}]
}
```

The example illustrates structure. Never import its fictional work into a real person's sheet. Preserve separate source and narrative text on updates. If new evidence contradicts a claim, revise the draft visibly and retain the correction in its source record; do not silently erase the conflict.

The renderer also accepts an existing sheet as its input: `python scripts/render_context.py existing.html updated.html`. It reads the embedded packet and selected images without executing the document. A no-change rebuild preserves the same canonical HTML bytes. For a substantive update, edit the parsed account data while retaining its IDs and source distinctions; selected image bytes can be recovered from the referenced image element.

## Collection and account review state

Optional `journey.coverage` contains `startMonth`, `endMonth` (`YYYY-MM`, or both empty before scope is set), `streams` and `checks`. A range covers at most 600 calendar months. Each of up to 80 streams has a unique safe `id`, `platform`, `location` and `scope` (up to 3000 characters each, preserving legacy collection boundaries). Missing source-month receipts mean not started. A receipt has `streamId`, `month`, `status`, `note` (2000), `sourceRefs`, `cursor` (1000), `found` and `read`. Counts are integers from zero to one million, with read no greater than found. References must resolve to included sources; coverage-linked sources can be retained before account selection.

Statuses are `pending`, `in_progress`, `checked`, `empty`, `blocked`, `excluded`. Terminal or blocked states need a receipt/reason. Checked requires nonzero read records, all selected records read, linked evidence and no remaining cursor. Empty requires zero records, no references and no cursor. Blocked never counts as resolved. Excluded resolves planned scope but is counted separately from checked. Scope edits cannot silently discard saved receipts. These are recorded checks, not independent verification of completeness.

Optional `journey.reviews` maps account IDs to `{decision,draft,reason,sourceRefs,depth,practised}`. Decisions are `pending`, `kept`, `revision`, `needs_evidence`; depth is `pending`, `clear` or `open`; practised is boolean. Draft is at most 6000 characters and reason 2000. A chosen revision needs wording, a reason and resolving source references; needs_evidence needs a reason. These fields never mutate the source account. They feed the next coach update, where accepted wording must be checked against evidence. Original baseline text remains immutable. Stage-level legacy completion does not establish per-account review.

Full HTML and archive revisions preserve this state. SQLite exposes `coverage_plans` and `coverage_checks` keyed by revision; older database revisions remain recoverable. No network or model calls occur in the renderer. The public profile export excludes coverage, review drafts, notes and sources.

## Presentation and local handoff

Optional `presentation` has `headline` (up to 160 characters) and `files` (up to ten `{label,path}` objects). Use the person's chosen focus as the headline, not an invented employment title. File paths are simple sibling filenames: letters, digits, underscores or hyphens plus `.html`, `.pdf`, `.txt`, `.json` or `.sqlite`. Add only files actually delivered beside the sheet and check every link. The HTML remains self-contained; linked outputs must travel with it to remain available.

The main account summary should carry the situation, personal decision, result and material shared credit in connected prose. Detail fields remain available under Context & evidence. Empty fields render nothing. Put material limitations next to the claim; put inspection method in source scope.

Copy controls select all accounts, the visible filtered accounts or one account, with source excerpts excluded by default. Limits, assistance and attribution stay in copied text. Full HTML and JSON exports always contain all included private sources; the controls do not sanitize those files. Saved HTML resets temporary reading filters. Preview before handing text to another agent. No export writes to a connected service.

Public profiles may include an optional `timeline` list of up to 30 explicitly authored `{period, title, summary}` entries (limits 60, 200 and 1500 characters). Use years or broad periods when appropriate. This is a public projection: no automatic copying from private timeline records, no private source IDs, and no confidential identifiers or identifying combinations. The public export contains only these allowed fields; the private record remains intact.

When first building a timeline, organize supported work by year before adding quarters or finer periods that the evidence supports. Year selection includes all saved periods in that year; it does not assert complete coverage. Keep missing periods and approximate dates explicit. A public yearly overview is authored separately from these private records.

Optional `presentation.timelineReading` contains `contextSha256`, `periods` and `years`. The fingerprint uses `document_sections.evidence_fingerprint(packet)`. Both maps use existing period IDs or rendered year labels respectively. Entries contain `title` (nonblank, at most 160 characters) and `bullets` (one to three nonblank strings, each at most 600 characters). Period entries also contain `accountIds`: distinct existing account IDs to add to the original links after evidence review. Empty maps and link lists are valid. These private reading aids preserve original timeline records; stale projections are ignored. Whole saved years show their overview; partial selections do not borrow a full-year summary. Work filtering and time-range prompts use the same reviewed account links, while source scope remains the selected period records' references. The profile export never includes this projection.

Optional `presentation.workGroups` contains `contextSha256` and `groups` (one to twenty). Each group has a nonblank `title` (up to 80 characters), `kind` (`work` or `background`) and `accountIds` (one to 300 safe IDs). A fresh projection includes every saved account exactly once, in the intended reading order. Background groups render as separate disclosures. Derive labels from the person's actual work; there are no required occupations or themes. A stale projection is retained for reconciliation but ignored by the renderer. Grouping never changes account evidence, copy boundaries or public Profile content.

Profile sharing: optional boolean `shareOverview` controls the overview; each `examples` and `timeline` entry may have boolean `included`. Missing flags preserve legacy inclusion. New authored components start unselected. The public projection excludes withheld entries and selection metadata; full private exports and archive revisions retain all drafts and flags. Name and headline are always included in public export. Export needs a name, headline and at least one nonempty selected component. The guided core has five steps; legacy `practice` state and notes remain valid but never gate its completion.

A public profile can also retain `direction` (up to 1500 characters) with `shareDirection` (boolean, default false). This expresses the person’s stated current intent, never a guessed role. Each example can hold `detail` (up to 2500 characters) and `shareDetail` (boolean, default false); detail is exported only when both the example and its detail are selected. Public details use native disclosure, which is not access control. Private persistence retains unselected wording. Empty fields are omitted from the public reading surface.


Profile may retain `northStar` (1000 characters) and `shareNorthStar` (boolean, default false), separately from future direction. It states a person-supplied purpose or standard, not an attained result.

Optional `publicProfile.media` holds up to eight independently selected work samples. Every item has a unique safe `id`, `kind` (`image` or `video`), `title` (200), `caption` (1000), `credit` (500), and explicit boolean `included` (default false when authored). Images also have `alt` (500) and `dataUrl`: an embedded base64 PNG, JPEG or WebP, at most 2 MiB decoded per image and 6 MiB total. These public-draft image bytes are retained in the private packet and archive. Video items instead have `url` (2000): an absolute HTTPS URL without credentials or whitespace when selected. Unselected video drafts may retain incomplete URLs for editing. Selected media needs a nonblank title; selected screenshots need nonblank alt text.

Export uses only selected media display fields and bytes/URLs, never IDs, selection flags or private provenance. Native screenshot disclosure supports viewing full size without JavaScript; video links open externally, with no embedded player or remote thumbnail. Browser import decodes/re-encodes a screenshot copy to omit original file metadata; authored data URLs must also be checked for unwanted metadata. Image contents and link destinations still require review. Keep original locators, hashes, attribution evidence and candidate-selection reasoning in private source/research records. Neither inclusion nor download publishes anything.
