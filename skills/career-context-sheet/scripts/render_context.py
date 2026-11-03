"""Render portable career context with no dependencies or network access."""
import argparse
import base64
import copy
import hashlib
import html
import importlib.util
import json
import os
import re
import tempfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
TEXT_FIELDS = ['title', 'period', 'summary', 'context', 'aim', 'contribution', 'sharedCredit', 'outcome']
LIST_FIELDS = ['decisions', 'limits', 'questions', 'sourceRefs']
KINDS = {'person_account', 'source_excerpt', 'redacted_excerpt', 'archive_summary', 'artifact_record'}
MIMES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif'}
MAX_SOURCES = 2048
MAX_PACKET_BYTES = 24 * 1024 * 1024
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024


def load_helper(name):
    spec = importlib.util.spec_from_file_location('career_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sections = load_helper('document_sections')
memory = load_helper('context_memory')
guided_path = load_helper('guided_path')
public_profile = load_helper('public_profile')
_interview_renderer = None

def check_text(value, label, maximum=100_000):
    if not isinstance(value, str) or '\0' in value or len(value) > maximum:
        raise ValueError(f'{label} must be text of at most {maximum} characters, without NULs')

def keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f'{label} has an unsupported field or is not an object')

def validate(data):
    keys(data, ['schema', 'updatedAt', 'reviewStatus', 'person', 'accounts', 'sources', 'synthetic', 'profile', 'collection', 'presentation', 'timeline', 'interview', 'rehearsal', 'journey', 'publicProfile', 'memory'], 'Sheet')
    if 'presentation' in data:
        presentation = data['presentation']
        keys(presentation, ['headline', 'files', 'briefs', 'timelineSelection', 'timelineReading', 'workGroups'], 'Presentation')
        check_text(presentation.get('headline', ''), 'Headline', 160)
        files = presentation.get('files', [])
        if not isinstance(files, list) or len(files) > 10: raise ValueError('Invalid related files')
        for item in files:
            keys(item, ['label', 'path'], 'Related file')
            check_text(item['label'], 'File label', 100)
            if not isinstance(item['path'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*\.(?:html|pdf|txt|json|sqlite)', item['path']):
                raise ValueError('Related files must be simple sibling filenames')
    if 'synthetic' in data and not isinstance(data['synthetic'], bool):
        raise ValueError('synthetic must be true or false')
    if data.get('schema') != 'career-context/v1' or data.get('reviewStatus') not in ['draft', 'person_reviewed']:
        raise ValueError('Unsupported schema or review status')
    date.fromisoformat(data['updatedAt'])
    person = data['person']; keys(person, ['name', 'overview', 'background'], 'Person')
    for field in ['name', 'overview']: check_text(person[field], field)
    if not isinstance(person.get('background', []), list): raise ValueError('Background must be a list')
    for line in person.get('background', []): check_text(line, 'Background item')
    if 'profile' in data:
        keys(data['profile'], ['disciplines', 'targetRoles', 'emphasis', 'referenceNotes'], 'Profile')
        for field in ['disciplines', 'targetRoles', 'emphasis']:
            items = data['profile'].get(field, [])
            if not isinstance(items, list) or len(items) > 20: raise ValueError(f'Invalid profile {field}')
            for item in items: check_text(item, field, 500)
        check_text(data['profile'].get('referenceNotes', ''), 'Reference notes', 3000)
    if not isinstance(data.get('collection', []), list) or len(data.get('collection', [])) > 80:
        raise ValueError('Invalid source collection inventory')
    for location in data.get('collection', []):
        keys(location, ['platform', 'location', 'access', 'status', 'scope', 'nextStep'], 'Collection location')
        for field in ['platform', 'location', 'scope', 'nextStep']: check_text(location[field], field, 3000)
        if location['access'] not in ['connector', 'export', 'supplied', 'unavailable']:
            raise ValueError('Invalid collection access')
        if location['status'] not in ['not_started', 'partial', 'read', 'blocked', 'excluded']:
            raise ValueError('Invalid collection status')
    for field, maximum in [('accounts', 80), ('sources', MAX_SOURCES)]:
        if not isinstance(data[field], list): raise ValueError(f'{field} must be a list')
        if len(data[field]) > maximum: raise ValueError(f'{field} has {len(data[field])} entries; maximum is {maximum}')
        if any(not isinstance(item, dict) for item in data[field]):
            raise ValueError(f'{field} entries must be objects')
        ids = [item.get('id') for item in data[field]]
        if any(not isinstance(i, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}', i) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError(f'{field} need unique safe IDs')
    source_ids = {s['id'] for s in data['sources']}; used = set(); artifact_ids = set()
    selection = data.get('presentation', {}).get('timelineSelection')
    if selection is not None:
        keys(selection, ['contextSha256', 'updatedAt', 'fromId', 'toId', 'purpose', 'year'], 'Timeline selection')
        if not isinstance(selection.get('contextSha256'), str) or not re.fullmatch('[a-f0-9]{64}', selection['contextSha256']):
            raise ValueError('Timeline selection needs an evidence fingerprint')
        if type(selection.get('updatedAt')) is not int or not 0 <= selection['updatedAt'] <= 9007199254740991:
            raise ValueError('Timeline selection needs a safe update time')
        period_ids = [p.get('id') for p in data.get('timeline', [])]
        if selection.get('fromId') not in period_ids or selection.get('toId') not in period_ids:
            raise ValueError('Timeline selection must reference saved periods')
        if period_ids.index(selection['fromId']) > period_ids.index(selection['toId']):
            raise ValueError('Timeline selection must run forward')
        if selection.get('purpose') not in ['patterns', 'cv', 'interview', 'profile']:
            raise ValueError('Unknown timeline purpose')
        if 'year' in selection:
            selected = data['timeline'][period_ids.index(selection['fromId']):period_ids.index(selection['toId']) + 1]
            if not isinstance(selection['year'], str) or not any(selection['year'] in sections.period_years(p) for p in selected):
                raise ValueError('Timeline year must intersect the selected saved periods')
    sections.validate_timeline_reading(data, check_text, keys)
    sections.validate_work_groups(data, check_text, keys)
    briefs = data.get('presentation', {}).get('briefs')
    if briefs is not None:
        keys(briefs, ['contextSha256', 'accounts'], 'Work briefs')
        if not isinstance(briefs.get('contextSha256'), str) or not re.fullmatch('[a-f0-9]{64}', briefs['contextSha256']):
            raise ValueError('Work briefs need their evidence fingerprint')
        entries = briefs.get('accounts')
        if not isinstance(entries, dict) or set(entries) - {a['id'] for a in data['accounts']}:
            raise ValueError('Work briefs must reference saved accounts')
        for lines in entries.values():
            if not isinstance(lines, list) or not 1 <= len(lines) <= 4:
                raise ValueError('Each work brief needs one to four bullets')
            for line in lines:
                check_text(line, 'Work brief bullet', 600)
                if not line.strip(): raise ValueError('Work brief bullets must not be blank')
    for source in data['sources']:
        keys(source, ['id', 'label', 'kind', 'content', 'scope', 'date', 'locator'], 'Source')
        if source['kind'] not in KINDS: raise ValueError('Invalid source kind')
        for field in ['label', 'content', 'scope']: check_text(source[field], field)
        for field in ['date', 'locator']:
            if field in source: check_text(source[field], field)
    for account in data['accounts']:
        keys(account, ['id', *TEXT_FIELDS, *LIST_FIELDS, 'artifacts', 'tags', 'capabilities'], 'Account')
        if not isinstance(account.get('tags', []), list) or len(account.get('tags', [])) > 20: raise ValueError('Invalid account tags')
        for tag in account.get('tags', []): check_text(tag, 'Account tag', 200)
        capabilities = account.get('capabilities', [])
        if not isinstance(capabilities, list) or len(capabilities) > 30:
            raise ValueError('Capabilities must be a list of at most 30 entries')
        for capability in capabilities:
            keys(capability, ['name', 'kind', 'application', 'assistance', 'limits'], 'Capability')
            if capability.get('kind') not in ['practice', 'tool']:
                raise ValueError('Capability kind must be practice or tool')
            for field, maximum in [('name', 200), ('application', 3000), ('assistance', 3000)]:
                check_text(capability.get(field), 'Capability ' + field, maximum)
                if not capability[field].strip():
                    raise ValueError('Capability ' + field + ' must not be blank')
            limits = capability.get('limits')
            if not isinstance(limits, list) or len(limits) > 20:
                raise ValueError('Capability limits must be a list of at most 20 entries')
            for limit in limits:
                check_text(limit, 'Capability limit', 1000)
                if not limit.strip(): raise ValueError('Capability limit must not be blank')
        for field in TEXT_FIELDS: check_text(account[field], field)
        for field in LIST_FIELDS:
            if not isinstance(account[field], list): raise ValueError(f'{field} must be a list')
            for line in account[field]: check_text(line, field)
        if not account['sourceRefs'] or len(set(account['sourceRefs'])) != len(account['sourceRefs']) or set(account['sourceRefs']) - source_ids:
            raise ValueError('Each account needs unique references to included sources')
        used.update(account['sourceRefs'])
        if not isinstance(account.get('artifacts', []), list): raise ValueError('Artifacts must be a list')
        for artifact in account.get('artifacts', []):
            keys(artifact, ['id', 'title', 'caption', 'file', 'embeddedId', 'mediaType', 'sha256', '_dataUrl'], 'Artifact')
            for field in ['id', 'title', 'caption']: check_text(artifact[field], field)
            aid = artifact['id']
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}', aid) or aid in artifact_ids: raise ValueError('Artifacts need unique safe IDs')
            artifact_ids.add(aid)
    used.update(sections.validate_timeline(data, check_text, keys))
    used.update(memory.validate(data, check_text, keys))
    if 'interview' in data:
        global _interview_renderer
        if _interview_renderer is None:
            _interview_renderer = load_helper('render_interview')
        _interview_renderer.validate_projection(data, data['interview'], sections.evidence_fingerprint(data))
    sections.validate_rehearsal(data, check_text, keys)
    guided_path.validate(data, check_text, keys)
    if data.get('journey', {}).get('coverage'):
        used.update(guided_path.validate_coverage(data['journey']['coverage'], source_ids, check_text, keys))
    for review in data.get('journey', {}).get('reviews', {}).values():
        used.update(review['sourceRefs'])
    for name in ['rounds', 'leads']:
        for row in data.get('journey', {}).get('investigation', {}).get(name, []):
            used.update(row['sourceRefs'])
    public_profile.validate(data, check_text, keys)
    if used != source_ids: raise ValueError('Remove unreferenced source records from the packet')
    # HTML loading temporarily attaches image bytes. They live outside the
    # canonical JSON and have their own image and complete-document bounds.
    canonical = dict(data, accounts=[dict(account, artifacts=[
        {k: v for k, v in artifact.items() if k != '_dataUrl'}
        for artifact in account.get('artifacts', [])]) if 'artifacts' in account else account
        for account in data['accounts']])
    if len(json.dumps(canonical, ensure_ascii=False).encode('utf-8')) > MAX_PACKET_BYTES:
        raise ValueError('Sheet exceeds 24 MiB')

class SheetReader(HTMLParser):
    def __init__(self): super().__init__(); self.capture = False; self.parts = []; self.images = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('id') == 'career-context-data': self.capture = True
        if tag == 'img' and attrs.get('id'): self.images[attrs['id']] = attrs.get('src', '')
    def handle_data(self, data):
        if self.capture: self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == 'script': self.capture = False

def load_packet(source):
    is_html = source.suffix.lower() in ['.html', '.htm']
    maximum = MAX_DOCUMENT_BYTES if is_html else MAX_PACKET_BYTES
    if source.stat().st_size > maximum:
        raise ValueError('HTML sheet exceeds 64 MiB' if is_html else 'Sheet exceeds 24 MiB')
    return parse_packet(source.read_text(encoding='utf-8'), is_html=is_html)


def parse_packet(raw, *, is_html=False):
    maximum = MAX_DOCUMENT_BYTES if is_html else MAX_PACKET_BYTES
    if len(raw.encode()) > maximum: raise ValueError('HTML sheet exceeds 64 MiB' if is_html else 'Sheet exceeds 24 MiB')
    if not is_html: return json.loads(raw)
    parser = SheetReader(); parser.feed(raw); data = json.loads(''.join(parser.parts))
    if len(json.dumps(data, ensure_ascii=False).encode('utf-8')) > MAX_PACKET_BYTES:
        raise ValueError('Sheet exceeds 24 MiB')
    for account in data['accounts']:
        for artifact in account.get('artifacts', []): artifact['_dataUrl'] = parser.images.get(artifact.get('embeddedId'), '')
    return data

def image_data(artifact, base):
    if 'file' in artifact:
        selected = Path(artifact['file'])
        path = (base / selected).resolve()
        if selected.is_absolute() or not path.is_relative_to(base.resolve()):
            raise ValueError('Select an image inside the input folder using a relative path')
        if path.stat().st_size > 2 * 1024 * 1024: raise ValueError('Image must be at most 2 MiB')
        mime = MIMES.get(path.suffix.lower()); raw = path.read_bytes()
    else:
        match = re.fullmatch(r'data:(image/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/=]+)', artifact.get('_dataUrl', ''))
        if not match: raise ValueError('The selected artifact has no embedded image or authoring file')
        mime = match[1]; raw = base64.b64decode(match[2], validate=True)
    if mime not in MIMES.values() or len(raw) > 2 * 1024 * 1024: raise ValueError('Image must be supported and at most 2 MiB')
    signatures = {'image/png': raw.startswith(b'\x89PNG\r\n\x1a\n'), 'image/jpeg': raw.startswith(b'\xff\xd8\xff'),
                  'image/gif': raw.startswith((b'GIF87a', b'GIF89a')), 'image/webp': raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'}
    if not signatures[mime]: raise ValueError('Image content does not match its declared format')
    if 'file' not in artifact and artifact.get('sha256') != hashlib.sha256(raw).hexdigest():
        raise ValueError('Embedded image does not match its saved checksum')
    return mime, raw


def publish_new(temporary, destination):
    # Windows rename is atomic and refuses an existing target. POSIX rename
    # replaces targets, so use an exclusive hard link there instead.
    if os.name == 'nt':
        os.rename(temporary, destination)
    else:
        os.link(temporary, destination)

def capability_text(capability):
    text = (f'{capability["name"]} ({capability["kind"]}): {capability["application"]}\n'
            f'Assistance: {capability["assistance"]}')
    if capability['limits']:
        text += '\nLimits: ' + ' '.join(capability['limits'])
    return text


def capability_index(accounts):
    groups = {}
    for account in accounts:
        for capability in account.get('capabilities', []):
            key = (capability['name'].casefold(), capability['kind'])
            group = groups.setdefault(key, {'name': capability['name'], 'kind': capability['kind'], 'uses': []})
            group['uses'].append((account, capability))
    if not groups: return ''
    sections = []
    for kind, label in [('practice', 'Skills & practices'), ('tool', 'Tools')]:
        entries = []
        for group in sorted(groups.values(), key=lambda g: g['name'].casefold()):
            if group['kind'] != kind: continue
            uses = ''.join('<div class="skill-use"><a href="#account-' + html.escape(a['id']) + '" data-show-capabilities="' + html.escape(a['id']) + '">' + html.escape(a['title']) + ' ↗</a><p>' + html.escape(c['application']) + '</p><p class="assistance">' + html.escape(c['assistance']) + '</p>' + ('<ul>' + ''.join('<li>' + html.escape(x) + '</li>' for x in c['limits']) + '</ul>' if c['limits'] else '') + '</div>' for a,c in group['uses'])
            entries.append('<details class="skill-entry"><summary><strong>' + html.escape(group['name']) + '</strong><span>' + str(len(group['uses'])) + ' work account' + ('s' if len(group['uses']) != 1 else '') + '</span><span aria-hidden="true">+</span></summary>' + uses + '</details>')
        if entries: sections.append('<section class="skill-group"><h3>' + label + '</h3><div>' + ''.join(entries) + '</div></section>')
    return '<section id="skills" class="document-view skills-view" aria-labelledby="skills-title"><div class="section-heading"><h2 id="skills-title">Skills &amp; tools</h2><span>' + str(len(groups)) + ' recorded</span></div>' + ''.join(sections) + '</section>'


def account_capabilities(account):
    entries = []
    for capability in account.get('capabilities', []):
        c = {k: html.escape(capability[k]) for k in ('name', 'kind', 'application', 'assistance')}
        limits = ''.join(f'<li>{html.escape(limit)}</li>' for limit in capability['limits'])
        entries.append(f'<li class="capability"><div class="capability-heading"><h4>{c["name"]}</h4>'
                       f'<span class="kind">{c["kind"].capitalize()}</span></div><p>{c["application"]}</p>'
                       f'<p class="assistance"><span>Assistance</span> {c["assistance"]}</p>'
                       + (f'<ul class="capability-limits">{limits}</ul>' if limits else '') + '</li>')
    if not entries:
        return ''
    return ('<details class="capability-details"><summary>Skills &amp; tools'
            '<span class="disclosure-mark" aria-hidden="true">+</span></summary><ul class="capability-list">'
            + ''.join(entries) + '</ul></details>')


def preserve_views(previous, incoming):
    missing = [key for key in ['timeline', 'interview', 'journey', 'publicProfile', 'memory'] if previous.get(key) and not incoming.get(key)]
    if {c['id'] for c in memory.claims(previous)} - {c['id'] for c in memory.claims(incoming)}:
        missing.append('memory claims (retain rejected or withdrawn interpretations)')
    for key in ['coverage', 'reviews', 'continuation', 'investigation']:
        if previous.get('journey', {}).get(key) and not incoming.get('journey', {}).get(key):
            missing.append('journey.' + key)
    if missing:
        raise ValueError('Update would remove ' + ', '.join(missing) + '. Retain the complete packet; use --allow-remove-views only for intentional removal.')


def render(source, destination, *, overwrite=True, allow_view_removal=False, guided=False):
    if source.suffix.lower() in {'.html', '.htm'} and re.search(r'<script[^>]+id=[\"\']career-draft-data[\"\']', source.read_text(encoding='utf-8')):
        raise ValueError('This file contains notebook edits. Use merge_notebook.py to reconcile them before rendering the complete document.')
    data = load_packet(source); validate(data); packet = copy.deepcopy(data)
    if overwrite and destination.exists() and not allow_view_removal:
        try:
            previous = load_packet(destination)
        except (ValueError, KeyError, TypeError):
            previous = None
        if isinstance(previous, dict): preserve_views(previous, packet)
    if guided and 'journey' not in packet:
        packet['journey'] = guided_path.initial_state(packet, sections.evidence_fingerprint(packet))
    if 'journey' in packet and 'publicProfile' not in packet:
        packet['publicProfile'] = public_profile.initial_state(packet, sections.evidence_fingerprint(packet))
    esc = html.escape
    def paragraphs(text): return ''.join(f'<p>{esc(p)}</p>' for p in text.split('\n\n') if p.strip())
    def bullets(items): return '<ul>' + ''.join(f'<li>{esc(i)}</li>' for i in items) + '</ul>' if items else ''
    accounts = []
    briefs = packet.get('presentation', {}).get('briefs', {})
    brief_accounts = briefs.get('accounts', {}) if briefs.get('contextSha256') == sections.evidence_fingerprint(packet) else {}
    for ordinal, account in enumerate(packet['accounts'], 1):
        pictures = []
        for artifact in account.get('artifacts', []):
            mime, raw = image_data(artifact, source.parent); artifact.pop('file', None); artifact.pop('_dataUrl', None)
            artifact.update(embeddedId='artifact-'+artifact['id'], mediaType=mime, sha256=hashlib.sha256(raw).hexdigest())
            url = f'data:{mime};base64,' + base64.b64encode(raw).decode()
            pictures.append(f'<figure><img id="{artifact["embeddedId"]}" src="{url}" alt="{esc(artifact["title"])}" loading="lazy"><figcaption>{esc(artifact["caption"])}</figcaption><button type="button" class="text-button artifact-expand" data-artifact="{artifact["embeddedId"]}" aria-haspopup="dialog">Enlarge image</button></figure>')
        fields = [('context', 'Context'), ('aim', 'Aim'), ('contribution', 'My contribution'), ('decisions', 'Decisions'), ('sharedCredit', 'Shared work'), ('outcome', 'Outcome')]
        details = '<div class="detail-grid">' + ''.join('<div><h4>' + label + '</h4>' + (bullets(account[key]) if isinstance(account[key], list) else paragraphs(account[key])) + '</div>' for key, label in fields if account[key]) + '</div>'
        questions = '<h4>Still to clarify</h4>' + bullets(account['questions']) if account['questions'] else ''
        refs = ' · '.join(f'<a href="#source-{esc(ref)}">{esc(next(s["label"] for s in packet["sources"] if s["id"]==ref))}</a>' for ref in account['sourceRefs'])
        limits = '<div class="limit" aria-label="Limits">' + bullets(account['limits']) + '</div>' if account['limits'] else ''
        review_link = f'<div class="account-review js-only" data-account-review="{account["id"]}"><a href="#path-review--{account["id"]}">Review this account</a></div>' if 'journey' in packet else ''
        practice_label = 'Practise this story' if account['id'] in {s['id'] for s in packet.get('interview', {}).get('stories', [])} else 'Prepare this story'
        review_link += f'<a class="account-practice" href="#prep-story-{account["id"]}">{practice_label} · optional →</a>'
        review_link = '<div class="account-actions">' + review_link + '</div>'
        brief = brief_accounts.get(account['id'])
        summary = '<div class="account-brief">' + bullets(brief) + '</div>' if brief else '<div class="account-summary">' + paragraphs(account['summary']) + '</div>'
        retained = '<div class="retained-account"><h4>Original account</h4>' + paragraphs(account['summary']) + '</div>' if brief else ''
        evidence_label = 'Full account &amp; evidence' if brief else 'Context &amp; evidence'
        accounts.append(f'''<article class="account{' has-brief' if brief else ''}" id="account-{account['id']}"><div class="account-ordinal" aria-hidden="true">{ordinal:02d}</div><div class="account-main"><div class="account-heading"><span class="period">{esc(account['period']) or 'Period not recorded'}</span><h3>{esc(account['title'])}</h3></div>{summary}{review_link}{'' if brief else ''.join(pictures) + limits}{account_capabilities(account)}<details class="context-details"><summary>{evidence_label} <span class="arrow" aria-hidden="true"><svg viewBox="0 0 20 20"><path d="m7 4 6 6-6 6"/></svg></span></summary>{retained}{details}{(''.join(pictures) + limits) if brief else ''}{questions}<p class="references">Sources: {refs}</p></details></div></article>''')
    account_html = dict(zip((a['id'] for a in packet['accounts']), accounts))
    account_index = {a['id']: f'<a href="#account-{a["id"]}"><span aria-hidden="true">{i:02d}</span>{esc(a["title"])}</a>' for i, a in enumerate(packet['accounts'], 1)}
    grouped_accounts, grouped_index = [], []
    for group in sections.work_groups(packet):
        label, ids = esc(group['title']), group['accountIds']
        scope = esc(' '.join(ids))
        content = ''.join(account_html[key] for key in ids)
        if group['kind'] == 'background':
            grouped_accounts.append(f'<details class="work-group work-background" data-work-group="{scope}"><summary>{label}</summary>{content}</details>')
        else:
            grouped_accounts.append(f'<section class="work-group" aria-label="{label}" data-work-group="{scope}"><p class="work-group-label">{label}</p>{content}</section>')
        grouped_index.append(f'<div class="work-index-group" data-work-group="{scope}"><p>{label}</p>{"".join(account_index[key] for key in ids)}</div>')
    sources = []
    for s in packet['sources']:
        location = f'<p class="source-meta">{esc(s["locator"])}</p>' if s.get('locator') else ''
        source_date = f'<p class="source-meta">Source date: {esc(s["date"])}</p>' if s.get('date') else ''
        related = ''.join(f'<a href="#account-{esc(a["id"])}">{esc(a["title"])}</a>' for a in packet['accounts'] if s['id'] in a['sourceRefs'])
        related += ''.join(f'<a href="#quarter-{esc(p["id"])}">{esc(p["period"])}</a>' for p in packet.get('timeline', []) if s['id'] in p['sourceRefs'])
        related = f'<nav class="source-used-by" aria-label="Used in">{related}</nav>' if related else ''
        sources.append(f'<details class="source" id="source-{s["id"]}"><summary><span>{esc(s["label"])}</span><small>{esc(s["kind"].replace("_", " "))}</small><span class="arrow" aria-hidden="true"><svg viewBox="0 0 20 20"><path d="m7 4 6 6-6 6"/></svg></span></summary><div class="source-content">{source_date}{paragraphs(s["content"])}<p class="scope">{esc(s["scope"])}</p>{location}</div>{related}</details>')
    profile = packet.get('profile', {})
    profile_html = ''.join('<div><dt>' + label + '</dt><dd>' + esc(' · '.join(profile[field])) + '</dd></div>'
                           for field, label in [('disciplines', 'Work'), ('targetRoles', 'Exploring'), ('emphasis', 'Focus')] if profile.get(field))
    coverage = ''.join('<tr>' + ''.join('<td>' + esc(location[field].replace('_', ' ') if field == 'status' else location[field]) + '</td>'
                                      for field in ['platform', 'location', 'status', 'scope', 'nextStep']) + '</tr>' for location in packet.get('collection', []))
    review_basis = memory.review_basis(packet)
    if 'journey' in packet and packet['journey']['contextSha256'] == sections.evidence_fingerprint(packet):
        # Legacy current packets can safely acquire a baseline. A stale legacy
        # packet has no account-level baseline and must reopen once, conservatively.
        packet['journey'].setdefault('reviewBasis', review_basis)
    values = {
        'RESUME': json.dumps({'schema': 'career-resume/v1', 'contextSha256': sections.evidence_fingerprint(packet),
                             'journeyUpdatedAt': packet.get('journey', {}).get('updatedAt', 0),
                             'instructions': (SKILL / 'assets/continuation.txt').read_text(encoding='utf-8')}, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026'),
        'PATH': guided_path.render(packet, sections.evidence_fingerprint(packet), review_basis),
        'PATHNAV': '<a href="#path" data-view="path">Develop context</a>' if 'journey' in packet else '',
        'HOME': '#context',
        'CONTEXTHOME': '#context',
        'CONTEXTOVERVIEW': sections.context_overview(packet),
        'CONTEXTACTION': '<a class="context-add" href="#path" data-add-context>Add context <span aria-hidden="true">+</span></a>' if 'journey' in packet else '',
        'CONTEXTCSS': (SKILL / 'assets/context.css').read_text(encoding='utf-8'),
        'PATHCSS': (SKILL / 'assets/path.css').read_text(encoding='utf-8') if 'journey' in packet or 'publicProfile' in packet else '',
        'PATHSCRIPT': '\n'.join((SKILL / ('assets/' + name)).read_text(encoding='utf-8') for name in (['continuation.js', 'coverage.js', 'path.js'] if 'journey' in packet else ['continuation.js'])),
        'PUBLIC': public_profile.render(packet, sections.evidence_fingerprint(packet)),
        'PUBLICNAV': '<a href="#profile" data-view="profile">Public profile</a>' if 'publicProfile' in packet else '',
        'PUBLICCSS': (SKILL / 'assets/public-profile.css').read_text(encoding='utf-8') if 'publicProfile' in packet else '',
        'PUBLICSCRIPT': (SKILL / 'assets/public-profile.js').read_text(encoding='utf-8') if 'publicProfile' in packet else '',
        'SECTIONSCSS': (SKILL / 'assets/sections.css').read_text(encoding='utf-8') + '\n' + (SKILL / 'assets/explore.css').read_text(encoding='utf-8'),
        'SECTIONSSCRIPT': (SKILL / 'assets/sections.js').read_text(encoding='utf-8') + '\n' + (SKILL / 'assets/explore.js').read_text(encoding='utf-8'),
        'TIMELINE': sections.timeline_html(packet),
        'INTERVIEW': sections.interview_html(packet),
        'TIMELINECOUNT': f'{len(packet.get("timeline", []))} periods' if packet.get('timeline') else '',
        'EVIDENCE': sections.evidence_fingerprint(packet),
        'PREPSTATE': 'Draft for practice' if packet.get('interview') else '',
        'HEADLINE': esc(packet.get('presentation', {}).get('headline') or 'Work, in context.'),
        'FILES': '<nav class="related-files" aria-label="Local files">' + ''.join(f'<a href="{esc(item["path"])}">{esc(item["label"])}</a>' for item in packet.get('presentation', {}).get('files', [])) + '</nav>',
        'OPTIONS': ''.join(f'<option value="{a["id"]}">{esc(a["title"])}</option>' for a in packet['accounts']),
        'PROFILE': '<dl class="profile">' + profile_html + '</dl>' if profile_html else '',
        'CAPABILITIES': capability_index(packet['accounts']),
        'SKILLSLINK': '<a href="#skills" data-view="skills">Skills</a>' if any(a.get('capabilities') for a in packet['accounts']) else '',
        'SKILLOPTIONS': ''.join(f'<option value="{esc(name, quote=True)}">{esc(name)}</option>' for name in sorted({c['name'] for a in packet['accounts'] for c in a.get('capabilities', [])}, key=str.casefold)),
        'SKILLFILTERHIDDEN': '' if any(a.get('capabilities') for a in packet['accounts']) else ' hidden',
        'COVERAGE': '<details class="coverage"><summary>Source coverage</summary><div class="table-scroll"><table><thead><tr><th>Platform</th><th>Location</th><th>State</th><th>Read scope</th><th>Next step</th></tr></thead><tbody>' + coverage + '</tbody></table></div></details>' if coverage else '',
        'TITLE': esc(packet['person']['name'] + ' — Career context'), 'NAME': esc(packet['person']['name']),
        'OVERVIEW': paragraphs(packet['person']['overview']), 'BACKGROUND': ('<section class="background" aria-labelledby="background-title"><h2 id="background-title">Broader background</h2>' + bullets(packet['person']['background']) + '</section>') if packet['person'].get('background') else '',
        'DATE': esc(packet['updatedAt']), 'STATUS': 'Draft for review' if packet['reviewStatus']=='draft' else 'Reviewed by the person',
        'COUNT': f'{len(packet["accounts"])} work account' + ('' if len(packet['accounts']) == 1 else 's'),
        'DEMO': '<p class="demo-notice"><strong>Fictional example</strong><span>' + esc(packet['person']['name']) + ' is a sample person. The dates, work and sources are invented.</span></p>' if packet.get('synthetic') else '',
        'ACCOUNTS': ''.join(grouped_accounts or accounts) or '<p class="empty">No work accounts recorded yet. Start with one piece of work: what happened, what you did and what remains uncertain.</p>',
        'INDEX': ''.join(grouped_index) if grouped_index else ''.join(account_index.values()),
        'SOURCES': ''.join(sources) or '<p>No sources included yet.</p>',
        'DATA': json.dumps(packet, ensure_ascii=True).replace('<', '\\u003c').replace('&', '\\u0026'),
    }
    validate(packet)  # Embedded-image metadata must also fit the canonical packet.
    template = (SKILL / 'assets/sheet.html').read_text(encoding='utf-8')
    output = re.sub(r'@@([A-Z]+)@@', lambda m: values[m[1]], template)
    if len(output.encode('utf-8')) > MAX_DOCUMENT_BYTES:
        raise ValueError('HTML sheet exceeds 64 MiB')
    if destination.is_symlink(): raise ValueError('Output must not be a symbolic link')
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix='.career-context-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream: stream.write(output.encode('utf-8'))
        if overwrite:
            os.replace(temporary, destination)
        else:
            publish_new(temporary, destination)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return {'path': str(destination), 'accounts': len(packet['accounts']), 'sources': len(packet['sources']), 'bytes': len(output.encode()), 'sha256': hashlib.sha256(output.encode()).hexdigest()}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Selected context JSON or an existing HTML sheet")
    parser.add_argument("output", type=Path, nargs='?', help="HTML destination")
    parser.add_argument("--inspect", action="store_true", help="Read the canonical evidence fingerprint for embedded interview preparation")
    parser.add_argument("--force", action="store_true", help="Replace an existing output")
    parser.add_argument("--guided", action="store_true", help="Add a guided path with a retained starting draft and private review notes")
    parser.add_argument("--allow-remove-views", action="store_true", help="Explicitly allow removing an existing timeline or interview view")
    args = parser.parse_args(argv)
    try:
        source = args.input.expanduser().resolve()
        if args.inspect:
            packet = load_packet(source)
            evidence = {k: v for k, v in packet.items() if k not in ['interview', 'rehearsal']}
            validate(evidence)
            basis = sections.evidence_fingerprint(packet)
            print(json.dumps({'contextSha256': basis, 'interviewCurrent': packet.get('interview', {}).get('contextSha256') == basis, 'context': packet}))
            return
        if args.output is None:
            raise ValueError('Choose an HTML output path')
        destination = args.output.expanduser().absolute()
        if destination.suffix.lower() not in {".html", ".htm"}:
            raise ValueError("Choose an output ending in .html or .htm.")
        if destination.is_symlink():
            raise ValueError("Output must not be a symbolic link.")
        if destination.exists() and not args.force:
            raise ValueError("Output already exists; use --force to replace it.")
        if not destination.parent.is_dir():
            raise ValueError("Create the output folder first.")
        result = render(source, destination, overwrite=args.force, allow_view_removal=args.allow_remove_views, guided=args.guided)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"Could not create the sheet: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
