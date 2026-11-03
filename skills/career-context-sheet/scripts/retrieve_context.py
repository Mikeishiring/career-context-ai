"""Find lexical or local semantic reading leads; no network, writes or fit scores."""
import argparse
import importlib.util
import json
import re
import sqlite3
from pathlib import Path


_spec = importlib.util.spec_from_file_location(
    'career_retrieval_renderer', Path(__file__).with_name('render_context.py'))
renderer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(renderer)
LAYERS = ('accounts', 'timeline', 'sources', 'claims')
FIELDS = {
    'accounts': (*renderer.TEXT_FIELDS, 'decisions', 'limits', 'questions', 'tags', 'capabilities'),
    'timeline': ('period', 'title', 'focus', 'actions', 'tension', 'approach', 'questions'),
    'sources': ('label', 'date', 'content', 'scope'),
    'claims': ('statement', 'aliases', 'rationale', 'nextQuestion'),
}


def records(packet, layer):
    return renderer.memory.claims(packet) if layer == 'claims' else packet.get(layer, [])


def text_fields(value, prefix):
    """Preserve field locations; never search transport bytes, IDs or file paths."""
    if isinstance(value, str):
        yield prefix, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from text_fields(item, f'{prefix}[{index}]')
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from text_fields(item, f'{prefix}.{key}')


def links(packet, layer, record):
    key = record['id']
    claims = renderer.memory.claims(packet)
    if layer == 'claims':
        return {'accountIds': record['accountIds'],
                'sourceRefs': list(dict.fromkeys(e['sourceId'] for e in renderer.memory.evidence(record))),
                'claimIds': [c['id'] for c in renderer.memory.connected_claims(packet, [key]) if c['id'] != key]}
    if layer == 'sources':
        return {
            'accountIds': [a['id'] for a in packet['accounts'] if key in a['sourceRefs']],
            'timelineIds': [p['id'] for p in packet.get('timeline', []) if key in p['sourceRefs']],
            'claimIds': [c['id'] for c in claims if any(e['sourceId'] == key for e in renderer.memory.evidence(c))],
        }
    return {
        'sourceRefs': record['sourceRefs'],
        'accountIds': record.get('accountIds', []),
        'timelineIds': [p['id'] for p in packet.get('timeline', [])
                        if layer == 'accounts' and key in p['accountIds']],
        'claimIds': [c['id'] for c in claims if layer == 'accounts' and key in c['accountIds']],
    }


def snippet(value, match, radius=130):
    start, end = max(0, match.start() - radius), match.end() + radius
    return ('…' if start else '') + value[start:end] + ('…' if end < len(value) else '')


def searchable_fields(record, layer):
    """One allowlist for lexical and semantic input; transport and locators stay out."""
    fields = [(field, value) for key in FIELDS[layer]
              for field, value in text_fields(record.get(key), key)]
    if layer == 'claims':
        fields.extend((f'attributions[{i}].{key}', item[key])
                      for i, item in enumerate(record.get('attributions', [])) for key in ['actor', 'action', 'state'])
    return fields


def lexical_hits(packet, layer, queries, mode):
    patterns = [(query, [re.compile(re.escape(term) if mode == 'literal' else
                r'(?<!\w)' + re.escape(term) + r'(?!\w)', re.IGNORECASE)
                for term in ([query] if mode == 'literal' else list(dict.fromkeys(query.split())))]) for query in queries]
    hits = []
    for record in records(packet, layer):
        fields = searchable_fields(record, layer)
        matches, score = [], 0
        for query, terms in patterns:
            found, query_score = [], 0
            for pattern in terms:
                candidates = [(4 if field.split('[')[0] in {'title', 'label', 'aliases'} else 1,
                               field, value, pattern.search(value)) for field, value in fields]
                candidate = max((c for c in candidates if c[3]), key=lambda c: c[0], default=None)
                if candidate:
                    weight, field, value, match = candidate
                    found.append({'query': query, 'field': field, 'snippet': snippet(value, match)} | match_context(record, field))
                    query_score += weight
            if len(found) == len(terms):
                matches.extend(found)
                score += query_score
        if matches:
            hits.append(hit_record(packet, layer, record) | {'matches': matches[:6], 'rankScore': score})
    return sorted(hits, key=lambda hit: -hit['rankScore'])


def hit_record(packet, layer, record):
    result = {'id': record['id'], 'label': record.get('title', record.get('label', record.get('statement', '')[:200])),
              'kind': record.get('kind'), 'status': record.get('status'), 'links': links(packet, layer, record)}
    if layer == 'claims':
        result['statement'] = record['statement']  # Keep qualifications outside the matched fragment.
        if record.get('rationale'):
            result['rationale'] = record['rationale']
    return result


def match_context(record, field):
    match = re.fullmatch(r'attributions\[(\d+)\]\.(?:actor|action|state)', field)
    return {'attribution': record['attributions'][int(match[1])]} if match else {}


