"""Collection receipts and chosen corrections survive rendering and archive recovery."""
import copy
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/career-context-sheet/scripts'
spec = importlib.util.spec_from_file_location('collection_archive', SCRIPTS / 'archive_context.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)
renderer = archive.renderer


class CollectionPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.packet = json.loads((ROOT / 'examples/complete-context.json').read_text(encoding='utf-8'))
        self.basis = renderer.sections.evidence_fingerprint(self.packet)
        self.packet['journey'] = renderer.guided_path.initial_state(self.packet, self.basis)
        self.packet['journey']['coverage'] = {'startMonth': '2025-12', 'endMonth': '2026-01',
            'streams': [{'id': 'mail', 'platform': 'Email', 'location': 'Selected work export', 'scope': 'Work only'}], 'checks': []}
        self.receipt = {'streamId': 'mail', 'month': '2025-12', 'status': 'checked',
            'note': 'Selected work folder; all pages read. Source dates checked separately.',
            'sourceRefs': [self.packet['sources'][0]['id']], 'cursor': '', 'found': 3, 'read': 3}

    def save(self):
        source = self.folder / 'input.json'
        source.write_text(json.dumps(self.packet), encoding='utf-8')
        return source

    def test_plan_does_not_claim_existing_collection_was_checked(self):
        c = renderer.guided_path.initial_coverage(self.packet)
        self.assertEqual(c['checks'], [])
        self.assertEqual((c['startMonth'], c['endMonth']), ('', ''))

    def test_legacy_location_boundaries_are_never_truncated(self):
        scope = 'Work scope. ' * 200 + 'EXCLUDE private correspondence.'
        self.packet['collection'] = [{'platform': 'P' * 200, 'location': 'L' * 400,
            'scope': scope, 'nextStep': '', 'access': 'export', 'status': 'partial'}]
        self.packet['journey'] = renderer.guided_path.initial_state(self.packet, self.basis)
        renderer.validate(self.packet)
        self.assertEqual(self.packet['journey']['coverage']['streams'][0]['scope'], scope)

    def test_sources_can_be_retained_by_coverage_before_account_selection(self):
        self.packet.pop('presentation', None)
        self.packet.pop('interview', None)
        self.packet.pop('timeline', None)
        self.packet['accounts'] = []
        self.packet['sources'] = [self.packet['sources'][0]]
        self.packet['journey']['storyId'] = ''
        self.packet['journey']['baseline']['accounts'] = {}
        self.packet['journey']['coverage']['checks'] = [self.receipt]
        renderer.validate(self.packet)
        self.packet['journey']['coverage']['checks'] = []
        with self.assertRaisesRegex(ValueError, 'unreferenced'):
            renderer.validate(self.packet)

    def test_checked_requires_real_receipt_references_and_exhausted_pages(self):
        for change in [{'sourceRefs': []}, {'sourceRefs': ['missing']}, {'note': ''},
                       {'cursor': 'next-page'}, {'found': 4}, {'read': True}, {'read': 4},
                       {'month': '2025-11'}, {'streamId': 'other'}, {'month': '2025-13'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.packet['journey']['coverage']['checks'] = [dict(self.receipt, **change)]
                renderer.validate(self.packet)

    def test_empty_and_blocked_are_explicit_not_false_completion(self):
        c = self.packet['journey']['coverage']
        c['checks'] = [dict(self.receipt, status='empty', sourceRefs=[], found=0, read=0,
                            note='Exact month and work folder query returned zero; pagination exhausted.')]
        renderer.validate(self.packet)
        c['checks'][0]['cursor'] = 'next'
        with self.assertRaises(ValueError): renderer.validate(self.packet)
        c['checks'] = [dict(self.receipt, status='blocked', sourceRefs=[], found=0, read=0, note='Export unavailable.')]
        renderer.validate(self.packet)

    def test_duplicate_and_shrinking_receipts_are_rejected(self):
        c = self.packet['journey']['coverage']
        c['checks'] = [self.receipt, self.receipt]
        with self.assertRaises(ValueError): renderer.validate(self.packet)
        c['checks'] = [self.receipt]
        c['startMonth'] = '2026-01'
        with self.assertRaises(ValueError): renderer.validate(self.packet)

    def test_chosen_revision_is_separate_from_original_evidence(self):
        account = self.packet['accounts'][0]
        original = account['summary']
        decision = {'decision': 'revision', 'draft': 'A chosen alternative wording.',
            'reason': 'Preserve the shared contribution.', 'sourceRefs': account['sourceRefs'],
            'depth': 'pending', 'practised': False}
        self.packet['journey']['reviews'][account['id']] = decision
        renderer.validate(self.packet)
        self.assertEqual(account['summary'], original)
        self.assertEqual(renderer.sections.evidence_fingerprint(self.packet), self.basis)
        decision['sourceRefs'] = []
        with self.assertRaises(ValueError): renderer.validate(self.packet)

    def test_archive_adds_queryable_receipts_and_recovers_all_state(self):
        workspace = self.folder / 'workspace'
        before = archive.build(self.save(), workspace)
        self.packet['journey']['coverage']['checks'] = [self.receipt]
        after = archive.build(self.save(), workspace, update=True)
        with closing(sqlite3.connect(workspace / 'career.sqlite')) as db:
            self.assertEqual(db.execute('SELECT month,status,found,records_read FROM coverage_checks WHERE revision=?', (after['revision'],)).fetchone(), ('2025-12', 'checked', 3, 3))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 2)
        exported = self.folder / 'recovered.html'
        archive.export(workspace / 'career.sqlite', exported)
        restored = renderer.load_packet(exported)['journey']
        self.assertEqual(restored.pop('reviewBasis'), renderer.memory.review_basis(self.packet))
        self.assertEqual(restored, self.packet['journey'])
        self.assertNotEqual(before['revision'], after['revision'])

    def test_old_archive_gets_additive_tables_without_losing_revisions(self):
        workspace = self.folder / 'legacy'
        archive.build(self.save(), workspace)
        with closing(sqlite3.connect(workspace / 'career.sqlite')) as db:
            db.execute('DROP TABLE coverage_checks'); db.execute('DROP TABLE coverage_plans')
            db.commit()
        self.packet['journey']['coverage']['checks'] = [self.receipt]
        archive.build(self.save(), workspace, update=True)
        with closing(sqlite3.connect(workspace / 'career.sqlite')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM coverage_checks').fetchone()[0], 1)

    def test_update_cannot_silently_drop_the_collection_plan(self):
        old = copy.deepcopy(self.packet)
        del self.packet['journey']['coverage']
        with self.assertRaisesRegex(ValueError, 'coverage'):
            renderer.preserve_views(old, self.packet)


if __name__ == '__main__': unittest.main()
