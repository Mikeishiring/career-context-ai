"""The realistic fixture's evidence and correction contracts, without model dependencies."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('realistic_workflow_test', ROOT / 'tools/check_career_workflow.py')
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class RealisticWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = workflow.load_fixture()
        self.packet = workflow.packet_from_fixture(self.fixture)

    def test_realistic_history_is_valid_and_retains_conflicting_originals(self):
        workflow.renderer.validate(self.packet)
        claims = {c['id']: c for c in self.packet['memory']['claims']}
        self.assertEqual(len(self.packet['sources']), 26)
        self.assertEqual(len(self.packet['accounts']), 6)
        self.assertEqual(claims['hiring-speed']['status'], 'rejected')
        self.assertEqual(claims['reminder-wide']['status'], 'disputed')
        expanded = workflow.retrieval.expand(self.packet, 'claims:hiring-speed', limit=50)
        ids = {r['record']['id'] for r in expanded['related']['sources']['records']}
        self.assertTrue({'hiring-praise', 'hiring-correction'} <= ids)
        self.assertEqual(claims['relay-offer']['attributions'][0]['state'], 'offered')
        self.assertTrue(any(a['state'] == 'completed' for a in claims['relay-reviewed']['attributions']))

    def test_followup_preserves_history_and_updates_all_current_descriptions(self):
        initial = copy.deepcopy(self.packet)
        updated = workflow.reconcile_followup(initial, self.fixture)
        workflow.renderer.preserve_views(initial, updated)
        self.assertEqual(initial, self.packet)
        self.assertEqual(updated['sources'][:26], initial['sources'])
        self.assertEqual({c['id'] for c in initial['memory']['claims']} - {c['id'] for c in updated['memory']['claims']}, set())
        account = next(a for a in updated['accounts'] if a['id'] == 'renewal-reminders')
        period = next(p for p in updated['timeline'] if account['id'] in p['accountIds'])
        self.assertIn('retired', account['title'])
        self.assertEqual(period['title'], account['title'])
        old_basis = workflow.renderer.memory.review_basis(initial)
        new_basis = workflow.renderer.memory.review_basis(updated)
        self.assertEqual([key for key in old_basis['accounts'] if old_basis['accounts'][key] != new_basis['accounts'][key]], ['renewal-reminders'])
        expanded = workflow.retrieval.expand(updated, 'claims:reminder-wide', limit=50)
        self.assertEqual(expanded['record']['status'], 'rejected')
        self.assertIn('reminder-retired', {r['record']['id'] for r in expanded['related']['claims']['records']})

    def test_selected_context_does_not_acquire_private_memory(self):
        updated = workflow.reconcile_followup(self.packet, self.fixture)
        selected = workflow.renderer.load_helper('context_selection').select(updated, ['renewal-reminders'])
        self.assertNotIn('memory', selected)
        self.assertNotIn('sources', selected)
        self.assertEqual(selected['accounts'][0]['summary'], updated['accounts'][-1]['summary'])
        self.assertEqual(selected['sourceEvidenceIncluded'], False)


if __name__ == '__main__':
    unittest.main()