def semantic_fields(record, layer):
    # Generic scope labels, dates and isolated actor names are poor semantic
    # candidates. They remain available to lexical search and full-record reads.
    for field, text in searchable_fields(record, layer):
        root = field.split('[')[0]
        if layer == 'sources' and field != 'content':
            continue
        if root in {'period', 'date', 'tags', 'capabilities', 'aliases'}:
            continue
        if root == 'attributions' and not field.endswith('.action'):
            continue
        yield field, text


def fuse(lexical, semantic):
    """Reciprocal rank fusion; incomparable score scales never get added."""
    combined = {}
    for channel, rows in [('lexical', lexical), ('semantic', semantic)]:
        for rank, row in enumerate(rows, 1):
            key = row['id']
            if key not in combined:
                combined[key] = dict(row, rankScore=0, matches=[], retrieval=[])
            hit = combined[key]
            hit['rankScore'] += 1 / (60 + rank)
            hit[channel + 'Score'] = row['rankScore']
            hit['retrieval'].append(channel)
            hit['matches'].extend(row['matches'])
    return sorted(combined.values(), key=lambda hit: -hit['rankScore'])


def search(packet, queries, *, layers=LAYERS, limit=8, offset=0, mode='terms', encoder=None, min_similarity=0.5):
    queries = list(dict.fromkeys(q.strip() for q in queries))
    maximum = 500 if mode == 'literal' else 200
    if not queries or any(not q or len(q) > maximum for q in queries) or len(queries) > 12:
        raise ValueError(f'Supply 1–12 nonblank queries, each at most {maximum} characters.')
    if not 1 <= limit <= 50 or offset < 0:
        raise ValueError('Limit must be 1–50 and offset must be nonnegative.')
    if not layers or set(layers) - set(LAYERS):
        raise ValueError('Unknown search layer.')
    if mode not in {'terms', 'literal', 'semantic', 'hybrid'}:
        raise ValueError('Search mode must be terms, literal, semantic or hybrid')
    meaning = mode in {'semantic', 'hybrid'}
    if meaning and encoder is None:
        raise ValueError('Semantic search requires an explicit local model; no lexical fallback was substituted.')
    if not meaning and encoder is not None:
        raise ValueError('A semantic model requires semantic or hybrid mode.')
    result = {'queries': queries, 'method': mode + '; OR across queries; ranked reading leads, not truth, support or fit scores',
              'contextSha256': renderer.sections.evidence_fingerprint(packet),
              'memorySha256': renderer.memory.digest(packet.get('memory', {})), 'layers': {}}
    if meaning:
        # Validate even for API callers, before any source text reaches the encoder.
        renderer.validate(packet)
        semantic = renderer.load_helper('semantic_context')
        fields = ((layer, record['id'], field, text) for layer in dict.fromkeys(layers)
                  for record in records(packet, layer) for field, text in semantic_fields(record, layer))
        matches, count = semantic.rank(queries, fields, encoder, min_similarity)
        result['semantic'] = dict(encoder.metadata, chunksExamined=count, minSimilarity=min_similarity,
                                  ranking='cosine similarity' if mode == 'semantic' else 'reciprocal rank fusion; k=60',
                                  retention='in-memory vectors only; no index file or source writes')
    for layer in layers:
        lexical = lexical_hits(packet, layer, queries, 'literal' if mode == 'literal' else 'terms') if mode != 'semantic' else []
        if meaning:
            rows = []
            for record in records(packet, layer):
                match = matches.get((layer, record['id']))
                if match is None:
                    continue
                match = dict(match, method='semantic', snippet=match['quote']) | match_context(record, match['field'])
                if layer == 'sources' and match['field'] == 'content':
                    match['evidenceAnchor'] = renderer.memory.anchor(record, match['start'], match['end'])
                rows.append(hit_record(packet, layer, record) | {
                    'matches': [match], 'rankScore': match['similarity'], 'retrieval': ['semantic']})
            rows.sort(key=lambda hit: -hit['rankScore'])
            hits = fuse(lexical, rows) if mode == 'hybrid' else rows
        else:
            hits = lexical
        page = hits[offset:offset + limit]
        result['layers'][layer] = {'recordsSearched': len(records(packet, layer)),
                                  'totalMatches': len(hits), 'offset': offset,
                                  'nextOffset': offset + len(page) if offset + len(page) < len(hits) else None,
                                  'hits': page}
    return result


def read_record(packet, selector):
    layer, separator, key = selector.partition(':')
    if not separator or layer not in LAYERS:
        raise ValueError('Use accounts:ID, timeline:ID, sources:ID or claims:ID.')
    record = next((r for r in records(packet, layer) if r['id'] == key), None)
    if record is None:
        raise ValueError('Record not found in this packet.')
    # Work samples stay in the sheet. Avoid dumping embedded image bytes.
    result = {'layer': layer, 'record': {k: v for k, v in record.items() if k != 'artifacts'},
              'links': links(packet, layer, record)}
    if layer == 'sources':
        result['sourceSha256'] = renderer.memory.source_hash(record)
    return result


