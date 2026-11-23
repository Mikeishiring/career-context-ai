"""Timeline and interview views for the single portable career document."""
import copy
from collections import Counter
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


def validate_experience_roles(packet, check_text, keys, image_bytes):
    roles = packet.get('presentation', {}).get('experienceRoles', [])
    if not isinstance(roles, list) or len(roles) > 80:
        raise ValueError('Experience supports up to 80 roles')
    ids, assigned = set(), set()
    account_ids = {a['id'] for a in packet['accounts']}
    source_ids = {s['id'] for s in packet['sources']}
    for role in roles:
        keys(role, ['id', 'title', 'organization', 'period', 'current', 'accountIds', 'sourceRefs', 'logo', 'personEdited'], 'Experience role')
        key = role.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', key) or key in ids:
            raise ValueError('Experience roles need unique safe IDs')
        ids.add(key)
        check_text(role.get('title'), 'Role or engagement', 160)
        if not role['title'].strip() or any(not isinstance(role.get(field, False), bool) for field in ('current', 'personEdited')):
            raise ValueError('A role needs a title and boolean flags')
        for field in ['organization', 'period']:
            check_text(role.get(field, ''), field, 160)
        for field, allowed in [('accountIds', account_ids), ('sourceRefs', source_ids)]:
            refs = role.get(field, [] if field == 'sourceRefs' else None)
            if not isinstance(refs, list) or any(not isinstance(k, str) or k not in allowed for k in refs) or len(set(refs)) != len(refs):
                raise ValueError('Invalid experience role ' + field)
        if assigned.intersection(role['accountIds']):
            raise ValueError('Choose one primary role per work example')
        assigned.update(role['accountIds'])
        if 'logo' in role:
            if not isinstance(role['logo'], str) or len(role['logo']) > 90000:
                raise ValueError('Role logo is too large')
            image_bytes(role['logo'])


def experience_heading(role):
    organization = role.get('organization', '')
    initials = ''.join(w[:1].upper() for w in (organization or role['title']).split()[:2])
    mark = f'<img src="{esc(role["logo"])}" alt="">' if role.get('logo') else esc(initials)
    meta = ' · '.join(filter(None, [organization, role.get('period'), 'Current' if role.get('current') else '']))
    return (f'<header class="experience-role-heading"><span class="role-mark" aria-hidden="true">{mark}</span>'
            f'<div><h3>{esc(role["title"])}</h3><p>{esc(meta)}</p></div></header>')


def context_overview(packet):
    """A private reading of saved context, with links back to the full accounts."""
    accounts = packet['accounts']
    rows = {a['id']: (
        f'<li><details class="experience-file" data-experience="{esc(a["id"])}"{" open" if i == 0 else ""}><summary>'
        '<span class="file-token" aria-hidden="true"><i></i></span>'
        f'<span><span class="context-period">{esc(a["period"]) or "Date not recorded"}</span>'
        f'<strong>{esc(a["title"])}</strong></span><span class="file-chevron" aria-hidden="true"></span>'
        f'</summary><div class="file-reading">{paragraphs(a["contribution"] or a["summary"])}'
        f'<a href="#account-{esc(a["id"])}">Read full account <span aria-hidden="true">→</span>'
        f'<span class="sr-only"> · {esc(a["title"])}</span></a>'
        + (f'<a class="file-revise" href="#path-review--{esc(a["id"])}">Review wording</a>' if packet.get('journey') else '')
        + '</div></details></li>'
        ) for i, a in enumerate(accounts)}
    roles = sorted(packet.get('presentation', {}).get('experienceRoles', []), key=lambda r: not r.get('current'))
    assigned = {key for role in roles for key in role['accountIds']}
    groups = ''.join('<section class="experience-role">' + experience_heading(role) + '<ol>' +
                     ''.join(rows[key] for key in role['accountIds']) + '</ol></section>' for role in roles)
    remaining = ''.join(row for key, row in rows.items() if key not in assigned)
    if remaining:
        groups += '<section class="ungrouped-experience">' + ('<h3>Other work</h3>' if roles else '') + '<ol>' + remaining + '</ol></section>'
    register = (f'<section class="context-register"><div class="context-section-heading"><h2 id="experience-heading">{"Work experience" if roles else "Work examples"}</h2>'
                '<button type="button" class="text-button js-only" id="edit-experience">Edit experience</button></div>'
                f'<div id="experience-groups">{groups}</div><p id="experience-status" role="status"></p></section>')
    questions = [(a, q) for a in accounts for q in a['questions']][:3]
    groups = {}
    for account, question in questions:
        groups.setdefault(account['id'], []).append(question)
    gaps = ''.join(
        f'<div class="account-gaps" data-gap-for="{esc(a["id"])}">'
        f'<a href="#account-{esc(a["id"])}">{esc(a["title"])} <span aria-hidden="true">↗</span></a>'
        + bullets(groups[a['id']]) + '</div>' for a in accounts if a['id'] in groups)
    gaps = f'<section class="context-questions"><h2>What your AI still needs to ask</h2>{gaps}</section>' if gaps else ''
    return f'<div class="context-collection">{register}{gaps}</div>' if register or gaps else ''


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



