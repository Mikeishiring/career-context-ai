"""A guided review path; notes and progress never change career evidence."""
import html
import re

STEPS = ('gather', 'review', 'deepen', 'connect', 'write', 'practice')
LABELS = ('Collect context', 'Review accounts', 'Resolve gaps', 'Connect the pieces', 'Your voice', 'Practise')
CORE_STEPS = STEPS[:-1]  # Keep legacy practice state readable without making it a requirement.


def month_number(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value):
        raise ValueError('Use a month in YYYY-MM format')
    year, month = map(int, value.split('-'))
    if not 1900 <= year <= 2199:
        raise ValueError('Coverage year must be between 1900 and 2199')
    return year * 12 + month - 1


def initial_coverage(packet):
    return {'startMonth': '', 'endMonth': '', 'streams': [
        {'id': 'source-' + str(i + 1), 'platform': c['platform'],
         'location': c['location'], 'scope': c['scope']}
        for i, c in enumerate(packet.get('collection', []))], 'checks': []}


def validate_coverage(value, source_ids, check_text, keys):
    """Receipts describe an inspected interval; existing source dates prove no coverage."""
    keys(value, ['startMonth', 'endMonth', 'streams', 'checks'], 'Coverage')
    start, end = value.get('startMonth'), value.get('endMonth')
    if (start, end) != ('', ''):
        if not 0 <= month_number(end) - month_number(start) < 600:
            raise ValueError('Coverage range must be ordered and at most 600 months')
    streams = value.get('streams')
    if not isinstance(streams, list) or len(streams) > 80:
        raise ValueError('Coverage needs at most 80 source locations')
    stream_ids = set()
    for stream in streams:
        keys(stream, ['id', 'platform', 'location', 'scope'], 'Coverage source')
        sid = stream.get('id')
        if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', sid) or sid in stream_ids:
            raise ValueError('Coverage sources need unique safe IDs')
        stream_ids.add(sid)
        for field, limit in [('platform', 3000), ('location', 3000), ('scope', 3000)]:
            check_text(stream.get(field), 'Coverage ' + field, limit)
        if not stream['platform'].strip() or not stream['location'].strip():
            raise ValueError('Name the platform and source location')
    checks = value.get('checks')
    if not isinstance(checks, list) or len(checks) > 48000:
        raise ValueError('Invalid coverage receipts')
    seen, used = set(), set()
    for item in checks:
        keys(item, ['streamId', 'month', 'status', 'note', 'sourceRefs', 'cursor', 'found', 'read'], 'Coverage receipt')
        pair = (item.get('streamId'), item.get('month'))
        if not all(isinstance(x, str) for x in pair) or pair[0] not in stream_ids or pair in seen:
            raise ValueError('Coverage receipts need unique source/month pairs')
        seen.add(pair)
        if not start or not month_number(start) <= month_number(pair[1]) <= month_number(end):
            raise ValueError('Coverage receipt is outside the selected range')
        if item.get('status') not in ['pending', 'in_progress', 'checked', 'empty', 'blocked', 'excluded']:
            raise ValueError('Invalid coverage receipt status')
        for field, limit in [('note', 2000), ('cursor', 1000)]:
            check_text(item.get(field), 'Coverage ' + field, limit)
        refs = item.get('sourceRefs')
        if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs) or len(set(refs)) != len(refs) or set(refs) - source_ids:
            raise ValueError('Coverage references must resolve to included sources')
        used.update(refs)
        for field in ['found', 'read']:
            if type(item.get(field)) is not int or not 0 <= item[field] <= 1000000:
                raise ValueError('Coverage counts must be nonnegative integers')
        if item['read'] > item['found']:
            raise ValueError('Read count cannot exceed discovered count')
        if item['status'] in ['checked', 'empty', 'blocked', 'excluded'] and not item['note'].strip():
            raise ValueError('Record the check, limitation or exclusion reason')
        if item['status'] == 'checked' and (not refs or not item['read'] or item['cursor'].strip() or item['read'] != item['found']):
            raise ValueError('Checked coverage needs sources, all selected records read and no pending cursor')
        if item['status'] == 'empty' and (item['found'] or item['read'] or refs or item['cursor'].strip()):
            raise ValueError('An empty search must have no records or pending cursor')
    return used