def index(packet, *, layers=LAYERS, limit=8, offset=0):
    if not 1 <= limit <= 50 or offset < 0 or not layers or set(layers) - set(LAYERS):
        raise ValueError('Invalid index bounds or layers')
    result = {}
    for layer in layers:
        rows = records(packet, layer)
        page = [{k: row[k] for k in ['id', 'title', 'label', 'period', 'date', 'kind', 'status', 'aliases'] if k in row}
                | {'summary': row.get('summary', row.get('statement', ''))[:240], 'links': links(packet, layer, row)}
                for row in rows[offset:offset + limit]]
        result[layer] = {'total': len(rows), 'records': page,
                         'nextOffset': offset + len(page) if offset + len(page) < len(rows) else None}
    return {'layers': result, 'contextSha256': renderer.sections.evidence_fingerprint(packet),
            'memorySha256': renderer.memory.digest(packet.get('memory', {}))}


def expand(packet, selector, *, limit=8, offset=0):
    if not 1 <= limit <= 50 or offset < 0:
        raise ValueError('Invalid expansion bounds')
    root = read_record(packet, selector)
    selected = {layer: set() for layer in LAYERS}
    layer, key = selector.split(':', 1)
    selected[layer].add(key)
    for field, target in [('accountIds', 'accounts'), ('sourceRefs', 'sources'), ('timelineIds', 'timeline'), ('claimIds', 'claims')]:
        selected[target].update(root['links'].get(field, []))
    related_claims = renderer.memory.connected_claims(packet, selected['claims'])
    for claim in related_claims:
        selected['claims'].add(claim['id'])
        selected['accounts'].update(claim['accountIds'])
        selected['sources'].update(e['sourceId'] for e in renderer.memory.evidence(claim))
    # Keep broader linked accounts distinct from proof for the selected claim.
    root['related'] = {}
    for layer in LAYERS:
        rows = [r for r in records(packet, layer) if r['id'] in selected[layer]]
        page = rows[offset:offset + limit]
        root['related'][layer] = {'total': len(rows), 'records': [read_record(packet, layer + ':' + r['id']) for r in page],
                                  'nextOffset': offset + len(page) if offset + len(page) < len(rows) else None}
    return root


def load_input(source, revision=None):
    if source.suffix.lower() in {'.sqlite', '.sqlite3', '.db'}:
        return renderer.load_helper('archive_context').load_snapshot(source, revision)
    if revision is not None:
        raise ValueError('--revision requires a SQLite archive')
    packet = renderer.load_packet(source)
    renderer.validate(packet)
    return packet


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Career context JSON, saved HTML or read-only SQLite archive')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--query', action='append', help='Search terms (or a phrase with --mode literal); repeat for alternatives')
    action.add_argument('--read', help='Read a full record by layer:ID')
    action.add_argument('--index', action='store_true', help='Browse a compact, paginated record index')
    action.add_argument('--anchor', help='Source ID for an exact evidence anchor')
    parser.add_argument('--start', type=int)
    parser.add_argument('--end', type=int)
    parser.add_argument('--expand', action='store_true', help='Include linked evidence, corrections and interpretations for --read')
    parser.add_argument('--revision', help='Read a specific archived revision; default is current')
    parser.add_argument('--mode', choices=['terms', 'literal', 'semantic', 'hybrid'], default='terms')
    parser.add_argument('--model-dir', type=Path, help='Explicit prepared local model directory for semantic/hybrid search')
    parser.add_argument('--min-similarity', type=float, help='Semantic cosine cutoff, 0–1 (default 0.5); not a confidence threshold')
    parser.add_argument('--layer', action='append', choices=LAYERS)
    parser.add_argument('--limit', type=int, default=8, help='Matches per layer, 1–50')
    parser.add_argument('--offset', type=int, default=0, help='Skip this many matches in each selected layer')
    args = parser.parse_args(argv)
    try:
        semantic_mode = args.mode in {'semantic', 'hybrid'}
        if semantic_mode and (not args.query or args.model_dir is None):
            raise ValueError('Semantic/hybrid mode requires --query and --model-dir.')
        if not semantic_mode and (args.model_dir is not None or args.min_similarity is not None):
            raise ValueError('--model-dir and --min-similarity require semantic or hybrid mode.')
        packet = load_input(args.input, args.revision)
        if args.expand and not args.read:
            raise ValueError('--expand requires --read')
        if not args.anchor and (args.start is not None or args.end is not None):
            raise ValueError('--start and --end require --anchor')
        if args.anchor:
            result = renderer.memory.anchor(read_record(packet, 'sources:' + args.anchor)['record'], args.start, args.end)
        elif args.read:
            result = expand(packet, args.read, limit=args.limit, offset=args.offset) if args.expand else read_record(packet, args.read)
        elif args.index:
            result = index(packet, layers=args.layer or LAYERS, limit=args.limit, offset=args.offset)
        else:
            encoder = renderer.load_helper('semantic_context').LocalEncoder(args.model_dir) if semantic_mode else None
            result = search(packet, args.query, layers=args.layer or LAYERS, limit=args.limit, offset=args.offset, mode=args.mode,
                            encoder=encoder, min_similarity=0.5 if args.min_similarity is None else args.min_similarity)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(2, f'Could not read context: {error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