AUDIENCES = {'recruiter': 'Recruiter', 'manager': 'Hiring manager', 'panel': 'Panel'}


def walkthrough_question(account):
    title = account['title'].strip().rstrip('.')
    if re.match(r"^[A-Za-z]+ing\s", title) and len(title) <= 90:
        return 'Can you walk me through ' + title[0].lower() + title[1:] + '?'
    return 'Can you walk me through one example in your own words?'


def spoken_clause(text):
    """Embed a short recorded clause in an interviewer's sentence."""
    text = text.strip().rstrip('.')
    text = re.sub(r'\b(I was|I am|I have|I|my|me)\b',
                  lambda m: {'I was':'you were', 'I am':'you are', 'I have':'you have', 'I':'you', 'my':'your', 'me':'you'}[m[0]], text)
    return re.sub(r'^(The|A|An|Two|One|Three|Four|Five|Six|Several|Most|Some|All)\b', lambda m: m[0].lower(), text)


def panel_question(account):
    """Use an affirmative event as part of the spoken question. Otherwise name the work."""
    topic = account['title'].strip().rstrip('.?!')
    credit = account['sharedCredit'].strip()
    result = account['outcome'].strip()
    # Only compose with short clauses. Negation, pronouns without antecedents and
    # multi-part notes are safer to explore through the topic than to reinterpret.
    def clauses(text):
        for line in re.split(r'[.!?](?:\s+|$)', text):
            line = line.strip()
            if (0 < len(line) <= 110 and not re.search(r'[;:"“”\n]|\b(?:no|not|never|if|might|would|could|will|yet|pending|they|it|this|that|we|our)\b|n[’\']t\b',line,re.I)
                    and re.match(r'(?:The|A|An|I)\s', line)):
                yield spoken_clause(line)

    credits = list(clauses(credit))
    for clause in credits:
        if re.search(r'\b(?:approved|authori[sz]ed|signed off on)\s+\S', clause):
            return f'What input, if any, did you have when {clause}?'
    for clause in credits:
        if re.search(r'\b(?:chose|decided|selected)\s+\S', clause):
            return f'Did you have any say when {clause}?'
        handoff = re.fullmatch(r'.+? (?:checked|reviewed|verified) (.+?) after (you (?:handed|passed|sent|delivered) .+)', clause)
        if handoff:
            return f'After {handoff[2]}, what could you say firsthand about {handoff[1]}?'
        if re.search(r'\b(?:supplied|provided|delivered)\s+\S', clause):
            return f'What part, if any, did you play when {clause}?'

    first_result = re.split(r'[.!?](?:\s+|$)', result, maxsplit=1)[0]
    subset = re.fullmatch(r'([\w-]+ of (?:the |your |my )?[\w -]+?) (still )?(had|showed) ((?:a|an|the) [\w -]+)', first_result, re.I)
    if subset:
        verb = 'having' if subset[3].lower() == 'had' else 'showing'
        return f'What could you conclude from {spoken_clause(subset[1])} {subset[2] or ""}{verb} {subset[4]}?'
    outcome = next(clauses(result), '')
    if credit and outcome and not outcome.startswith('you '):
        return f'How did you learn that {outcome}?'
    if outcome and re.search(r'\b(?:reached|went to|was sent to)\b', outcome):
        return f'What did you learn, if anything, after {outcome}?'

    # Keep the actual story title intact when it is a sentence or a proper name.
    if re.match(r'^[A-Za-z]+ing\s', topic):
        topic = topic[0].lower() + topic[1:]
    else:
        topic = spoken_clause(topic)
    if re.match(r'^(?:you|we|they|he|she)\s', topic, re.I):
        return f'In the story titled “{account["title"]}”, what can you tell us firsthand?'
    if credit:
        return f'Which parts of {topic} could you describe from your own experience?'
    if result:
        return f'What did you learn from {topic}, and what remained uncertain?'
    return f'What can you tell us firsthand about {topic}?'


