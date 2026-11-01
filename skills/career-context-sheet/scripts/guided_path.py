"""A guided review path; notes and progress never change career evidence."""
import html
import re

STEPS = ('gather', 'review', 'deepen', 'connect', 'write', 'practice')
LABELS = ('Your work', 'First draft', 'Go deeper', 'Your thread', 'Your voice', 'Practise')


def initial_state(packet, basis):
    return {'contextSha256': basis, 'updatedAt': 0,
            'current': 'review' if packet['accounts'] else 'gather',
            'completed': [], 'notes': {},
            'storyId': packet['accounts'][0]['id'] if packet['accounts'] else '',
            'baseline': {'overview': packet['person']['overview'],
                         'accounts': {a['id']: a['summary'] for a in packet['accounts']}}}


def validate(packet, check_text, keys):
    state = packet.get('journey')
    if state is None:
        return
    keys(state, ['contextSha256', 'updatedAt', 'current', 'completed', 'notes', 'storyId', 'baseline', 'writing'], 'Journey')
    if 'writing' in state:
        writing = state['writing']
        keys(writing, ['guideName', 'guideText', 'draft'], 'Writing')
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
    completed = len(packet['journey']['completed']) if packet['journey']['contextSha256'] == basis else 0
    icons = (
        '<path d="M5 7h6l2 3h14v15H5z"/><path d="M9 5h14v5"/>',
        '<path d="M8 5h12l5 5v17H8zM20 5v6h5M12 16h9M12 21h7"/>',
        '<circle cx="14" cy="14" r="8"/><path d="m20 20 7 7M10 14h8M14 10v8"/>',
        '<path d="M8 5v7c0 7 16 1 16 8v7M8 27v-8"/><circle cx="8" cy="5" r="3"/><circle cx="8" cy="27" r="3"/><circle cx="24" cy="27" r="3"/>',
        '<path d="m8 24 2-7L23 4l5 5-13 13-7 2zM19 8l5 5M6 28h20"/>',
        '<path d="M5 7h22v15H15l-7 5v-5H5zM11 12h10M11 17h7"/>',
    )
    nodes = ''.join(f'<li class="path-stop"><a id="path-link-{key}" href="#path-{key}" class="path-node" data-path-step="{key}" aria-label="{i+1}. {LABELS[i]}"><span class="path-token"><svg viewBox="0 0 32 32" aria-hidden="true">{icons[i]}</svg><span class="path-check" aria-hidden="true">✓</span></span><span class="path-label">{esc(LABELS[i])}</span><span class="path-state"></span></a></li>' for i, key in enumerate(STEPS))
    options = ''.join(f'<option value="{esc(a["id"])}">{esc(a["title"])}</option>' for a in packet['accounts'])
    return f'''<section id="path" class="document-view guided-path" aria-labelledby="path-title" data-evidence="{basis}">
<div class="path-heading"><div><h1 id="path-title">Your story.<br> One step at a time.</h1></div><div class="path-progress"><span id="path-count">{completed} of 6 steps reviewed</span><progress id="path-progress" max="6" value="{completed}" aria-label="Steps reviewed"></progress><button type="button" class="path-save js-only" id="path-save">Save full HTML <span aria-hidden="true">↓</span></button></div></div>
<div class="path-workspace js-only"><nav aria-label="Your career path" class="path-map"><svg class="path-route" aria-hidden="true"><path/></svg><ol>{nodes}</ol><a class="path-destination" href="#profile">Your public profile <span aria-hidden="true">↗</span></a></nav>
<article class="path-activity" aria-labelledby="path-activity-title"><div class="path-step-number" id="path-step-number"></div><h2 id="path-activity-title">Your first draft</h2>
<div id="path-story-picker"><label for="path-story">Work story</label><select id="path-story">{options}</select></div>
<div id="path-content"></div><div class="path-note-area"><label for="path-note">Your bullet notes</label><textarea id="path-note" maxlength="10000" rows="3" placeholder="• Keep…&#10;• Change…&#10;• Missing…"></textarea><p class="path-status" id="path-status" role="status"></p><button type="button" class="path-secondary" id="path-copy" hidden>Copy review notes</button></div>
<div class="path-actions"><button type="button" id="path-continue" class="path-primary">Reviewed · Next <span aria-hidden="true">→</span></button><button type="button" id="path-reopen" class="path-secondary" hidden>Mark unreviewed</button></div>
<p class="path-finish" id="path-finish" hidden>Review complete. Choose what to share in your profile.</p></article></div>
<div class="no-script"><ol><li><a href="#sources">Review collected material</a></li><li><a href="#work">Read your work accounts</a></li><li><a href="#timeline">Connect the chapters</a></li><li><a href="#interview">Practise your stories</a></li></ol></div>
</section>'''
