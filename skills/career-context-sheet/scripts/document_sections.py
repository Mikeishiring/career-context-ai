"""Timeline and interview views for the single portable career document."""
import copy
import hashlib
import html
import json
import re


def evidence_fingerprint(packet):
    """Ignore presentation, image transport and rehearsal edits, not evidence."""
    evidence = {k: copy.deepcopy(packet[k]) for k in
                ('person', 'profile', 'accounts', 'sources', 'timeline') if k in packet}
    for account in evidence['accounts']:
        account.pop('artifacts', None)
    if 'memory' in packet:
        evidence['memory'] = copy.deepcopy(packet['memory'])
        for claim in evidence['memory']['claims']:
            claim.pop('aliases', None)  # Retrieval vocabulary does not alter a claim.
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':')).encode()).hexdigest()


def validate_timeline(packet, check_text, keys):
    timeline = packet.get('timeline', [])
    if not isinstance(timeline, list) or len(timeline) > 240:
        raise ValueError('Timeline must contain at most 240 periods')
    source_ids = {s['id'] for s in packet['sources']}
    account_ids = {a['id'] for a in packet['accounts']}
    ids, used = set(), set()
    for period in timeline:
        keys(period, ['id', 'period', 'title', 'focus', 'actions', 'tension',
                      'approach', 'questions', 'sourceRefs', 'accountIds'], 'Timeline period')
        key = period.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', key) or key in ids:
            raise ValueError('Timeline periods need unique safe IDs')
        ids.add(key)
        for field in ['period', 'title', 'focus', 'tension', 'approach']:
            check_text(period.get(field), 'Timeline ' + field, 15000)
        for field in ['period', 'title']:
            if not period[field].strip(): raise ValueError('Timeline ' + field + ' must not be blank')
        for field in ['actions', 'questions', 'sourceRefs', 'accountIds']:
            if not isinstance(period.get(field), list) or len(period[field]) > 300:
                raise ValueError('Timeline ' + field + ' must be a bounded list')
            for value in period[field]: check_text(value, 'Timeline ' + field, 15000)
        for field, allowed in [('sourceRefs', source_ids), ('accountIds', account_ids)]:
            if len(set(period[field])) != len(period[field]) or set(period[field]) - allowed:
                raise ValueError('Timeline ' + field + ' must resolve without duplicates')
        if not period['sourceRefs']: raise ValueError('Every timeline period needs source references')
        used.update(period['sourceRefs'])
    return used


def validate_rehearsal(packet, check_text, keys):
    rehearsal = packet.get('rehearsal')
    if rehearsal is None: return
    keys(rehearsal, ['updatedAt', 'notes'], 'Rehearsal')
    if not isinstance(rehearsal.get('updatedAt'), int) or isinstance(rehearsal['updatedAt'], bool) or rehearsal['updatedAt'] < 0:
        raise ValueError('Rehearsal needs a nonnegative update time')
    ids = {s['id'] for s in packet.get('interview', {}).get('stories', [])}
    notes = rehearsal.get('notes')
    if not isinstance(notes, dict) or set(notes) - ids:
        raise ValueError('Rehearsal notes must reference prepared stories')
    for note in notes.values(): check_text(note, 'Rehearsal note', 15000)


def esc(value):
    return html.escape(str(value), quote=True)


def paragraphs(value):
    return ''.join('<p>' + esc(p) + '</p>' for p in value.split('\n\n') if p.strip())


def bullets(values):
    return '<ul>' + ''.join('<li>' + esc(v) + '</li>' for v in values) + '</ul>' if values else ''


def references(packet, ids):
    names = {s['id']: s['label'] for s in packet['sources']}
    return '<div class="section-references">' + ''.join(
        f'<a href="#source-{esc(key)}">{esc(names[key])}</a>' for key in ids) + '</div>'


def period_year(period):
    match = re.search(r'\b(?:19|20)\d{2}\b', period['period'])
    return match.group() if match else 'Other periods'


