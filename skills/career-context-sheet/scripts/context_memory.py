"""Private, portable assertions and exact anchors. No inference or source access."""
import hashlib
import json
import re

KINDS = {'fact', 'self_report', 'interpretation', 'hypothesis', 'correction'}
STATUSES = {'candidate', 'supported', 'qualified', 'disputed', 'rejected', 'withdrawn'}
RELATIONS = {'supports', 'qualifies', 'contradicts', 'supersedes'}
ACTION_STATES = {'offered', 'requested', 'planned', 'in_progress', 'completed', 'reported', 'unknown'}
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':')).encode()).hexdigest()


def source_hash(source):
    return hashlib.sha256(source['content'].encode('utf-8')).hexdigest()


def claims(packet):
    return packet.get('memory', {}).get('claims', [])


def anchor(source, start, end):
    """Offsets are Unicode code points into the retained source content."""
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source['content']):
        raise ValueError('Anchor offsets must select a nonempty span of retained source text')
    return {'sourceId': source['id'], 'sourceSha256': source_hash(source),
            'start': start, 'end': end, 'quote': source['content'][start:end]}


def validate(packet, check_text, keys):
    memory = packet.get('memory')
    if memory is None:
        return set()
    keys(memory, ['schema', 'claims'], 'Memory')
    if memory.get('schema') != 'career-memory/v1':
        raise ValueError('Unsupported memory schema')
    rows = memory.get('claims')
    if not isinstance(rows, list) or len(rows) > 4096 or any(not isinstance(c, dict) for c in rows):
        raise ValueError('Memory claims must be a bounded list of objects')
    ids = [c.get('id') for c in rows]
    if any(not isinstance(i, str) or not ID.fullmatch(i) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Memory claims need unique safe IDs')
    accounts = {a['id'] for a in packet['accounts']}
    sources = {s['id']: s for s in packet['sources']}
    used = set()
    for claim in rows:
        keys(claim, ['id', 'statement', 'kind', 'status', 'accountIds', 'evidence',
                     'counterEvidence', 'relations', 'aliases', 'rationale', 'nextQuestion', 'attributions'], 'Memory claim')
        check_text(claim.get('statement'), 'Claim statement', 6000)
        if not claim['statement'].strip() or claim.get('kind') not in KINDS or claim.get('status') not in STATUSES:
            raise ValueError('A claim needs a statement, kind and support state')
        refs = claim.get('accountIds')
        if (not isinstance(refs, list) or any(not isinstance(i, str) for i in refs)
                or len(set(refs)) != len(refs) or set(refs) - accounts):
            raise ValueError('Claim account references must resolve without duplicates')
        for field in ['rationale', 'nextQuestion']:
            check_text(claim.get(field, ''), 'Claim ' + field, 6000)
        if claim['kind'] in {'hypothesis', 'interpretation', 'correction'} or claim['status'] in {'disputed', 'rejected', 'withdrawn'}:
            if not claim.get('rationale', '').strip():
                raise ValueError('Interpretations, corrections and rejected/disputed claims need a rationale')
        if claim['kind'] == 'hypothesis' and claim['status'] in {'supported', 'qualified'}:
            raise ValueError('A hypothesis remains tentative; explicitly reclassify a supported interpretation')
        attributions = claim.get('attributions', [])
        if not isinstance(attributions, list) or len(attributions) > 100:
            raise ValueError('Claim attributions must be a bounded list')
        evidence_groups = [claim.get('evidence'), claim.get('counterEvidence', [])]
        for attribution in attributions:
            keys(attribution, ['actor', 'action', 'state', 'evidence'], 'Claim attribution')
            for field in ['actor', 'action']:
                check_text(attribution.get(field), 'Attribution ' + field, 3000)
                if not attribution[field].strip():
                    raise ValueError('Attributions need an actor and action')
            if attribution.get('state') not in ACTION_STATES or not attribution.get('evidence'):
                raise ValueError('Attributions need an action state and exact evidence')
            evidence_groups.append(attribution['evidence'])
        for spans in evidence_groups:
            if not isinstance(spans, list) or len(spans) > 100:
                raise ValueError('Claim evidence must be a bounded list')
            for span in spans:
                keys(span, ['sourceId', 'sourceSha256', 'start', 'end', 'quote'], 'Evidence anchor')
                source = sources.get(span.get('sourceId')) if isinstance(span.get('sourceId'), str) else None
                if source is None:
                    raise ValueError('Evidence anchors must reference retained sources')
                expected = anchor(source, span.get('start'), span.get('end'))
                if span != expected:
                    raise ValueError('Evidence anchor is stale or does not match the exact source span')
                used.add(source['id'])
        if claim['status'] in {'supported', 'qualified'} and not claim['evidence']:
            raise ValueError('Supported claims need exact retained evidence')
        aliases = claim.get('aliases', [])
        if not isinstance(aliases, list) or len(aliases) > 30:
            raise ValueError('Claim aliases must be a bounded list')
        for value in aliases:
            check_text(value, 'Claim alias', 200)
            if not value.strip():
                raise ValueError('Claim aliases must not be blank')
        relations = claim.get('relations', [])
        if not isinstance(relations, list) or len(relations) > 100:
            raise ValueError('Claim relations must be a bounded list')
        seen = set()
        for relation in relations:
            keys(relation, ['claimId', 'type'], 'Claim relation')
            target, kind = relation.get('claimId'), relation.get('type')
            if not isinstance(target, str) or not isinstance(kind, str):
                raise ValueError('Invalid claim relation')
            if target not in ids or target == claim['id'] or kind not in RELATIONS or (target, kind) in seen:
                raise ValueError('Claim relations must resolve without self-links or duplicates')
            seen.add((target, kind))
    return used


def connected_claims(packet, selected):
    """Include incoming corrections as well as outgoing links; cycles terminate."""
    selected = set(selected)
    adjacent = {c['id']: set() for c in claims(packet)}
    for c in claims(packet):
        for r in c.get('relations', []):
            adjacent[c['id']].add(r['claimId'])
            adjacent[r['claimId']].add(c['id'])
    pending = list(selected)
    while pending:
        for key in adjacent.get(pending.pop(), ()):
            if key not in selected:
                selected.add(key)
                pending.append(key)
    return [c for c in claims(packet) if c['id'] in selected]


def evidence(claim):
    return [e for field in ['evidence', 'counterEvidence'] for e in claim.get(field, [])] + [
        e for attribution in claim.get('attributions', []) for e in attribution['evidence']]


def review_basis(packet):
    """Account dependencies exclude global prose and retrieval-only aliases."""
    sources = {s['id']: digest(s) for s in packet['sources']}
    result = {}
    for account in packet['accounts']:
        related = connected_claims(packet, [c['id'] for c in claims(packet) if account['id'] in c['accountIds']])
        refs = set(account['sourceRefs'])
        for c in related:
            refs.update(e['sourceId'] for e in evidence(c))
        # Image transport is not evidence. Captions and selected image hashes are.
        content = {k: v for k, v in account.items() if k != 'artifacts'}
        if account.get('artifacts'):
            content['artifacts'] = [{k: v for k, v in a.items() if k not in {'file', '_dataUrl', 'embeddedId'}}
                                    for a in account['artifacts']]
        result[account['id']] = digest({'account': content,
            'claims': [{k: v for k, v in c.items() if k != 'aliases'} for c in related],
            'sources': {key: sources[key] for key in sorted(refs)}})
    return {'accounts': result, 'sources': sources}