def rehearsal_plan(account):
    """Pick the kind of follow-up supported by this account, independent of occupation."""
    credit, result = account['sharedCredit'].strip(), account['outcome'].strip()
    action = account['contribution'] or account['summary']
    # A colleague's presence alone supplies no second action to explore.
    presence = re.fullmatch(r"[^.!?]+ (?:was|were|stood|sat) (?:there|beside me|with me|nearby|next to me)[.!]?", credit, re.I)
    one_action = not any(account[k] for k in ('decisions', 'outcome', 'aim', 'context')) and (not credit or presence)
    adds_detail = account['summary'].strip() not in ('', action.strip())
    if one_action and not adds_detail and len(action.split()) <= 30 and not re.search(r'[.!?]\s+\S|\b(?:after|because|instead|then)\b', action, re.I):
        return {'single': True, 'question': walkthrough_question(account)}
    return {'question': panel_question(account)}


def personally_attributed(verb, evidence):
    root = verb[:-3] if verb.endswith('ing') else verb
    stems = {root, root.rstrip('e')}
    if len(root) > 2 and root[-1] == root[-2]:
        stems.add(root[:-1])
    forms = {verb, *(s + ending for s in stems for ending in ('', 'e', 'd', 'ed', 'ing'))}
    if len(root) > 1:
        forms.update((root + root[-1] + 'ed', root + root[-1] + 'ing'))
    for family in ('write wrote written writing', 'make made making', 'choose chose chosen choosing',
                   'take took taken taking', 'send sent sending', 'build built building', 'run ran running'):
        if verb in family.split():
            forms.update(family.split())
    # I/we are deliberately distinct. A noun, a future intention, another person's
    # action or a negation cannot confirm the action was personally performed.
    direct = '|'.join(map(re.escape, forms))
    ongoing = '|'.join(map(re.escape, (f for f in forms if f.endswith('ing'))))
    return re.search(r'\bI\s+(?:(?:have|had)\s+)?(?:' + direct + r')\b|\bI was (?:' + ongoing + r')\b', evidence, re.I) is not None


def recorded_mark(question, verb_match, account):
    """Physical chalking supports marking the same item, in that direction only."""
    if verb_match[1] not in {'mark', 'marked', 'marking'}:
        return False
    before, after = question[:verb_match.start()], question[verb_match.end():]
    # Limit this inference to a simple object. Qualifiers such as "final" are
    # material. "It" needs a named antecedent in the question itself.
    item = re.match(r'\s+(?:the|a|an|your) ([a-z -]+?)(?=\s+(?:after|before|when)\b|[?.,!]|$)', after)
    if item:
        noun = item[1].strip()
    elif re.match(r'\s+it(?:[?.,!]|$)', after):
        item = re.search(r'\b(?:the|a|an|your) ([a-z-]+(?: [a-z-]+){0,3})\s*$', before)
        if not item:
            return False
        noun = item[1]
    else:
        return False
    if not noun or len(noun.split()) > 5:
        return False
    for field in ('contribution', 'summary'):
        for clause in re.split(r'[.!?;\n]', account[field].casefold()):
            chalk = re.fullmatch(r'\s*i (?:have |had )?chalk(?:ed)?\s+(.+)', clause)
            if not chalk or re.search(r'\b(?:up|if|unless|instead|but|and|while|before|after|without)\b|[,:"“”]', chalk[1]):
                continue
            objects = re.fullmatch(r'((?:a |an |the |my )?[\w -]+?)(?: (?:on|onto) ((?:the |my |a |an )?[\w -]+))?', chalk[1])
            if objects:
                for item in filter(None, objects.groups()):
                    if (not re.search(r'\b(?:beside|near|for|from|with|of|under|by|next|at|in|as)\b', item)
                            and re.search(r'\b' + re.escape(noun) + r'$', item)):
                        return True
    return False


def unsupported_action(question, account):
    """Return the first unchecked action, checking embedded premises before the main question."""
    evidence = ' '.join(account[k] for k in ('contribution', 'summary', 'context', 'sharedCredit', 'outcome'))
    for pattern in (r'\b(?:while|when|as) you were ([a-z]+ing)\b',
                    r'\b(?:after|before|when|once) you (?:had )?([a-z]+ed|wrote|made|chose|took|sent|built|ran)\b',
                    r'\bhow did you know (?:what|where|when|how) to ([a-z]+)\b',
                    r'\b(?:why|how|where|when) did you ([a-z]+)\b'):
        for match in re.finditer(pattern, question.lower()):
            verb = match[1]
            if (verb not in {'know', 'feel', 'learn', 'hear', 'find', 'get', 'see', 'think'}
                    and not personally_attributed(verb, evidence) and not recorded_mark(question.lower(), match, account)):
                return verb
    return None


