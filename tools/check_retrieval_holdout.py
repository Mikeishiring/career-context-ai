"""Evaluate frozen independent queries; report misses without tuning or hiding them."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import patch

from check_career_workflow import ROOT, load_fixture, packet_from_fixture, retrieval, renderer

HOLDOUT = ROOT / 'tests/fixtures/retrieval-holdout.json'


def evaluate(model_dir, output):
    output = Path(output).resolve()
    if output.is_relative_to(ROOT.resolve()):
        raise ValueError('Save the evaluation outside the checkout.')
    holdout = json.loads(HOLDOUT.read_text(encoding='utf-8'))
    packet = packet_from_fixture(load_fixture())
    source_ids = {s['id'] for s in packet['sources']}
    claim_ids = {c['id'] for c in packet['memory']['claims']}
    for case in holdout['queries']:
        if not set(case['requiredSources']) <= source_ids or not set(case['relevantClaims']) <= claim_ids:
            raise ValueError('Holdout references absent evidence; review fixture drift before evaluation.')
    original = json.dumps(packet, sort_keys=True)
    semantic = renderer.load_helper('semantic_context')
    rows = []
    with patch.object(socket, 'socket', side_effect=AssertionError('Evaluation network forbidden')):
        encoder = semantic.LocalEncoder(model_dir)
        for case in holdout['queries']:
            result = retrieval.search(packet, [case['query']], layers=['sources', 'claims'], limit=5, mode='hybrid', encoder=encoder)
            sources = {h['id'] for h in result['layers']['sources']['hits']}
            claims = result['layers']['claims']['hits']
            expanded_sources = set(sources)
            truncated = []
            # Fixed budget: expand the first three claim leads, at most eight sources each.
            for hit in claims[:3]:
                expansion = retrieval.expand(packet, 'claims:' + hit['id'], limit=8)
                linked = expansion['related']['sources']
                expanded_sources.update(r['record']['id'] for r in linked['records'])
                if linked['nextOffset'] is not None:
                    truncated.append(hit['id'])
            required = set(case['requiredSources'])
            row = dict(case, sourceHits=[h['id'] for h in result['layers']['sources']['hits']],
                       claimHits=[{'id': h['id'], 'status': h.get('status')} for h in claims],
                       anySourceAtFive=bool(required & sources), allSourcesAtFive=bool(required) and required <= sources,
                       allSourcesAfterExpansion=bool(required) and required <= expanded_sources,
                       sourcesReadAfterExpansion=len(expanded_sources), paginatedExpansions=truncated,
                       missingSourcesAfterExpansion=sorted(required - expanded_sources))
            rows.append(row)
            print(json.dumps({k: row[k] for k in ['id', 'answerable', 'allSourcesAtFive', 'allSourcesAfterExpansion', 'missingSourcesAfterExpansion']}), flush=True)
    if json.dumps(packet, sort_keys=True) != original:
        raise AssertionError('Retrieval changed the supplied packet.')
    answerable = [r for r in rows if r['answerable']]
    report = {'synthetic': True, 'method': holdout['method'], 'holdoutSha256': hashlib.sha256(HOLDOUT.read_bytes()).hexdigest(),
              'contextSha256': renderer.sections.evidence_fingerprint(packet), 'model': encoder.metadata,
              'budget': 'Five source and five claim leads; first three claims expanded to at most eight sources each. Unique source counts reported per query.',
              'answerGenerationTested': False, 'unknownQuestions': len(rows) - len(answerable),
              'summary': {'answerableQueries': len(answerable), 'anyRequiredSourceAtFive': sum(r['anySourceAtFive'] for r in answerable),
                          'allRequiredSourcesAtFive': sum(r['allSourcesAtFive'] for r in answerable),
                          'allRequiredSourcesAfterExpansion': sum(r['allSourcesAfterExpansion'] for r in answerable)},
              'packetUnchanged': True, 'queries': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report['summary']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.model_dir, args.output)))
