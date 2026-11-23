"""Private output desk, projected from existing accounts and actual artifacts."""
from html import escape


def studio_overview(packet, work):
    accounts = packet['accounts']
    reviews = packet['journey'].get('reviews', {})
    pending = [a for a in accounts if not any(reviews.get(a['id'], {}).get(key)
               for key in ('importance', 'emphasis', 'interest'))]
    featured = (pending or accounts)[0]
    total = len(accounts)
    rated = total - len(pending)
    progress = f'{rated} of {total} {"story" if total == 1 else "stories"} rated'
    library = [('work', 'Work accounts', total), ('sources', 'Saved sources', len(packet['sources']))]
    if packet.get('timeline'):
        library.append(('timeline', 'Timeline periods', len(packet['timeline'])))
    resources = ''.join(
        f'<a href="#{key}"><span class="library-icon icon-{key}" aria-hidden="true"></span>'
        f'<span>{label}</span><strong>{count}</strong><span aria-hidden="true">›</span></a>'
        for key, label, count in library)
    return f'''<div class="studio-desk"><a class="review-launch" href="#story-review" data-featured="{escape(featured["id"])}">
<div class="launch-copy"><h2>Review your stories</h2><p id="studio-rating-count">{progress}</p>
<progress id="studio-rating-progress" aria-labelledby="studio-rating-count" value="{rated}" max="{total}"></progress>
<span class="launch-action">Open review <span aria-hidden="true">→</span></span></div>
<div class="story-folder" data-sheets="{min(total,3)}"><div class="folder-sheet">
<span class="folder-period">{escape(featured['period'])}</span><strong class="folder-title">{escape(featured['title'])}</strong></div>
<div class="folder-pocket" aria-hidden="true"></div></div></a>
<div class="studio-work">{work}</div>
<section class="studio-library" aria-labelledby="library-title"><h2 id="library-title">Context library</h2>{resources}</section></div>'''


def story_review(packet):
    journey = packet.get('journey')
    if not journey or not packet['accounts']:
        return ''
    rows, options, fallback = [], [], []
    for account in packet['accounts']:
        key = escape(account['id'])
        title = escape(account['title'])
        rows.append(f'<li><button type="button" data-review-story="{key}" aria-controls="review-sheet">'
                    f'<span>{title}</span><small data-story-verdict="{key}"></small></button></li>')
        options.append(f'<option value="{key}">{title}</option>')
        gap = next((q for q in account['questions'] if q.strip()), '')
        fallback.append(f'<li><a href="#account-{key}">{title}</a>'
                        + (f'<p>{escape(gap)}</p>' if gap else '') + '</li>')
    missing = escape(journey['notes'].get('missingWork', ''))
    count = len(rows)
    return f'''<section class="document-view studio-review" id="story-review" aria-labelledby="review-title">
<header class="review-heading"><h1 id="review-title">Review your stories</h1><button type="button" class="review-save js-only" id="save-story-review">Save private file <span aria-hidden="true">↓</span></button>
<p id="story-review-status" role="status"></p></header>
<div class="review-workbench js-only"><aside class="review-index">
<h2 id="review-index-title">Your stories <span>{count}</span></h2>
<p>Stories are often easier to tell when you’re excited about the work, proud of it, or were deeply involved.</p>
<ul>{"".join(rows)}</ul>
<select class="review-picker" id="review-picker" aria-labelledby="review-index-title">{"".join(options)}</select>
</aside><article id="review-sheet" aria-labelledby="review-story-title"></article></div>
<details class="review-omission js-only"><summary>What work is missing from this list?</summary>
<label for="missing-work">Work to add</label><textarea id="missing-work" rows="2" maxlength="10000">{missing}</textarea></details>
<div class="no-script"><ul>{"".join(fallback)}</ul></div></section>'''