def needs_panel_referent(question):
    """Catch standalone follow-ups which point back to an unnamed step, person or result."""
    return bool(re.search(r'^(?:once|when|after|before) (?:that|this)\b|'
                          r'^which of (?:those|these) (?:steps|parts|decisions)\b|'
                          r'\b(?:from that result|in that decision|at that point|about that part|do that|handle it)\??$|'
                          r'^what did you see that told you (?:he|she|they)\b', question.strip(), re.I))


def review_rehearsal(accounts, preparation, review_link=None):
    """A derived practice view. Preserve source accounts and saved preparation."""
    view = copy.deepcopy(preparation)
    by_id = {a['id']: a for a in accounts}
    findings = []
    if not view:
        return view, findings
    gap = view.get('priorityGap')
    if gap and review_link:
        question, reason = review_link(by_id[gap['storyId']], gap['question'])
        if reason:
            findings.append(dict(storyId=gap['storyId'], field='priorityGap', question=gap['question'], replacement=question, reason=reason))
            gap['question'] = question
            gap.pop('label', None)
    def question_key(value):
        return ' '.join(value.casefold().rstrip('?.! ').split())
    panel_questions = Counter(question_key(panel['question']) for story in view['stories']
                              if (panel := story.get('audiences', {}).get('panel')))
    for story in view['stories']:
        key = story['id']
        account = by_id[key]
        plan = rehearsal_plan(account)
        opening = account['contribution'] or account['summary'] or account['title']
        shared = story.get('walkthrough') or (plan['question'] if plan.get('single') else '')
        def check(question, location):
            if review_link:
                replacement, reason = review_link(account, question)
                if reason:
                    findings.append(dict(storyId=key, field=location, reason=reason, question=question, replacement=replacement))
                    return replacement
            action = unsupported_action(question, account)
            if not action:
                return question
            findings.append({'storyId': key, 'field': location, 'action': action, 'question': question})
            return walkthrough_question(account)
        panel_replacements = {}
        for listener, cue in story.get('audiences', {}).items():
            original = cue['question']
            cue['question'] = check(original, listener)
            if original != cue['question']:
                if unsupported_action(original, account):
                    cue['opening'] = opening
                if listener == 'panel':
                    panel_replacements[original] = cue['question']
            elif listener == 'panel' and not shared:
                repeated = panel_questions[question_key(original)] > 1
                if repeated or needs_panel_referent(original):
                    cue['question'] = plan['question']
                    panel_replacements[original] = cue['question']
                    findings.append({'storyId': key, 'field': listener, 'reason': 'Repeated panel question' if repeated else 'Panel question needs a named referent', 'question': original})
        questions = [q for q in view['questions'] if q['storyId'] == key]
        for q in questions:
            old = q['question']
            q['question'] = panel_replacements[old] if old in panel_replacements else check(old, 'interview question')
            if old != q['question']:
                q.pop('label', None)
                q.update(answer=opening, tests='Firsthand experience', reason=account['title'])
        if shared:
            story['walkthrough'] = check(shared, 'walkthrough')
            story.pop('audiences', None)
            if story['tests'].rstrip().endswith('?'):
                story['tests'] = 'Firsthand experience'
            if questions:
                first = questions[0]
                first.update(question=story['walkthrough'], answer=opening, tests='Firsthand experience', reason=account['title'])
                first.pop('label', None)
                view['questions'] = [q for q in view['questions'] if q['storyId'] != key or q is first]
        for finding in (f for f in findings if f['storyId'] == key):
            if story['tests'] == finding['question']:
                story['tests'] = 'Firsthand experience'
    return view, findings


def audience_reference(story):
    if story.get('walkthrough'):
        return f'<p><strong>Story question</strong> · {esc(story["walkthrough"])}</p>'
    angles = story.get('audiences', {})
    entries = ''.join(f'<h4>{label}</h4>{paragraphs(angles[key]["opening"])}'
                      f'<p><strong>Interviewer question</strong> · {esc(angles[key]["question"])}</p>'
                      for key, label in AUDIENCES.items() if key in angles)
    return f'<details class="reference section-detail audience-reference"><summary>Compare all openings</summary>{entries}</details>' if entries else ''


def rehearsal_json(element_id, value):
    encoded = html.escape(json.dumps(value, ensure_ascii=True), quote=False)
    return f'<template id="{element_id}">{encoded}</template>'


