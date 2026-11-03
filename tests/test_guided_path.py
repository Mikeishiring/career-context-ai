"""Guided review retains facts, baseline wording and portable private notes."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/career-context-sheet/scripts'
spec = importlib.util.spec_from_file_location('path_renderer', SCRIPTS / 'render_context.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class GuidedPathTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is an optional development check')
    def test_browser_draft_restoration_before_evidence_migration(self):
        result = subprocess.run([shutil.which('node'), str(ROOT / 'tests/check_path_restore.cjs')],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.packet = json.loads((ROOT / 'examples/complete-context.json').read_text(encoding='utf-8'))
        self.basis = renderer.sections.evidence_fingerprint(self.packet)
        self.packet['journey'] = {'contextSha256': self.basis, 'updatedAt': 0, 'current': 'review',
            'completed': [], 'notes': {}, 'storyId': self.packet['accounts'][0]['id'],
            'baseline': {'overview': self.packet['person']['overview'],
                         'accounts': {a['id']: a['summary'] for a in self.packet['accounts']}}}
        self.packet['publicProfile'] = renderer.public_profile.initial_state(self.packet, self.basis)

    def render(self):
        source = self.folder / 'context.json'
        source.write_text(json.dumps(self.packet), encoding='utf-8')
        output = self.folder / 'context.html'
        renderer.render(source, output)
        return output

    def test_path_and_notes_roundtrip_without_changing_facts(self):
        before = copy.deepcopy(self.packet)
        self.packet['journey']['notes']['review:' + self.packet['accounts'][0]['id']] = 'Keep the shared credit.'
        self.packet['journey']['completed'] = ['review']
        output = self.render()
        recovered = renderer.load_packet(output)
        self.assertEqual(recovered['journey'].pop('reviewBasis'), renderer.memory.review_basis(self.packet))
        self.assertEqual(recovered, self.packet)
        self.assertEqual(recovered['accounts'], before['accounts'])
        self.assertEqual(recovered['reviewStatus'], 'draft')
        self.assertEqual(renderer.sections.evidence_fingerprint(recovered), self.basis)
        rebuilt = self.folder / 'rebuilt.html'
        renderer.render(output, rebuilt)
        self.assertEqual(output.read_bytes(), rebuilt.read_bytes())

    def test_changing_current_account_preserves_first_draft(self):
        original = self.packet['accounts'][0]['summary']
        self.packet['accounts'][0]['summary'] += ' A supported correction.'
        self.packet['interview']['contextSha256'] = renderer.sections.evidence_fingerprint(self.packet)
        recovered = renderer.load_packet(self.render())
        self.assertEqual(recovered['journey']['baseline']['accounts'][self.packet['accounts'][0]['id']], original)
        self.assertNotEqual(recovered['journey']['contextSha256'], renderer.sections.evidence_fingerprint(recovered))

    def test_rejects_foreign_notes_and_invalid_state(self):
        for field, bad in [('current', 'invented'), ('completed', ['review', 'review']),
                           ('storyId', 'someone-else'), ('notes', {'review:missing': 'x'}),
                           ('updatedAt', True), ('updatedAt', 9007199254740992)]:
            packet = copy.deepcopy(self.packet)
            packet['journey'][field] = bad
            with self.subTest(field=field, value=bad), self.assertRaises(ValueError):
                renderer.validate(packet)

    def test_notes_and_baseline_remain_inert(self):
        payload = '</script><img src=x onerror=alert(1)>'
        self.packet['journey']['notes']['connect'] = payload
        self.packet['journey']['baseline']['overview'] = payload
        output = self.render()
        self.assertNotIn(payload, output.read_text(encoding='utf-8'))
        self.assertEqual(renderer.load_packet(output)['journey']['notes']['connect'], payload)

    def test_update_cannot_drop_path_progress(self):
        old = copy.deepcopy(self.packet)
        self.packet.pop('journey')
        with self.assertRaisesRegex(ValueError, 'journey'):
            renderer.preserve_views(old, self.packet)

    def test_opt_in_initializes_once_without_erasing_later_notes(self):
        self.packet.pop('journey')
        source = self.folder / 'input.json'
        source.write_text(json.dumps(self.packet), encoding='utf-8')
        output = self.folder / 'path.html'
        renderer.render(source, output, guided=True)
        saved = renderer.load_packet(output)
        self.assertEqual(saved['journey']['baseline']['overview'], self.packet['person']['overview'])
        # A stale authoring input cannot reset progress by adding --guided again.
        with self.assertRaisesRegex(ValueError, 'journey'):
            renderer.render(source, output, guided=True)
        renderer.render(output, output, guided=True)
        self.assertEqual(renderer.load_packet(output)['journey'], saved['journey'])

    def test_archive_recovers_path_and_notes(self):
        spec = importlib.util.spec_from_file_location('path_archive', SCRIPTS / 'archive_context.py')
        archive = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(archive)
        self.packet['journey']['notes']['connect'] = 'Keep the first account.'
        source = self.render()
        workspace = self.folder / 'archive'
        archive.build(source, workspace)
        recovered = self.folder / 'recovered.html'
        archive.export(workspace / 'career.sqlite', recovered)
        saved = renderer.load_packet(recovered)['journey']
        self.assertEqual(saved.pop('reviewBasis'), renderer.memory.review_basis(self.packet))
        self.assertEqual(saved, self.packet['journey'])

    def test_writing_candidates_and_style_are_private_and_portable(self):
        self.packet['journey']['current'] = 'write'
        self.packet['journey']['writing'] = {'guideName': 'SKILL.md', 'guideText': 'Use short sentences.',
                                            'draft': 'A proposed public overview.'}
        result = renderer.load_packet(self.render())
        self.assertEqual(result['journey']['writing'], self.packet['journey']['writing'])
        self.assertEqual(result['person'], self.packet['person'])
        self.assertEqual(result['publicProfile']['overview'], '')
        self.assertEqual(renderer.sections.evidence_fingerprint(result), self.basis)

    def test_public_projection_never_auto_copies_private_overview(self):
        self.packet.pop('publicProfile')
        result = renderer.load_packet(self.render())
        self.assertEqual(result['publicProfile']['name'], '')
        self.assertEqual(result['publicProfile']['overview'], '')
        self.assertEqual(result['publicProfile']['examples'], [])

    def test_profile_rejects_extra_data_and_unsafe_fields(self):
        for value in [{'sources': self.packet['sources']}, {'overview': 'x' * 3001},
                      {'updatedAt': True}, {'examples': [{'title': 'Test', 'summary': 'Text', 'synthetic': 'yes'}]}]:
            packet = copy.deepcopy(self.packet)
            packet['publicProfile'].update(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                renderer.validate(packet)

    def test_public_timeline_is_authored_bounded_and_escaped(self):
        self.assertEqual(self.packet['publicProfile']['timeline'], [])
        hostile = '<img src=x onerror=alert(1)>'
        self.packet['publicProfile']['timeline'] = [{'period': '2030', 'title': hostile, 'summary': 'Public wording only.', 'included': True}]
        recovered = renderer.load_packet(self.render())
        self.assertEqual(recovered['publicProfile']['timeline'], self.packet['publicProfile']['timeline'])
        preview = renderer.public_profile.preview(recovered['publicProfile'])
        self.assertNotIn(hostile, preview)
        self.assertIn('&lt;img', preview)
        self.assertNotIn(self.packet['timeline'][0]['focus'], preview)
        for change in [{'period': 'x' * 61}, {'summary': 'x' * 1501}, {'sourceRefs': ['private-id']}]:
            data = copy.deepcopy(self.packet)
            data['publicProfile']['timeline'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                renderer.validate(data)
        self.packet['publicProfile']['timeline'] *= 31
        with self.assertRaises(ValueError): renderer.validate(self.packet)

    def test_profile_cannot_disappear_on_update(self):
        previous = copy.deepcopy(self.packet)
        self.packet.pop('publicProfile')
        with self.assertRaisesRegex(ValueError, 'publicProfile'):
            renderer.preserve_views(previous, self.packet)

    def test_profile_without_path_has_working_return_links(self):
        self.packet.pop('journey')
        markup = self.render().read_text(encoding='utf-8')
        self.assertNotIn('href="#path-write"', markup)
        self.assertIn('href="#work">Back to your context', markup)
        self.assertIn('id="public-editor"', markup)


if __name__ == '__main__':
    unittest.main()