def period_years(period):
    """Expand only an explicitly written year range, never missing chronology."""
    months = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    span = re.search(r'\b((?:19|20)\d{2})(?:[-/]\d{2}(?:[-/]\d{2})?)?\s*(?:[–—-]|\bto\b)\s*'
                     r'(?:\d{1,2}\s+)?(?:' + months + r'\.?\s+)?(?:\d{1,2},?\s+)?((?:19|20)\d{2})\b', period['period'], re.I)
    if span and int(span[1]) <= int(span[2]):
        return [str(year) for year in range(int(span[1]), int(span[2]) + 1)]
    return [period_year(period)]


def context_overview(packet):
    """A private reading of saved context, with links back to the full accounts."""
    accounts = packet['accounts']
    rows = ''.join(
        f'<li><span class="context-period">{esc(a["period"]) or "Date not recorded"}</span>'
        f'<div><a href="#account-{esc(a["id"])}">{esc(a["title"])}</a>'
        f'{paragraphs(a["summary"])}</div><span class="context-row-arrow" aria-hidden="true">↗</span></li>'
        for a in accounts[:6])
    more = f'<a href="#work">All {len(accounts)} accounts →</a>' if len(accounts) > 6 else ''
    register = (f'<section class="context-register"><div class="context-section-heading"><h2>Work &amp; experience</h2>'
                f'<a href="#timeline">Explore timeline →</a></div><ol>{rows}</ol>{more}</section>') if accounts else ''
    questions = [(a, q) for a in accounts for q in a['questions']][:3]
    gaps = ''.join(f'<li>{esc(q)}<a href="#account-{esc(a["id"])}">{esc(a["title"])}</a></li>' for a, q in questions)
    gaps = f'<section class="context-questions"><h2>Still to understand</h2><ul>{gaps}</ul></section>' if gaps else ''
    return register + gaps


def timeline_reading(packet):
    reading = packet.get('presentation', {}).get('timelineReading', {})
    return reading if reading.get('contextSha256') == evidence_fingerprint(packet) else {}


def work_groups(packet):
    projection = packet.get('presentation', {}).get('workGroups', {})
    return projection.get('groups', []) if projection.get('contextSha256') == evidence_fingerprint(packet) else []


