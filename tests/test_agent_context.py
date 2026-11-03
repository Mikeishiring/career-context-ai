"""Agent navigation and durable research rounds preserve evidence and permission boundaries."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


agent = module('agent_context_tests', ROOT / 'skills/career-context-sheet/scripts/agent_context.py')
workflow = module('agent_fixture_tests', ROOT / 'tools/check_career_workflow.py')


class AgentContextTests(unittest.TestCase):
    def setUp(self):
        self.packet = workflow.packet_from_fixture(workflow.load_fixture())
        self.basis = agent.renderer.sections.evidence_fingerprint(self.packet)
        self.packet['journey'] = agent.renderer.guided_path.initial_state(self.packet, self.basis)
        self.state = {'schema': 'career-investigation/v1', 'contextSha256': self.basis,
                      'goal': 'Understand the hiring contribution', 'rounds': [], 'leads': [], 'stopReason': ''}
        self.packet['journey']['investigation'] = self.state

    def round(self, purpose, key='round-1'):
        return {'id': key, 'purpose': purpose, 'question': 'Was the hiring improvement measured?',
                'finding': 'The recognition paragraph needs checking against the correction.',
                'accountIds': ['hiring-panels'], 'sourceRefs': ['hiring-praise'], 'claimIds': ['hiring-speed']}

    def lead(self, status='ready'):
        return {'id': 'check-measurement', 'question': 'What can be claimed about speed?', 'why': 'The requested bullet asserts an improvement.',
                'status': status, 'nextAction': 'Read the retained correction and compare the measurement periods.',
                'accountIds': ['hiring-panels'], 'sourceRefs': ['hiring-correction'], 'claimIds': ['hiring-speed']}

    def test_complete_account_bundle_carries_support_conflicts_and_reviews_together(self):
        self.packet['journey']['notes']['review:hiring-panels'] = 'Retain shared credit.'
        before = copy.deepcopy(self.packet)
        with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden')):
            bundle = agent.account_bundle(self.packet, 'hiring-panels', limit=50)
        sources = {s['record']['id']: s['record'] for s in bundle['sources']['records']}
        self.assertTrue({'hiring-praise', 'hiring-correction', 'hiring-decision', 'hiring-adoption'} <= set(sources))
        original = {s['id']: s for s in self.packet['sources']}
        self.assertTrue(all(sources[key] == original[key] for key in sources))
        claims = {c['record']['id']: c['record'] for c in bundle['claims']['records']}
        self.assertEqual(claims['hiring-speed']['status'], 'rejected')
        self.assertTrue(claims['hiring-speed']['counterEvidence'])
        self.assertEqual(bundle['notes']['review:hiring-panels'], 'Retain shared credit.')
        self.assertEqual(self.packet, before)
        self.assertFalse(bundle['permissionsGranted'])

    def test_navigation_pages_expose_omissions_and_unassigned_claims(self):
        first = agent.briefing(self.packet, limit=2)
        second = agent.briefing(self.packet, limit=2, offset=first['accountMap']['nextOffset'])
        self.assertEqual(first['accountMap']['total'], 6)
        self.assertFalse({a['id'] for a in first['accountMap']['records']} & {a['id'] for a in second['accountMap']['records']})
        global_claims = [c for c in self.packet['memory']['claims'] if not c['accountIds']]
        self.assertEqual(first['unassignedClaims']['total'], len(global_claims))
        bundle = agent.account_bundle(self.packet, 'hiring-panels', limit=1)
        self.assertEqual(bundle['sources']['nextOffset'], 1)
        self.assertGreater(bundle['sources']['total'], 1)

    def test_bundle_includes_sources_retained_only_by_timeline_or_investigation(self):
        for key in ['timeline-only', 'round-only', 'lead-only']:
            self.packet['sources'].append({'id': key, 'kind': 'person_account', 'label': key,
                                           'content': 'A separate selected recollection.', 'scope': 'Fictional test.'})
        next(t for t in self.packet['timeline'] if 'hiring-panels' in t['accountIds'])['sourceRefs'].append('timeline-only')
        self.state['rounds'] = [self.round('investigate')]
        self.state['rounds'][0]['sourceRefs'] = ['round-only']
        self.state['leads'] = [self.lead()]
        self.state['leads'][0]['sourceRefs'] = ['lead-only']
        # A lead may link through the claim instead of duplicating its account link.
        self.state['leads'][0]['accountIds'] = []
        bundle = agent.account_bundle(self.packet, 'hiring-panels', limit=50)
        ids = {s['record']['id'] for s in bundle['sources']['records']}
        self.assertTrue({'timeline-only', 'round-only', 'lead-only'} <= ids)
        self.assertEqual(bundle['investigation']['rounds']['total'], 1)
        self.assertEqual(bundle['investigation']['leads']['total'], 1)

    def test_multiple_rounds_continue_challenge_and_reopen_without_pass_quota(self):
        self.assertEqual(agent.next_round(self.packet)['stage'], 'orient')
        self.state['rounds'].append(self.round('orient'))
        self.state['leads'].append(self.lead())
        self.assertEqual(agent.next_round(self.packet)['stage'], 'investigate')
        self.state['rounds'].append(self.round('investigate', 'round-2'))
        self.state['leads'][0]['status'] = 'resolved'
        self.assertEqual(agent.next_round(self.packet)['stage'], 'map')
        self.state['rounds'].append(self.round('map', 'map-1'))
        # A wider reading of the map can reveal more work before any full challenge.
        self.state['leads'][0]['status'] = 'ready'
        self.assertEqual(agent.next_round(self.packet)['stage'], 'investigate')
        self.state['rounds'].append(self.round('investigate', 'round-3'))
        self.state['leads'][0]['status'] = 'resolved'
        self.assertEqual(agent.next_round(self.packet)['stage'], 'map')
        self.state['rounds'].append(self.round('map', 'map-2'))
        self.assertEqual(agent.next_round(self.packet)['stage'], 'challenge')
        self.state['rounds'].append(self.round('challenge', 'round-4'))
        self.state['leads'][0]['status'] = 'ready'
        self.assertEqual(agent.next_round(self.packet)['stage'], 'investigate')
        self.state['leads'][0]['status'] = 'needs_person'
        self.assertEqual(agent.next_round(self.packet)['stage'], 'handoff')
        self.assertTrue(agent.next_round(self.packet)['stopReasonMissing'])
        self.state['stopReason'] = 'Only the person can supply the requested personal meaning; no accessible material lead remains.'
        self.assertFalse(agent.next_round(self.packet)['stopReasonMissing'])
        self.assertEqual(agent.next_round(self.packet, 'Understand the volunteer work')['stage'], 'orient')

    def test_evidence_change_requires_reconciliation_without_refreshing_saved_basis(self):
        self.state['rounds'] = [self.round('challenge')]
        self.packet['person']['overview'] += ' A new supplied statement.'
        before = copy.deepcopy(self.packet)
        self.assertEqual(agent.next_round(self.packet)['stage'], 'reconcile')
        self.assertEqual(self.packet, before)

    def test_new_person_input_reopens_a_completed_challenge_independently_of_evidence(self):
        self.state['rounds'] = [self.round('challenge')]
        self.state['stopReason'] = 'The selected scope is checked.'
        self.state['reviewSha256'] = agent.renderer.guided_path.review_fingerprint(self.packet)
        self.assertEqual(agent.next_round(self.packet)['stage'], 'handoff')
        self.packet['journey']['reviews']['hiring-panels'] = {'decision': 'correction', 'reason': 'That was my colleague, not me.',
                                                             'draft': '', 'sourceRefs': [], 'depth': 'open', 'practised': False}
        self.packet['journey']['notes']['review:hiring-panels'] = 'Please check shared credit again.'
        self.assertEqual(agent.renderer.sections.evidence_fingerprint(self.packet), self.basis)
        next_step = agent.next_round(self.packet)
        self.assertEqual(next_step['stage'], 'reconcile')
        self.assertFalse(next_step['reviewInputCurrent'])
        self.assertIn('my colleague', next_step['reviewInput']['reviews']['hiring-panels']['reason'])
        self.state['reviewSha256'] = next_step['reviewSha256']
        self.state['rounds'].append(self.round('reconcile', 'review-reconciled'))
        self.assertEqual(agent.next_round(self.packet)['stage'], 'map')
        self.state.pop('reviewSha256')
        self.assertEqual(agent.next_round(self.packet)['stage'], 'reconcile')
        self.state['rounds'].append(self.round('challenge', 'challenge-again'))
        review = self.packet['journey']['reviews']['hiring-panels']
        review.update(decision='kept', depth='clear')
        self.state['reviewSha256'] = agent.renderer.guided_path.review_fingerprint(self.packet)
        review['practised'] = True
        self.assertEqual(agent.next_round(self.packet)['stage'], 'handoff')
        review['depth'] = 'open'
        self.assertEqual(agent.next_round(self.packet)['stage'], 'reconcile')

    def test_research_schema_rejects_fake_links_statuses_and_permission_fields(self):
        self.state['rounds'] = [self.round('orient')]
        self.state['leads'] = [self.lead()]
        agent.renderer.validate(self.packet)
        for mutate in [lambda s: s.update(allowUpload=True), lambda s: s['leads'][0].update(status='authorized'),
                       lambda s: s['rounds'][0].update(sourceRefs=['absent']), lambda s: s['rounds'][0].update(claimIds=['absent']),
                       lambda s: s['rounds'].append(copy.deepcopy(s['rounds'][0])), lambda s: s.update(contextSha256='bad')]:
            candidate = copy.deepcopy(self.packet)
            mutate(candidate['journey']['investigation'])
            with self.assertRaises(ValueError):
                agent.renderer.validate(candidate)

    def test_research_survives_private_archive_but_is_excluded_from_selected_and_public_exports(self):
        self.state['goal'] = 'PRIVATE_INVESTIGATION_CANARY'
        self.state['rounds'] = [self.round('orient')]
        self.state['leads'] = [self.lead()]
        self.packet['publicProfile'] = agent.renderer.public_profile.initial_state(self.packet, self.basis)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'input.json'
            source.write_text(json.dumps(self.packet), encoding='utf-8')
            archive = agent.renderer.load_helper('archive_context')
            result = archive.build(source, folder / 'archive')
            restored = archive.load_snapshot(Path(result['database']))
            self.assertEqual(restored['journey']['investigation'], self.state)
            before = Path(result['path']).read_bytes()
            with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden')), redirect_stdout(io.StringIO()) as out:
                agent.main([result['path'], '--next'])
            self.assertEqual(json.loads(out.getvalue())['stage'], 'investigate')
            self.assertEqual(Path(result['path']).read_bytes(), before)
        selected = agent.renderer.load_helper('context_selection').select(self.packet, ['hiring-panels'])
        self.assertNotIn('PRIVATE_INVESTIGATION_CANARY', json.dumps(selected))
        self.assertNotIn('PRIVATE_INVESTIGATION_CANARY', agent.renderer.public_profile.preview(self.packet['publicProfile']))
        missing = copy.deepcopy(self.packet)
        missing['journey'].pop('investigation')
        with self.assertRaisesRegex(ValueError, 'investigation'):
            agent.renderer.preserve_views(self.packet, missing)

    def test_cli_fails_explicitly_instead_of_silently_truncating_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'input.json'
            source.write_text(json.dumps(self.packet), encoding='utf-8')
            before = source.read_bytes()
            with patch.object(agent, 'MAX_OUTPUT_CHARS', 100), redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit) as stopped:
                agent.main([str(source), '--account', 'hiring-panels'])
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn('Nothing was silently truncated', error.getvalue())
            self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