def audience_card(actions='', accounts=()):
    controls = ''.join(f'<label><input type="radio" name="prep-audience" value="{key}"'
                       + (' checked' if key == 'recruiter' else '') + f'><span>{label}</span></label>'
                       for key, label in AUDIENCES.items())
    plans = rehearsal_json('rehearsal-plans', {a['id']: rehearsal_plan(a) for a in accounts})
    return f'''{plans}<div class="audience-desk" id="audience-desk" hidden>
<fieldset class="audience-switch"><legend>Who are you speaking with?</legend><div class="audience-track">{controls}</div></fieldset>
<article class="audience-cue" aria-labelledby="cue-title"><div class="cue-top"><span class="cue-speaker" aria-hidden="true"><i></i><i></i><i></i></span><span id="cue-focus"></span></div>
<details class="cue-lines" open><summary id="cue-title">Example opening</summary><p class="cue-opening" id="cue-opening"></p></details>
<div class="cue-question"><strong>Interviewer question</strong><p id="cue-question"></p></div>
<details class="cue-evidence"><summary>Credit, outcome &amp; limits</summary><div id="cue-evidence"></div></details>{actions}</article>
<details id="cue-context" class="cue-context" hidden><summary>What your AI still needs to ask</summary><ul id="cue-gaps"></ul><button type="button" id="copy-clarification" class="quiet text-button" data-copy="clarification">Copy context prompt</button><p id="clarification-status" role="status"></p></details>
<p class="sr-only" id="cue-change" role="status"></p></div>'''


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
        practice = story.get('practice', '')
        practice_html = f'<details class="section-detail"><summary>Practice notes</summary>{paragraphs(practice)}</details>' if practice else ''
        note = packet.get('rehearsal', {}).get('notes', {}).get(story['id'], story.get('practice', ''))
        guide = '' if story.get('walkthrough') else '<ol><li><strong>Set the scene.</strong> Name the problem and your responsibility.</li><li><strong>Explain your approach.</strong> Describe a choice or action.</li><li><strong>Give the result.</strong> Keep shared credit and unknowns clear.</li></ol>'
        body.append(f'''<details class="prep-story" id="prep-story-{key}"><summary><span class="period">{esc(account['period'])}</span><span class="story-label"><strong>{esc(account['title'])}</strong><span>{esc(story['takeaway'])}</span></span><span class="story-expand" aria-hidden="true">+</span></summary><div class="story-workspace">
<div class="practice-guide"><h3>Practise this story</h3>{guide}<button type="button" class="path-primary js-only" data-practise-story="{key}">Copy practice prompt</button><p class="status" role="status" data-practice-status="{key}"></p></div>
<div class="practice-detail"><p class="question-tests">{esc(story['tests'])}</p>{'' if questions and story.get('walkthrough') else audience_reference(story)}{questions}
<details class="section-detail"><summary>Story &amp; sequence</summary><ol class="story-chapters">{chapters}</ol><ol class="story-pace">{pace}</ol></details>
<details class="section-detail"><summary>Shared work &amp; limits</summary>{paragraphs(account['sharedCredit'])}{bullets(account['limits'])}</details>
{practice_html}
<label class="rehearsal-editor js-only" for="rehearsal-{key}">Your answer &amp; practice notes<textarea id="rehearsal-{key}" data-rehearsal="{key}" maxlength="15000" rows="5">{esc(note)}</textarea></label>
<div class="no-script" data-rehearsal-display="{key}">{paragraphs(note)}</div>
<div class="related-work"><a href="#account-{key}">Work account &amp; sources ↗</a></div></div></div></details>''')
    gap = prep['priorityGap']
    gap_html = f'<details class="section-detail"><summary>Priority question for your AI</summary><h4>{esc(gap["question"])}</h4>{paragraphs(gap["why"])}</details>' if gap else ''
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
    review_link = '<a href="#story-review">Rate your stories →</a>' if packet.get('journey') else ''
    actions = ('<div class="cue-actions"><button type="button" class="path-primary" id="rehearse-copy">Copy rehearsal prompt</button>'
               '<a id="rehearse-notes">Story &amp; notes →</a></div><p role="status" id="rehearse-status"></p>')
    room = (f'<div class="rehearsal-room" id="rehearsal-room" hidden><div class="rehearsal-library"><h3>Your stories</h3>'
            f'<label class="sr-only" for="rehearsal-story">Choose a story</label><select id="rehearsal-story"></select>'
            f'<div id="rehearsal-list" aria-label="Your stories"></div><p id="rehearsal-interest"></p>{review_link}</div>{audience_card(actions, accounts.values())}'
            '<p id="rehearsal-empty" hidden>Choose a story to practise.</p></div>') if accounts else ''
    return f'{room}{intro}<div class="practice-stories">{"".join(body)}</div>{pending}{gap_html}<div class="practice-footer">{copy_all}<p id="prep-status" class="status" role="status"></p></div>'
