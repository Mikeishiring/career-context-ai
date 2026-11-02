"""Reading projections cannot silently replace or outlive their evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('brief_renderer', ROOT / 'skills/career-context-sheet/scripts/render_context.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class WorkBriefTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads((ROOT / 'examples/complete-context.json').read_text(encoding='utf-8'))
        self.basis = renderer.sections.evidence_fingerprint(self.packet)
        self.account = self.packet['accounts'][0]
        self.packet.setdefault('presentation', {})['briefs'] = {
            'contextSha256': self.basis, 'accounts': {self.account['id']: ['A short reading aid.', 'The measured limit remains.']}}

    def render(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'context.json', Path(folder) / 'context.html'
            source.write_text(json.dumps(self.packet), encoding='utf-8')
            renderer.render(source, output, guided=True)
            return output.read_text(encoding='utf-8'), renderer.load_packet(output)

    def test_brief_preserves_original_and_roundtrips(self):
        html, recovered = self.render()
        self.assertIn('class="account-brief"', html)
        self.assertIn('Full account &amp; evidence', html)
        self.assertIn('Original account', html)
        self.assertEqual(recovered['accounts'], self.packet['accounts'])
        self.assertEqual(recovered['presentation']['briefs'], self.packet['presentation']['briefs'])
        self.assertEqual(renderer.sections.evidence_fingerprint(recovered), self.basis)

    def test_stale_briefs_fall_back_to_original(self):
        self.packet['presentation']['briefs']['contextSha256'] = '0' * 64
        html, recovered = self.render()
        self.assertNotIn('class="account-brief"', html)
        self.assertEqual(recovered['accounts'][0]['summary'], self.account['summary'])

    def test_invalid_briefs_rejected(self):
        for accounts in [{'missing': ['x']}, {self.account['id']: []}, {self.account['id']: [' ']}, {self.account['id']: ['x'] * 5}, {self.account['id']: ['x' * 601]}]:
            packet = copy.deepcopy(self.packet)
            packet['presentation']['briefs']['accounts'] = accounts
            with self.subTest(accounts=accounts), self.assertRaises(ValueError): renderer.validate(packet)

    def test_briefs_are_inert_and_private(self):
        payload = '<img src=x onerror=alert(1)>PRIVATE_BRIEF_CANARY'
        self.packet['presentation']['briefs']['accounts'][self.account['id']] = [payload]
        html, recovered = self.render()
        self.assertNotIn(payload, html)
        self.assertEqual(recovered['presentation']['briefs']['accounts'][self.account['id']], [payload])

    def test_writing_preference_validation(self):
        self.packet['journey'] = renderer.guided_path.initial_state(self.packet, self.basis)
        self.packet['journey']['writing'] = {'mode': 'own_skill', 'guideName': '', 'guideText': '', 'draft': ''}
        renderer.validate(self.packet)
        _, recovered = self.render()
        self.assertEqual(recovered['journey']['writing']['mode'], 'own_skill')
        self.packet['journey']['writing']['mode'] = 'unrecognised'
        with self.assertRaises(ValueError): renderer.validate(self.packet)
