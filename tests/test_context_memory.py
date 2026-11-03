"""Private evidence memory, retrieval and dependency-scoped review contracts."""
import copy
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('memory_retrieval', ROOT / 'skills/career-context-sheet/scripts/retrieve_context.py')
retrieval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retrieval)
renderer = retrieval.renderer
memory = renderer.memory
archive = renderer.load_helper('archive_context')


def fixture():
    packet = renderer.load_packet(ROOT / 'examples/career-context.json')
    account = packet['accounts'][0]['id']
    source = {'id': 'original-decision', 'kind': 'source_excerpt', 'label': 'Selected decision',
              'content': 'We clarified who owned the handoff. Another contributor reviewed the change. Use remained limited.',
              'scope': 'Fictional selected record; wider rollout is unknown.'}
    packet['sources'].append(source)
    packet['memory'] = {'schema': 'career-memory/v1', 'claims': [
        {'id': 'handoff', 'kind': 'fact', 'status': 'qualified',
         'statement': 'We clarified ownership; use remained limited.', 'accountIds': [account],
         'evidence': [memory.anchor(source, 0, len(source['content']))],
         'aliases': ['handling ambiguity', 'responsibility'], 'rationale': 'Retain shared credit and limited use.'},
        {'id': 'solo', 'kind': 'interpretation', 'status': 'rejected',
         'statement': 'I independently designed the whole process.', 'accountIds': [], 'evidence': [],
         'counterEvidence': [memory.anchor(source, 34, 74)],
         'relations': [{'claimId': 'handoff', 'type': 'contradicts'}],
         'rationale': 'The original explicitly credits another contributor.'},
        {'id': 'pattern', 'kind': 'hypothesis', 'status': 'candidate',
         'statement': 'Clarifying responsibility may connect several episodes.', 'accountIds': [], 'evidence': [],
         'rationale': 'A lead to test, not a career trait.', 'nextQuestion': 'Do other episodes support this interpretation?'}]}
    return packet


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.packet = fixture()

    def test_exact_anchors_and_unassigned_hypotheses_are_valid(self):
        renderer.validate(self.packet)
        self.assertEqual(memory.claims(self.packet)[2]['accountIds'], [])

    def test_forged_stale_and_foreign_anchors_are_rejected(self):
        for field, value in [('quote', 'I owned everything.'), ('sourceSha256', '0' * 64),
                             ('sourceId', 'unread'), ('start', True), ('end', 10000)]:
            packet = copy.deepcopy(self.packet)
            packet['memory']['claims'][0]['evidence'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                renderer.validate(packet)
        self.packet['sources'][-1]['content'] += ' A later revision.'
        with self.assertRaisesRegex(ValueError, 'stale'):
            renderer.validate(self.packet)

    def test_supported_claim_requires_evidence_and_hypothesis_is_not_fact(self):
        for change in [{'evidence': []}, {'kind': 'hypothesis'}, {'accountIds': ['foreign']},
                       {'relations': [{'claimId': 'missing', 'type': 'supports'}]},
                       {'permission': 'read everything'}]:
            packet = copy.deepcopy(self.packet)
            packet['memory']['claims'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                renderer.validate(packet)

    def test_rejected_interpretations_are_searchable_and_expand_counterevidence(self):
        hits = retrieval.search(self.packet, ['independently process'])['layers']['claims']['hits']
        self.assertEqual(hits[0]['status'], 'rejected')
        result = retrieval.expand(self.packet, 'claims:handoff')
        self.assertEqual({r['record']['id'] for r in result['related']['claims']['records']}, {'handoff', 'solo'})
        original = next(r for r in result['related']['sources']['records'] if r['record']['id'] == 'original-decision')
        self.assertIn('Another contributor', original['record']['content'])
        self.assertEqual(original['sourceSha256'], memory.source_hash(self.packet['sources'][-1]))

    def test_alias_retrieval_ranking_and_literal_compatibility(self):
        result = retrieval.search(self.packet, ['handling ambiguity'])
        self.assertEqual(result['layers']['claims']['hits'][0]['id'], 'handoff')
        self.assertEqual(result['layers']['claims']['hits'][0]['links']['accountIds'], [self.packet['accounts'][0]['id']])
        self.assertEqual(retrieval.search(self.packet, ['ambiguity handling'], mode='literal')['layers']['claims']['totalMatches'], 0)
        self.assertEqual(retrieval.search(self.packet, ['ambiguity handling'])['layers']['claims']['totalMatches'], 1)
        second = copy.deepcopy(memory.claims(self.packet)[0])
        second.update(id='other', aliases=[], statement='Handling ambiguity was discussed.')
        self.packet['memory']['claims'].insert(0, second)
        self.assertEqual(retrieval.search(self.packet, ['handling ambiguity'])['layers']['claims']['hits'][0]['id'], 'handoff')

    def test_index_and_expansion_are_paginated_without_source_dump(self):
        page = retrieval.index(self.packet, layers=['claims'], limit=1)
        self.assertEqual(page['layers']['claims']['nextOffset'], 1)
        self.assertNotIn('content', json.dumps(page))
        self.assertEqual(retrieval.expand(self.packet, 'claims:handoff', limit=1)['related']['claims']['nextOffset'], 1)
        self.assertEqual(len(retrieval.expand(self.packet, 'claims:handoff', limit=1, offset=1)['related']['claims']['records']), 1)

    def test_review_dependencies_ignore_overview_and_isolate_changes(self):
        before = memory.review_basis(self.packet)
        self.packet['person']['overview'] += ' Edited wording.'
        self.packet['profile'] = {'targetRoles': ['Another role']}
        self.assertEqual(before, memory.review_basis(self.packet))
        memory.claims(self.packet)[0]['aliases'].append('another retrieval lead')
        self.assertEqual(before, memory.review_basis(self.packet))
        # Even an unassigned incoming correction affects its linked account only.
        memory.claims(self.packet)[1]['rationale'] += ' Keep the original credit.'
        after = memory.review_basis(self.packet)
        first, second = [a['id'] for a in self.packet['accounts'][:2]]
        self.assertNotEqual(before['accounts'][first], after['accounts'][first])
        self.assertEqual(before['accounts'][second], after['accounts'][second])

    def test_changed_source_reopens_only_accounts_that_depend_on_it(self):
        before = memory.review_basis(self.packet)
        self.packet['sources'][-1]['scope'] += ' Clarified scope.'
        after = memory.review_basis(self.packet)
        changed = [key for key in before['accounts'] if before['accounts'][key] != after['accounts'][key]]
        self.assertEqual(changed, [self.packet['accounts'][0]['id']])

    def test_memory_cannot_silently_disappear_on_update(self):
        incoming = copy.deepcopy(self.packet)
        incoming['memory']['claims'].pop()
        with self.assertRaisesRegex(ValueError, 'memory'):
            renderer.preserve_views(self.packet, incoming)

    def test_missing_companion_html_does_not_allow_memory_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            source.write_text(json.dumps(self.packet), encoding='utf-8')
            archive.build(source, root / 'archive')
            (root / 'archive/CAREER-CONTEXT.html').unlink()
            older = renderer.load_packet(ROOT / 'examples/career-context.json')
            source.write_text(json.dumps(older), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'memory'):
                archive.build(source, root / 'archive', update=True)
            self.assertEqual(archive.load_snapshot(root / 'archive/career.sqlite')['memory'], self.packet['memory'])

    def test_substantive_memory_invalidates_derived_outputs_but_aliases_do_not(self):
        before = renderer.sections.evidence_fingerprint(self.packet)
        memory.claims(self.packet)[0]['aliases'].append('adjacent words')
        self.assertEqual(before, renderer.sections.evidence_fingerprint(self.packet))
        memory.claims(self.packet)[1]['rationale'] += ' A changed interpretation.'
        self.assertNotEqual(before, renderer.sections.evidence_fingerprint(self.packet))

    def test_private_roundtrip_archive_history_and_public_boundaries(self):
        marker = 'PRIVATE_MEMORY_CANARY </script><img src=x onerror=alert(1)>'
        memory.claims(self.packet)[2]['rationale'] = marker
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            source.write_text(json.dumps(self.packet), encoding='utf-8')
            first = archive.build(source, root / 'archive')
            database = root / 'archive/career.sqlite'
            page = root / 'archive/CAREER-CONTEXT.html'
            self.assertNotIn(marker, page.read_text(encoding='utf-8'))
            self.assertEqual(renderer.load_packet(page)['memory'], self.packet['memory'])
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM memory_claims').fetchone()[0], 3)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            before = database.read_bytes()
            self.assertTrue(any(r['kind'] == 'claim' for r in archive.search(database, 'handling ambiguity')))
            self.assertEqual(archive.search(database, 'x' * 500), [])
            self.assertEqual(retrieval.load_input(database)['memory'], self.packet['memory'])
            self.assertEqual(before, database.read_bytes())
            memory.claims(self.packet)[2]['status'] = 'rejected'
            source.write_text(json.dumps(self.packet), encoding='utf-8')
            archive.build(source, root / 'archive', update=True)
            historical = retrieval.load_input(database, first['revision'])
            self.assertEqual(memory.claims(historical)[2]['status'], 'candidate')
            recovered = root / 'recovered.html'
            archive.export(database, recovered)
            self.assertEqual(renderer.load_packet(recovered)['memory'], self.packet['memory'])
            selection = renderer.load_helper('context_selection').select(self.packet, [self.packet['accounts'][0]['id']])
            self.assertNotIn('memory', selection)
            self.assertNotIn('PRIVATE_MEMORY_CANARY', json.dumps(selection))
            profile = renderer.public_profile.initial_state(self.packet, renderer.sections.evidence_fingerprint(self.packet))
            self.assertNotIn('PRIVATE_MEMORY_CANARY', renderer.public_profile.preview(profile))


if __name__ == '__main__':
    unittest.main()