def render(packet):
    esc = lambda value: escape(str(value), quote=True)
    accounts = {a['id']: a for a in packet['accounts']}
    examples = []
    # A working original is the most useful entry into an example.
    ordered = sorted(accounts.values(), key=lambda account: not any(
        artifact.get('link') for artifact in account.get('artifacts', [])[:1]))
    for account in ordered:
        for artifact in account.get('artifacts', [])[:1]:
            link = artifact.get('link')
            destination = (f'<a href="{esc(link["url"])}" target="_blank" rel="noopener noreferrer">{esc(link["label"])} ↗</a>') if link else ''
            examples.append(
                f'<article class="studio-example"><a href="#account-{esc(account["id"])}" class="studio-preview"'
                f' aria-label="Read {esc(account["title"])}"><img data-studio-image="{esc(artifact["embeddedId"])}"'
                f' alt="{esc(artifact["title"])}" loading="lazy"></a><div class="studio-example-text">'
                f'<h3><a href="#account-{esc(account["id"])}">{esc(account["title"])}</a></h3>'
                f'<p>{esc(artifact["caption"])}</p><div class="studio-example-links">{destination}<a href="#account-{esc(account["id"])}">Read work example →</a></div>'
                f'</div></article>')
    examples_html = ('<section class="studio-examples" aria-labelledby="studio-examples-title">'
                     '<div class="studio-section-heading"><h2 id="studio-examples-title">Work examples</h2>'
                     '<a href="#work">All work →</a></div><div class="studio-example-grid">'
                     + ''.join(examples) + '</div></section>') if examples else ''
    stories = {s['id']: s for s in packet.get('interview', {}).get('stories', [])}
    reviews = packet.get('journey', {}).get('reviews', {})
    interest = lambda key: reviews.get(key, {}).get('interest')
    leads = [key for key in accounts if interest(key) == 'lead']
    shortlist = (leads + [key for key in stories if key not in leads and interest(key) != 'reserve'])[:3]
    story_rows = ''.join(
        f'<li><small>{esc(accounts[key]["period"])}</small><a data-rehearse="{esc(key)}" href="#prep-story-{esc(key)}"><span>{esc(accounts[key]["title"])}</span>'
        '<span aria-hidden="true">↗</span></a>'
        f'<p>{esc(stories[key]["takeaway"] if key in stories else accounts[key]["contribution"])}</p></li>' for key in shortlist)
    stories_html = ('<section class="studio-stories" id="studio-stories" aria-labelledby="studio-stories-title"'
                    + ('' if shortlist else ' hidden') + '>'
                    '<div class="studio-section-heading"><h2 id="studio-stories-title">Stories to use</h2>'
                    '<a href="#interview">Interview prep →</a></div><ul>' + story_rows + '</ul></section>') if accounts else ''
    files = ''.join(f'<a href="{esc(f["path"])}">{esc(f["label"])} <span aria-hidden="true">↗</span></a>'
                    for f in packet.get('presentation', {}).get('files', [])
                    if f['path'].lower().endswith('.html'))
    downloads = ''.join(f'<a href="{esc(f["path"])}">{esc(f["label"])}</a>'
                        for f in packet.get('presentation', {}).get('files', [])
                        if f['path'].lower().endswith(('.pdf', '.txt')))
    if downloads:
        files += '<details class="studio-downloads"><summary>Downloads</summary><div>' + downloads + '</div></details>'
    files_html = f'<nav class="studio-files" aria-label="Prepared drafts">{files}</nav>' if files else ''
    actions = ('<div class="studio-actions js-only" aria-label="Prepare an output">'
               '<button type="button" data-studio-kind="resume">Create draft <span aria-hidden="true">↗</span></button></div>') if packet.get('journey') and accounts else ''
    empty = ('<div class="studio-empty"><p>No work saved yet.</p><a class="context-add" href="#path-gather">'
             'Add your first piece of work <span aria-hidden="true">+</span></a></div>') if not accounts else ''
    if accounts and not examples and not stories and not shortlist and not packet.get('journey'):
        empty = '<div class="studio-empty"><p>No examples or stories prepared yet.</p><a href="#work">Read your saved work →</a></div>'
    options = ''.join(f'<option value="{esc(a["id"])}">{esc(a["title"])}</option>' for a in accounts.values())
    add_context = '<a href="#path-gather" class="text-button">Add context +</a>' if packet.get('journey') else '<a href="#work">Read work</a>'
    if not packet.get('journey') and not accounts:
        empty = '<p class="studio-empty">No work saved yet. Give this file to your assistant to begin.</p>'
    review = story_review(packet)
    work = examples_html + stories_html
    desk = studio_overview(packet, work) if review else work
    return f'''<section id="studio" class="document-view studio" aria-labelledby="studio-title">
<div class="context-heading"><h1 id="studio-title">Career studio</h1><div class="studio-header-actions">{add_context}{actions}</div></div>
{files_html}{empty}{desk}
<dialog id="studio-request" aria-labelledby="studio-request-title"><form id="studio-request-form">
<div class="studio-dialog-heading"><h2 id="studio-request-title">Prepare an output</h2><button type="button" id="studio-close" aria-label="Close output request">×</button></div>
<label>Output<select id="studio-kind"><option value="resume">Resume</option><option value="example">Visual work example</option><option value="story">Career story</option><option value="custom">Something else</option></select></label>
<label>Use<select id="studio-account"><option value="">All saved work</option>{options}</select></label>
<label><span id="studio-direction-label">Audience or role</span> <span class="studio-optional" id="studio-optional">(optional)</span><textarea id="studio-direction" rows="2" maxlength="2000"></textarea></label>
<button type="submit" class="primary">Save for assistant <span aria-hidden="true">↓</span></button>
<p class="studio-handoff-note">Attach the saved private file to your assistant. It includes your request and evidence.</p>
<p id="studio-status" role="status"></p></form></dialog></section>{review}'''