def initial_state(packet, basis):
    return {'contextSha256': basis, 'updatedAt': 0,
            'current': 'gather',
            'completed': [], 'notes': {},
            'writing': {'mode': 'own_skill', 'guideName': '', 'guideText': '', 'draft': ''},
            'reviews': {}, 'coverage': initial_coverage(packet),
            'storyId': packet['accounts'][0]['id'] if packet['accounts'] else '',
            'baseline': {'overview': packet['person']['overview'],
                         'accounts': {a['id']: a['summary'] for a in packet['accounts']}}}


def validate(packet, check_text, keys):
    state = packet.get('journey')
    if state is None:
        return
    keys(state, ['contextSha256', 'updatedAt', 'current', 'completed', 'notes', 'storyId', 'baseline', 'writing', 'reviews', 'coverage'], 'Journey')
    if 'writing' in state:
        writing = state['writing']
        keys(writing, ['guideName', 'guideText', 'draft', 'mode'], 'Writing')
        if 'mode' in writing and writing['mode'] not in ['own_skill', 'custom']:
            raise ValueError('Unknown writing style mode')
        for field, limit in [('guideName', 200), ('guideText', 20000), ('draft', 3000)]:
            check_text(writing.get(field), 'Writing ' + field, limit)
    if not isinstance(state.get('contextSha256'), str) or not re.fullmatch('[a-f0-9]{64}', state['contextSha256']):
        raise ValueError('Journey needs its evidence fingerprint')
    if type(state.get('updatedAt')) is not int or not 0 <= state['updatedAt'] <= 9007199254740991:
        raise ValueError('Journey needs a safe nonnegative update time')
    if state.get('current') not in STEPS:
        raise ValueError('Unknown journey step')
    done = state.get('completed')
    if not isinstance(done, list) or any(type(x) is not str or x not in STEPS for x in done) or len(set(done)) != len(done):
        raise ValueError('Journey completion must contain unique known steps')
    ids = {a['id'] for a in packet['accounts']}
    source_ids = {s['id'] for s in packet['sources']}
    if 'coverage' in state:
        validate_coverage(state['coverage'], source_ids, check_text, keys)
    reviews = state.get('reviews', {})
    if not isinstance(reviews, dict) or set(reviews) - ids:
        raise ValueError('Reviews must refer to existing accounts')
    for review in reviews.values():
        keys(review, ['decision', 'draft', 'reason', 'sourceRefs', 'depth', 'practised'], 'Account review')
        if review.get('decision') not in ['pending', 'kept', 'revision', 'needs_evidence'] or review.get('depth') not in ['pending', 'clear', 'open']:
            raise ValueError('Invalid account review state')
        if type(review.get('practised')) is not bool:
            raise ValueError('Practice state must be boolean')
        for field, limit in [('draft', 6000), ('reason', 2000)]:
            check_text(review.get(field), 'Review ' + field, limit)
        refs = review.get('sourceRefs')
        if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs) or len(set(refs)) != len(refs) or set(refs) - source_ids:
            raise ValueError('Review references must resolve to included sources')
        if review['decision'] == 'revision' and (not review['draft'].strip() or not review['reason'].strip() or not refs):
            raise ValueError('A chosen revision needs wording, a reason and source references')
        if review['decision'] == 'needs_evidence' and not review['reason'].strip():
            raise ValueError('An unresolved correction needs a reason')
    if state.get('storyId') not in ids | {''}:
        raise ValueError('Journey story must exist')
    notes = state.get('notes')
    allowed = set(STEPS) | {step + ':' + key for step in ('review', 'deepen', 'practice') for key in ids}
    if not isinstance(notes, dict) or set(notes) - allowed:
        raise ValueError('Journey notes must refer to a step or story')
    for note in notes.values():
        check_text(note, 'Journey note', 10000)
    baseline = state.get('baseline')
    keys(baseline, ['overview', 'accounts'], 'Journey first draft')
    check_text(baseline.get('overview'), 'First overview')
    summaries = baseline.get('accounts')
    if not isinstance(summaries, dict) or set(summaries) - ids:
        raise ValueError('First draft must refer to existing accounts')
    for summary in summaries.values():
        check_text(summary, 'First account summary')


