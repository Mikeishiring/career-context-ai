"""Cold start and continuation preserve private evidence and never imply permission."""
import copy
import importlib.util
import json
import re
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('starter_tests', ROOT / 'skills/career-context-sheet/scripts/start_context.py')
starter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(starter)
renderer = starter.renderer


class StartContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_new_archive_is_empty_private_and_existing_work_is_never_reset(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden')):
            result = starter.start(self.folder / 'career', 'Contributor 01', 'Understand one piece of work')
        path = Path(result['path'])
        packet = renderer.load_packet(path)
        self.assertEqual(packet['accounts'], [])
        self.assertEqual(packet['sources'], [])
        self.assertEqual(packet['reviewStatus'], 'draft')
        self.assertEqual(packet['publicProfile']['overview'], '')
        self.assertEqual(packet['journey']['continuation']['goal'], 'Understand one piece of work')
        self.assertEqual(packet['journey']['current'], 'gather')
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'not empty'):
            starter.start(path.parent, 'Contributor 02')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual({p.name for p in path.parent.iterdir()}, {'CAREER-CONTEXT.html', 'career.sqlite'})

    def test_inspection_is_read_only_and_reports_stale_continuation_without_refreshing(self):
        result = starter.start(self.folder / 'career', 'Contributor 01')
        source = Path(result['path'])
        packet = renderer.load_packet(source)
        packet['person']['overview'] = 'New supplied context.'
        changed = self.folder / 'changed.json'
        changed.write_text(json.dumps(packet), encoding='utf-8')
        for file in [source, Path(result['database']), changed]:
            before = file.read_bytes()
            with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden')):
                report = starter.inspect_runtime(file)
            self.assertEqual(before, file.read_bytes())
            self.assertFalse(report['permissionsGranted'])
            self.assertEqual(report['context']['continuationCurrent'], file != changed)
            self.assertTrue(report['localRuntime']['sqlite'])
            self.assertFalse(report['semantic']['checked'])
            self.assertIn('hostChecksRequired', report)

    def test_plain_correction_needs_no_source_ids_but_never_changes_facts(self):
        packet = json.loads((ROOT / 'examples/complete-context.json').read_text(encoding='utf-8'))
        before = copy.deepcopy(packet)
        basis = renderer.sections.evidence_fingerprint(packet)
        packet['journey'] = renderer.guided_path.initial_state(packet, basis)
        key = packet['accounts'][0]['id']
        packet['journey']['reviews'][key] = {'decision': 'correction', 'draft': '', 'reason': 'I tested it; my colleague wrote it.',
                                            'sourceRefs': [], 'depth': 'open', 'practised': False}
        renderer.validate(packet)
        self.assertEqual(packet['accounts'], before['accounts'])
        self.assertEqual(packet['sources'], before['sources'])
        self.assertEqual(renderer.sections.evidence_fingerprint(packet), basis)
        packet['journey']['reviews'][key]['decision'] = 'revision'
        with self.assertRaisesRegex(ValueError, 'chosen revision'):
            renderer.validate(packet)
        packet['journey']['reviews'][key].update(decision='correction', reason='')
        with self.assertRaisesRegex(ValueError, 'reason'):
            renderer.validate(packet)

    def test_continuation_schema_and_preservation_fail_closed(self):
        result = starter.start(self.folder / 'career', 'Contributor 01')
        packet = renderer.load_packet(Path(result['path']))
        for field, value in [('contextSha256', 'bad'), ('goal', 'x' * 3001), ('questions', ['x'] * 13),
                              ('questions', ['x' * 1001]), ('scopeNotes', None), ('allowUpload', True)]:
            candidate = copy.deepcopy(packet)
            candidate['journey']['continuation'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                renderer.validate(candidate)
        missing = copy.deepcopy(packet)
        missing['journey'].pop('continuation')
        with self.assertRaisesRegex(ValueError, 'continuation'):
            renderer.preserve_views(packet, missing)

    def test_private_continuation_is_not_selected_context_or_public_html(self):
        packet = json.loads((ROOT / 'examples/complete-context.json').read_text(encoding='utf-8'))
        basis = renderer.sections.evidence_fingerprint(packet)
        packet['journey'] = renderer.guided_path.initial_state(packet, basis)
        packet['journey']['continuation'] = {'contextSha256': basis, 'goal': 'PRIVATE_CONTINUATION_CANARY',
                                            'nextAction': 'Follow the selected evidence', 'questions': [], 'scopeNotes': 'Private scope'}
        packet['publicProfile'] = renderer.public_profile.initial_state(packet, basis)
        renderer.validate(packet)
        selected = renderer.load_helper('context_selection').select(packet, [packet['accounts'][0]['id']])
        self.assertNotIn('PRIVATE_CONTINUATION_CANARY', json.dumps(selected))
        self.assertNotIn('PRIVATE_CONTINUATION_CANARY', renderer.public_profile.preview(packet['publicProfile']))
        source = self.folder / 'input.json'
        source.write_text(json.dumps(packet), encoding='utf-8')
        archive = renderer.load_helper('archive_context')
        result = archive.build(source, self.folder / 'archive')
        restored = archive.load_snapshot(Path(result['database']))
        self.assertEqual(restored['journey']['continuation'], packet['journey']['continuation'])

    def test_saved_notebook_requires_reconciliation_instead_of_hiding_edits(self):
        notebook = ROOT / 'examples/CAREER-NOTEBOOK.html'
        before = notebook.read_bytes()
        with self.assertRaisesRegex(ValueError, 'merge_notebook'):
            starter.inspect_runtime(notebook)
        self.assertEqual(before, notebook.read_bytes())

    def test_copied_continuation_rejects_missing_or_wrong_saved_version(self):
        result = starter.start(self.folder / 'career', 'Contributor 01')
        source = Path(result['path'])
        context = starter.inspect_runtime(source)['context']
        starter.inspect_runtime(source, expected_context=context['contextSha256'], expected_session=context['journeyUpdatedAt'])
        before = source.read_bytes()
        with self.assertRaisesRegex(ValueError, 'does not match'):
            starter.inspect_runtime(source, expected_session=context['journeyUpdatedAt'] + 1)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            starter.inspect_runtime(source, expected_context='0' * 64)
        with self.assertRaisesRegex(ValueError, 'Select the saved input'):
            starter.inspect_runtime(expected_session=0)
        self.assertEqual(source.read_bytes(), before)

    def test_single_file_handoff_checks_itself_without_copied_brief(self):
        result = starter.start(self.folder / 'career', 'Contributor 01')
        source = Path(result['path'])
        self.assertEqual(starter.inspect_runtime(source)['context']['handoff'], {'present': True, 'matched': True})
        raw = source.read_text(encoding='utf-8')
        pattern = r'(<script id="career-resume-data" type="application/json">)(.*?)(</script>)'
        original = re.search(pattern, raw, re.S)
        self.assertIsNotNone(original)
        for mutation in ['version', 'duplicate', 'malformed']:
            changed = self.folder / (mutation + '.html')
            metadata = json.loads(original[2])
            metadata['journeyUpdatedAt'] += 1
            replacement = original[1] + json.dumps(metadata) + original[3]
            if mutation == 'duplicate':
                replacement = original[0] * 2
            elif mutation == 'malformed':
                replacement = original[1] + 'null' + original[3]
            changed.write_text(raw.replace(original[0], replacement), encoding='utf-8')
            before = changed.read_bytes()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                starter.inspect_runtime(changed)
            self.assertEqual(changed.read_bytes(), before)
        legacy = self.folder / 'legacy.html'
        legacy.write_text(raw.replace(original[0], ''), encoding='utf-8')
        self.assertFalse(starter.inspect_runtime(legacy)['context']['handoff']['present'])


if __name__ == '__main__':
    unittest.main()