def validate_work_groups(packet, check_text, keys):
    projection = packet.get('presentation', {}).get('workGroups')
    if projection is None: return
    keys(projection, ['contextSha256', 'groups'], 'Work groups')
    if not isinstance(projection.get('contextSha256'), str) or not re.fullmatch('[a-f0-9]{64}', projection['contextSha256']):
        raise ValueError('Work groups need an evidence fingerprint')
    groups = projection.get('groups')
    if not isinstance(groups, list) or not 1 <= len(groups) <= 20:
        raise ValueError('Work groups need one to twenty groups')
    seen = set()
    for group in groups:
        keys(group, ['title', 'kind', 'accountIds'], 'Work group')
        check_text(group.get('title'), 'Work group title', 80)
        if not group['title'].strip() or group.get('kind') not in ['work', 'background']:
            raise ValueError('Work groups need a title and work or background kind')
        ids = group.get('accountIds')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 300 or any(not isinstance(i, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', i) for i in ids):
            raise ValueError('Work groups need bounded account IDs')
        if len(set(ids)) != len(ids) or set(ids) & seen:
            raise ValueError('Each account belongs to one work group')
        seen.update(ids)
    if projection['contextSha256'] == evidence_fingerprint(packet) and seen != {a['id'] for a in packet['accounts']}:
        raise ValueError('Work groups must include every saved account exactly once')


def validate_timeline_reading(packet, check_text, keys):
    reading = packet.get('presentation', {}).get('timelineReading')
    if reading is None: return
    keys(reading, ['contextSha256', 'periods', 'years'], 'Timeline reading')
    if not isinstance(reading.get('contextSha256'), str) or not re.fullmatch('[a-f0-9]{64}', reading['contextSha256']):
        raise ValueError('Timeline reading needs an evidence fingerprint')
    periods = packet.get('timeline', [])
    accounts = {a['id'] for a in packet['accounts']}
    fresh = reading['contextSha256'] == evidence_fingerprint(packet)
    for group, allowed in [('periods', {p['id'] for p in periods}), ('years', {y for p in periods for y in period_years(p)})]:
        entries = reading.get(group)
        if not isinstance(entries, dict) or len(entries) > 240 or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_ -]{0,99}', key) for key in entries) or (fresh and set(entries) - allowed):
            raise ValueError('Timeline reading must reference saved ' + group)
        for entry in entries.values():
            keys(entry, ['title', 'bullets', 'accountIds'] if group == 'periods' else ['title', 'bullets'], 'Timeline reading entry')
            check_text(entry.get('title'), 'Timeline reading title', 160)
            if not entry['title'].strip(): raise ValueError('Timeline reading title must not be blank')
            lines = entry.get('bullets')
            if not isinstance(lines, list) or not 1 <= len(lines) <= 3:
                raise ValueError('Timeline reading needs one to three bullets')
            for line in lines:
                check_text(line, 'Timeline reading bullet', 600)
                if not line.strip(): raise ValueError('Timeline reading bullets must not be blank')
            if group == 'periods':
                ids = entry.get('accountIds')
                if not isinstance(ids, list) or len(ids) > 300 or any(not isinstance(i, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', i) for i in ids) or len(set(ids)) != len(ids) or (fresh and set(ids) - accounts):
                    raise ValueError('Timeline reading links must resolve without duplicates')


def timeline_html(packet):
    periods = packet.get('timeline', [])
    if not periods:
        return '<p class="empty">No dated career timeline recorded yet. Add supported periods from your work history.</p>'
    accounts = {a['id']: a for a in packet['accounts']}
    stories = {s['id'] for s in packet.get('interview', {}).get('stories', [])}
    reading = timeline_reading(packet)
    index, body = [], []
    years = sorted({y for p in periods for y in period_years(p)})
    for year in years:
        index.append(f'<div class="timeline-year" data-year="{esc(year)}"><button type="button" class="timeline-year-label js-only" data-year="{esc(year)}" aria-pressed="false">{esc(year)}</button><span class="no-script">{esc(year)}</span><div class="timeline-periods">')
        for ordinal, period in enumerate(periods):
            if year not in period_years(period):
                continue
            # Keep multi-year labels intact; removing the start year creates "–2026".
            short = period['period'] if len(period_years(period)) > 1 else period['period'].replace(year, '', 1).strip() or year
            index.append(f'<a href="#quarter-{esc(period["id"])}" data-period-index="{ordinal}" aria-label="{esc(period["period"] + ": " + period["title"])}" title="{esc(period["title"])}"><span>{esc(short)}</span></a>')
        index.append('</div></div>')
    for ordinal, period in enumerate(periods):
        key = esc(period['id'])
        year = period_year(period)
        brief = reading.get('periods', {}).get(period['id'])
        title = brief['title'] if brief else period['title']
        account_ids = list(dict.fromkeys(period['accountIds'] + (brief['accountIds'] if brief else [])))
        work = ''.join(f'<a href="#account-{esc(aid)}">{esc(accounts[aid]["title"])} <span aria-hidden="true">↗</span></a>'
                       for aid in account_ids)
        practice = ''.join(f'<a href="#prep-story-{esc(aid)}">Practise: {esc(accounts[aid]["title"])} <span aria-hidden="true">→</span></a>'
                           for aid in account_ids if aid in stories)
        next_links = ''.join(f'<a href="#quarter-{esc(periods[i]["id"])}">{label} {esc(periods[i]["period"])}</a>'
                             for i, label in [(ordinal - 1, '←'), (ordinal + 1, '→')] if 0 <= i < len(periods))
        readings = ''.join(f'<section><h4>{label}</h4>{paragraphs(period[field])}</section>'
                           for field, label in [('tension', 'Pressure & limits'), ('approach', 'Change in approach')]
                           if period[field])
        original = f'<div class="quarter-focus">{paragraphs(period["focus"])}</div><h4>The work</h4>{bullets(period["actions"])}<div class="quarter-interpretation">{readings}</div>'
        content = (f'<div class="period-brief">{bullets(brief["bullets"])}</div><details class="section-detail"><summary>Full period record</summary><h4>{esc(period["title"])}</h4>{original}</details>' if brief else original)
        body.append(f'''<details class="quarter-reading" id="quarter-{key}"><summary><span class="period">{esc(period['period'])}</span><strong>{esc(title)}</strong><span aria-hidden="true">+</span></summary><div class="quarter-body">
{content}
<details class="section-detail"><summary>Sources &amp; open questions</summary>{bullets(period['questions'])}{references(packet, period['sourceRefs'])}</details>
<div class="related-work">{work}{practice}</div><nav class="period-next" aria-label="Adjacent career periods">{next_links}</nav></div></details>''')
    overviews = ''.join(f'<section class="year-overview" data-overview-year="{esc(year)}"><h3>{esc(entry["title"])}</h3>{bullets(entry["bullets"])}</section>' for year, entry in reading.get('years', {}).items())
    options = ''.join(f'<option value="{esc(p["id"])}">{esc(p["period"])}</option>' for p in periods)
    year_picker = '<label class="timeline-year-picker js-only" for="timeline-year-select">Year<select id="timeline-year-select"><option value="" disabled>Selected range</option>' + ''.join(f'<option value="{esc(y)}">{esc(y)}</option>' for y in years) + '</select></label>'
    return (year_picker + '<div class="timeline-layout"><nav class="period-index" aria-label="Select career years and periods">'
            + ''.join(index) + '</nav><div class="timeline-content"><div class="timeline-selection js-only"><div class="timeline-range-summary"><strong id="timeline-range-label"></strong><span id="timeline-range-count"></span><a id="timeline-work" href="#work">View work →</a><a id="timeline-sources" href="#sources">Sources ↗</a></div><details class="timeline-use"><summary>Use this context</summary><div class="timeline-brief-controls"><label><span class="sr-only">Use selected context for</span><select id="timeline-purpose"><option value="patterns">Patterns</option><option value="cv">CV bullets</option><option value="interview">Interview</option><option value="profile">Profile</option></select></label><button type="button" id="timeline-copy" class="primary">Copy prompt</button><details class="timeline-options"><summary>Adjust dates &amp; sources</summary><div class="timeline-dates"><label>From<select id="timeline-from">' + options + '</select></label><label>To<select id="timeline-to">' + options + '</select></label></div><label class="timeline-excerpts"><input type="checkbox" id="timeline-excerpts">Include source excerpts</label></details></div></details><p class="status" id="timeline-status" role="status"></p></div><div class="timeline-readings">' + overviews + ''.join(body) + '</div></div></div>')



def interview_html(packet):
    prep = packet.get('interview')
    if prep is None and not packet['accounts']:
        return '<p class="empty">No practice stories yet. Start with a work account and the question it could answer.</p>'
    prep = prep or {'stories': [], 'questions': [], 'opening': [], 'throughline': '', 'priorityGap': None}
    accounts = {a['id']: a for a in packet['accounts']}
    intro_options = ''.join(f'<details class="section-detail"><summary>{esc(o["title"])}</summary>{paragraphs(o["text"])}</details>' for o in prep.get('introOptions', []))
    opening = ''.join(paragraphs(p) for p in prep['opening'])
    body = []
    for story in prep['stories']:
        account, key = accounts[story['id']], esc(story['id'])
        chapters = ''.join(f'<li><h4>{esc(c["title"])}</h4>{paragraphs(c["text"])}</li>' for c in story['chapters'])
        pace = ''.join(f'<li><span class="period">{esc(m["when"])}</span>{paragraphs(m["text"])}</li>' for m in story['timeline'])
        questions = ''.join(f'<details class="section-detail answer"><summary>{esc(q["question"])}</summary><p class="question-tests">{esc(q["tests"])}</p>{paragraphs(q["answer"])}<details class="answer-reason"><summary>Why this example</summary>{paragraphs(q["reason"])}</details></details>' for q in prep['questions'] if q['storyId'] == story['id'])
        note = packet.get('rehearsal', {}).get('notes', {}).get(story['id'], story.get('practice', ''))
        body.append(f'''<details class="prep-story" id="prep-story-{key}"><summary><span class="period">{esc(account['period'])}</span><span class="story-label"><strong>{esc(account['title'])}</strong><span>{esc(story['takeaway'])}</span></span><span class="story-expand" aria-hidden="true">+</span></summary><div class="story-workspace">
<div class="practice-guide"><h3>Practise this story</h3><ol><li><strong>Set the scene.</strong> Name the problem and your responsibility.</li><li><strong>Explain a decision.</strong> What did you choose, and why?</li><li><strong>Give the result.</strong> Keep shared credit and unknowns clear.</li></ol><button type="button" class="path-primary js-only" data-practise-story="{key}">Copy practice prompt</button><p class="status" role="status" data-practice-status="{key}"></p></div>
<div class="practice-detail"><p class="question-tests">{esc(story['tests'])}</p>{questions}
<details class="section-detail"><summary>Story &amp; sequence</summary><ol class="story-chapters">{chapters}</ol><ol class="story-pace">{pace}</ol></details>
<details class="section-detail"><summary>Shared work &amp; limits</summary>{paragraphs(account['sharedCredit'])}{bullets(account['limits'])}</details>
<details class="section-detail"><summary>What to sharpen</summary>{paragraphs(story.get('practice', ''))}{bullets(account['questions'])}</details>
<label class="rehearsal-editor js-only" for="rehearsal-{key}">Your answer &amp; practice notes<textarea id="rehearsal-{key}" data-rehearsal="{key}" maxlength="15000" rows="5">{esc(note)}</textarea></label>
<div class="no-script" data-rehearsal-display="{key}">{paragraphs(note)}</div>
<div class="related-work"><a href="#account-{key}">Work account &amp; sources ↗</a></div></div></div></details>''')
    gap = prep['priorityGap']
    gap_html = f'<details class="section-detail"><summary>One question to resolve</summary><h4>{esc(gap["question"])}</h4>{paragraphs(gap["why"])}</details>' if gap else ''
    prepared = {s['id'] for s in prep['stories']}
    missing = []
    for account in packet['accounts']:
        if account['id'] in prepared: continue
        key = esc(account['id'])
        missing.append(f'''<details class="prep-story prep-needed" id="prep-story-{key}"><summary><span class="period">{esc(account['period'])}</span><span class="story-label"><strong>{esc(account['title'])}</strong></span><span class="story-expand" aria-hidden="true">+</span></summary><div class="story-workspace">
<div class="practice-guide"><h3>Prepare this story</h3><p>Copy this account to your assistant to draft an answer, then practise one question at a time.</p><button type="button" class="path-primary js-only" data-prepare-story="{key}">Copy preparation prompt</button><p class="status" role="status" data-practice-status="{key}"></p></div>
<div class="practice-detail">{paragraphs(account['summary'])}<details class="section-detail"><summary>Shared work &amp; limits</summary>{paragraphs(account['sharedCredit'])}{bullets(account['limits'])}</details><div class="related-work"><a href="#account-{key}">Back to work account →</a></div></div></div></details>''')
    pending = ('<details class="practice-unprepared section-detail"><summary>Prepare another story · ' + str(len(missing)) + '</summary>' + ''.join(missing) + '</details>') if missing and body else ''.join(missing)
    intro = f'<div class="practice-introduction"><details class="opening section-detail"><summary>Introduce yourself</summary><div class="opening-text">{opening}</div>{intro_options}</details><details class="section-detail"><summary>How these stories fit together</summary>{paragraphs(prep["throughline"])}</details></div>' if packet.get('interview') else ''
    copy_all = '<button class="text-button js-only" id="copy-prep" type="button">Copy all preparation ↗</button>' if packet.get('interview') else ''
    return f'{intro}<div class="practice-stories">{"".join(body)}</div>{pending}{gap_html}<div class="practice-footer">{copy_all}<p id="prep-status" class="status" role="status"></p></div>'