def render(packet, basis):
    if 'journey' not in packet:
        return ''
    esc = lambda text: html.escape(str(text), quote=True)
    icons = (
        '<path d="M5 7h6l2 3h14v15H5z"/><path d="M9 5h14v5"/>',
        '<path d="M8 5h12l5 5v17H8zM20 5v6h5M12 16h9M12 21h7"/>',
        '<circle cx="14" cy="14" r="8"/><path d="m20 20 7 7M10 14h8M14 10v8"/>',
        '<path d="M8 5v7c0 7 16 1 16 8v7M8 27v-8"/><circle cx="8" cy="5" r="3"/><circle cx="8" cy="27" r="3"/><circle cx="24" cy="27" r="3"/>',
        '<path d="m8 24 2-7L23 4l5 5-13 13-7 2zM19 8l5 5M6 28h20"/>',
        '<path d="M5 7h22v15H15l-7 5v-5H5zM11 12h10M11 17h7"/>',
    )
    nodes = ''.join(f'<li class="path-stop"><a id="path-link-{key}" href="#path-{key}" class="path-node" data-path-step="{key}" aria-label="{i+1}. {LABELS[i]}"><span class="path-token"><svg viewBox="0 0 32 32" aria-hidden="true">{icons[i]}</svg><span class="path-check" aria-hidden="true">✓</span></span><span class="path-label">{esc(LABELS[i])}</span><span class="path-state"></span></a></li>' for i, key in enumerate(CORE_STEPS))
    options = ''.join(f'<option value="{esc(a["id"])}">{esc(a["title"])}</option>' for a in packet['accounts'])
    return f'''<section id="path" class="document-view guided-path" aria-labelledby="path-title" data-evidence="{basis}">
<div class="path-heading"><h1 id="path-title">Build your career context</h1><div class="path-progress"><span id="path-count">Review progress</span><progress id="path-progress" max="{len(packet['accounts']) or 1}" value="0" aria-label="Accounts reviewed"></progress><button type="button" class="path-save js-only" id="path-save">Save full HTML <span aria-hidden="true">↓</span></button></div></div>
<div class="path-workspace js-only"><details class="path-map-shell" open><summary>Full path</summary><nav aria-label="Your career path" class="path-map"><svg class="path-route" aria-hidden="true"><path/></svg><ol>{nodes}</ol><a class="path-destination" href="#profile">Choose what to share <span aria-hidden="true">↗</span></a></nav></details>
<article class="path-activity" aria-labelledby="path-activity-title"><div class="path-step-number" id="path-step-number"></div><h2 id="path-activity-title">Your first draft</h2>
<div id="path-story-picker"><label for="path-story">Work account</label><select id="path-story">{options}</select><div class="review-queue"><span id="path-account-count"></span><button type="button" class="path-secondary" id="path-next-account">Next unreviewed account</button></div></div>
<div id="path-content"></div><div class="path-note-area"><label for="path-note">Your bullet notes</label><textarea id="path-note" maxlength="10000" rows="3" placeholder="• Keep…&#10;• Change…&#10;• Missing…"></textarea><button type="button" class="path-secondary" id="path-copy" hidden>Copy review notes</button></div><p class="path-status" id="path-status" role="status"></p>
<div class="path-actions"><button type="button" id="path-continue" class="path-primary">Reviewed · Next <span aria-hidden="true">→</span></button><button type="button" id="path-reopen" class="path-secondary" hidden>Mark unreviewed</button></div>
<p class="path-finish" id="path-finish" hidden>Context review complete for this scope. You can revisit it as your experience grows.</p></article></div>
<div class="no-script"><ol><li><a href="#sources">Review collected material</a></li><li><a href="#work">Read your work accounts</a></li><li><a href="#timeline">Connect the chapters</a></li><li><a href="#profile">Choose what to share</a></li></ol></div>
</section>'''
