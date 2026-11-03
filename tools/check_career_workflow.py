"""Replay a fixed fictional career through retrieval, browser review and archive updates."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/realistic-career-history.json'
spec = importlib.util.spec_from_file_location('workflow_retrieval', ROOT / 'skills/career-context-sheet/scripts/retrieve_context.py')
retrieval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retrieval)
renderer = retrieval.renderer
archive = renderer.load_helper('archive_context')


def load_fixture():
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    if fixture.get('synthetic') is not True:
        raise ValueError('This runner accepts only its fixed, explicitly fictional fixture.')
    return fixture


def claim_from_draft(draft, sources):
    claim = copy.deepcopy(draft)
    for owner in [claim, *claim.get('attributions', [])]:
        for field in ['evidence', 'counterEvidence']:
            if field in owner:
                owner[field] = [renderer.memory.anchor(sources[key], 0, len(sources[key]['content'])) for key in owner[field]]
    return claim


def packet_from_fixture(fixture):
    sources = [dict(s, scope='Entirely fictional selected record. No completeness or publication permission implied.')
               for s in fixture['sources']]
    source_map = {s['id']: s for s in sources}
    packet = {'schema': 'career-context/v1', 'updatedAt': fixture['updatedAt'], 'reviewStatus': 'draft',
              'synthetic': True, 'person': copy.deepcopy(fixture['person']), 'sources': sources,
              'accounts': copy.deepcopy(fixture['accounts']),
              'memory': {'schema': 'career-memory/v1', 'claims': [claim_from_draft(c, source_map) for c in fixture['claims']]}}
    packet['timeline'] = [
        {'id': 'period-' + a['id'], 'period': a['period'], 'title': a['title'], 'focus': a['aim'],
         'actions': [a['contribution']], 'tension': a['context'], 'approach': ' '.join(a['decisions']),
         'questions': list(a['questions']), 'sourceRefs': list(a['sourceRefs']), 'accountIds': [a['id']]}
        for a in packet['accounts']]
    renderer.validate(packet)
    return packet


def reconcile_followup(packet, fixture):
    packet = copy.deepcopy(packet)
    follow = fixture['followUp']
    source = dict(follow['source'], scope='Fictional follow-up. Preserves the earlier announcement and conflicting extract.')
    packet['sources'].append(source)
    packet['updatedAt'] = source['date']
    claims = {c['id']: c for c in packet['memory']['claims']}
    claim = claims['reminder-wide']
    claim['status'] = 'rejected'
    claim['rationale'] = 'The later office follow-up confirms that setup was mistaken for use. Only one office used acknowledgements, then stopped.'
    claim['nextQuestion'] = ''
    claim['counterEvidence'].append(renderer.memory.anchor(source, 0, len(source['content'])))
    packet['memory']['claims'].append(claim_from_draft(follow['claim'], {s['id']: s for s in packet['sources']}))
    account = next(a for a in packet['accounts'] if a['id'] == 'renewal-reminders')
    account['title'] = 'A reminder trial that was later retired'
    account['summary'] = 'I scoped and tested an AI-assisted reminder prototype with two administrators using fictional grants. Later follow-up established that only one office used acknowledgements, then stopped. The prototype was retired; an earlier all-office adoption claim was rejected.'
    account['outcome'] = 'The July 2025 demonstration was followed by limited use at one office in February 2026. The prototype was later retired. No reduction in missed renewals was established.'
    account['questions'] = []
    account['sourceRefs'].append(source['id'])
    period = next(p for p in packet['timeline'] if account['id'] in p['accountIds'])
    period['title'] = account['title']
    period['questions'] = []
    period['sourceRefs'].append(source['id'])
    renderer.validate(packet)
    return packet


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def rank_of(hits, targets):
    return next((i for i, hit in enumerate(hits, 1) if hit['id'] in targets), None)


def evaluate_queries(packet, fixture, encoder):
    results = []
    for case in fixture['queries']:
        lexical = retrieval.search(packet, [case['query']], layers=['sources', 'claims'], limit=50)
        hybrid = retrieval.search(packet, [case['query']], layers=['sources', 'claims'], limit=50,
                                  mode='hybrid', encoder=encoder)
        row = {'id': case['id'], 'query': case['query'], 'targets': {k: case[k] for k in ['sources', 'claims']},
               'lexicalRanks': {}, 'hybridRanks': {}, 'topHits': {}}
        for layer in ['sources', 'claims']:
            row['lexicalRanks'][layer] = rank_of(lexical['layers'][layer]['hits'], case[layer])
            row['hybridRanks'][layer] = rank_of(hybrid['layers'][layer]['hits'], case[layer])
            row['topHits'][layer] = [dict(id=h['id'], status=h.get('status'), fields=[m['field'] for m in h['matches']])
                                     for h in hybrid['layers'][layer]['hits'][:5]]
        row['discoveredWithinFive'] = any(r is not None and r <= 5 for r in row['hybridRanks'].values())
        results.append(row)
        print(json.dumps({'query': case['id'], 'lexical': row['lexicalRanks'], 'hybrid': row['hybridRanks']}), flush=True)
    return results


def browser(stage, source, output):
    run = subprocess.run(['node', str(ROOT / 'tests/check_realistic_workflow.cjs'), stage, str(source), str(output)],
                         cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=100)
    if run.returncode:
        raise RuntimeError('Browser ' + stage + ' failed: ' + run.stderr[-5000:])
    return json.loads(run.stdout)


def run_workflow(output, model_dir):
    output = Path(output).expanduser().resolve()
    if output.is_relative_to(ROOT.resolve()):
        raise ValueError('Write the synthetic run outside the source checkout.')
    output.mkdir(parents=True, exist_ok=True)
    fixture = load_fixture()
    report = {'synthetic': True, 'fixtureSha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
              'scope': fixture['scope'], 'checks': [], 'passed': False}

    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    try:
        packet = packet_from_fixture(fixture)
        report['counts'] = {'accounts': len(packet['accounts']), 'sources': len(packet['sources']),
                            'claims': len(packet['memory']['claims']), 'queries': len(fixture['queries'])}
        save_json(output / 'input.json', packet)
        # Source/model files are already selected. Block Python socket creation
        # for the entire local data workflow, including model initialization.
        with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden during local workflow')):
            encoder = renderer.load_helper('semantic_context').LocalEncoder(model_dir)
            report['model'] = encoder.metadata
            report['retrieval'] = evaluate_queries(packet, fixture, encoder)
            first = output / 'first-retrieval.json'
            if not first.exists():
                save_json(first, {'fixtureSha256': report['fixtureSha256'], 'model': report['model'], 'retrieval': report['retrieval']})
            report['retrievalSummary'] = {
                'hybridWithinFive': sum(r['discoveredWithinFive'] for r in report['retrieval']),
                'lexicalWithinFive': sum(any(v is not None and v <= 5 for v in r['lexicalRanks'].values()) for r in report['retrieval'])}
            for case in fixture['queries']:
                if case.get('status'):
                    result = retrieval.search(packet, [case['query']], layers=['claims'], limit=50, mode='hybrid', encoder=encoder)
                    check(case['id'] + ': rejected target remains visibly rejected', any(h['id'] in case['claims'] and h['status'] == case['status'] for h in result['layers']['claims']['hits']))
            evidence = retrieval.expand(packet, 'claims:hiring-speed', limit=50)
            check('Rejected metric retains original praise and later correction',
                  {'hiring-praise', 'hiring-correction'} <= {r['record']['id'] for r in evidence['related']['sources']['records']})
            offered = retrieval.expand(packet, 'claims:relay-offer', limit=50)
            check('Earlier offer retains offered state alongside later completion',
                  offered['record']['attributions'][0]['state'] == 'offered' and
                  'relay-reviewed' in {r['record']['id'] for r in offered['related']['claims']['records']})
            # This is the fixed fictional starting artifact, not a person's saved
            # working file. Actual reviewed/update paths retain strict guards.
            renderer.render(output / 'input.json', output / 'initial.html', guided=True, allow_view_removal=True)
            report['browserReview'] = browser('review', output / 'initial.html', output)
            reviewed = renderer.load_packet(output / 'reviewed.html')
            renderer.validate(reviewed)
            check('Browser save keeps every claim and exact source', reviewed['memory'] == packet['memory'] and reviewed['sources'] == packet['sources'])
            with tempfile.TemporaryDirectory(dir=output, prefix='.workflow-archive-') as directory:
                private = Path(directory)
                first_revision = archive.build(output / 'reviewed.html', private)
                database = private / 'career.sqlite'
                before = database.read_bytes()
                loaded = retrieval.load_input(database)
                result = retrieval.search(loaded, ['recovering from upstream outages without duplicate transactions'],
                                          layers=['sources'], mode='hybrid', encoder=encoder)
                check('SQLite retrieval finds exact late incident evidence', any(h['id'] == 'relay-runbook' for h in result['layers']['sources']['hits'][:5]))
                check('SQLite semantic retrieval is read-only', before == database.read_bytes())
                updated = reconcile_followup(loaded, fixture)
                old_basis, new_basis = renderer.memory.review_basis(loaded), renderer.memory.review_basis(updated)
                changed = [aid for aid in old_basis['accounts'] if old_basis['accounts'][aid] != new_basis['accounts'][aid]]
                check('Follow-up changes only its dependent account', changed == ['renewal-reminders'])
                save_json(output / 'updated.json', updated)
                archive.build(output / 'updated.json', private, update=True)
                (output / 'updated.html').write_bytes((private / 'CAREER-CONTEXT.html').read_bytes())
                report['browserUpdate'] = browser('update', output / 'updated.html', output)
                current = renderer.load_packet(output / 'saved-current.html')
                renderer.validate(current)
                check('Private browser save keeps the corrected memory', current['memory'] == updated['memory'])
                archive.build(output / 'saved-current.html', private, update=True)
                archive.export(database, private / 'recovered.html')
                recovered = renderer.load_packet(private / 'recovered.html')
                check('Recovered current revision preserves the full packet', recovered == current)
                historical = archive.load_snapshot(database, first_revision['revision'])
                check('Historical revision retains disputed claim without later evidence',
                      next(c for c in historical['memory']['claims'] if c['id'] == 'reminder-wide')['status'] == 'disputed'
                      and not any(s['id'] == 'reminder-followup' for s in historical['sources']))
                expanded = retrieval.expand(current, 'claims:reminder-wide', limit=50)
                check('Current rejected claim expands to the incoming correction',
                      expanded['record']['status'] == 'rejected' and
                      'reminder-retired' in {r['record']['id'] for r in expanded['related']['claims']['records']})
                selection = renderer.load_helper('context_selection').select(current, ['booking-relay', 'renewal-reminders'])
                text = json.dumps(selection)
                check('Selected-context projection excludes sources, memory and private notes',
                      'memory' not in selection and 'sources' not in selection and 'PRIVATE_' not in text)
                check('Selected narrative carries the retirement correction and shared credit',
                      'retired' in text and 'Contributor 07' in text and 'AI generated' in text)
                # The archive is a temporary synthetic test fixture. Keep one
                # obvious portable entry point; remove the DB when the run ends.
                (output / 'CAREER-CONTEXT.html').write_bytes((private / 'CAREER-CONTEXT.html').read_bytes())
            check('All predeclared queries discover intended evidence within five',
                  report['retrievalSummary']['hybridWithinFive'] == len(fixture['queries']))
        report['passed'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        save_json(output / 'results.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model-dir', required=True, type=Path)
    args = parser.parse_args()
    result = run_workflow(args.output, args.model_dir)
    print(json.dumps({'passed': result['passed'], 'counts': result['counts'],
                      'retrieval': result['retrievalSummary'], 'checks': len(result['checks'])}), flush=True)


if __name__ == '__main__':
    main()
