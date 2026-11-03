"""Selected public components stay separate from recoverable private drafts."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sharing_trial', ROOT / 'tools/build_nontechnical_trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
r = trial.renderer


class ProfileSharingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is an optional development check')
    def test_javascript_projection_and_control_handlers(self):
        for script in ['check_public_projection.cjs', 'check_profile_controls.cjs']:
            with self.subTest(script=script):
                result = subprocess.run([shutil.which('node'), str(ROOT / 'tests' / script)],
                                        capture_output=True, text=True, encoding='utf-8', timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def setUp(self):
        self.data = trial.packet()
        self.data.pop('interview')
        self.profile = self.data['publicProfile']
        self.profile.update(headline='Shared routines and practical work', overview='WITHHELD_OVERVIEW', shareOverview=False,
            examples=[{'title':'Paper rota', 'summary':'Neighbours chose days; another neighbour arranged cover.', 'synthetic':False, 'included':True},
                      {'title':'WITHHELD_EXAMPLE', 'summary':'A draft for another audience.', 'synthetic':False, 'included':False}],
            timeline=[{'period':'2024', 'title':'WITHHELD_YEAR', 'summary':'Private draft detail.', 'included':False}])

    def test_preview_only_contains_selected_components(self):
        before = copy.deepcopy(self.data)
        markup = r.public_profile.preview(self.profile)
        self.assertIn('Paper rota', markup)
        self.assertNotIn('WITHHELD_', markup)
        self.assertEqual(self.data, before)
        self.profile['examples'][1]['included'] = True
        self.assertIn('WITHHELD_EXAMPLE', r.public_profile.preview(self.profile))

    def test_private_archive_recovers_withheld_content_and_choices(self):
        spec = importlib.util.spec_from_file_location('sharing_archive', ROOT / 'skills/career-context-sheet/scripts/archive_context.py')
        archive = importlib.util.module_from_spec(spec); spec.loader.exec_module(archive)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'input.json'; source.write_text(json.dumps(self.data), encoding='utf8')
            page = folder / 'context.html'; r.render(source, page, guided=True)
            archive.build(page, folder / 'archive')
            recovered = folder / 'recovered.html'; archive.export(folder / 'archive/career.sqlite', recovered)
            packet = r.load_packet(recovered)
            self.assertEqual(packet['publicProfile'], self.profile)
            self.assertEqual(packet['accounts'], self.data['accounts'])
            self.assertNotIn('interview', packet)

    def test_invalid_selection_flags_are_rejected(self):
        for target, key in [(self.profile, 'shareOverview'), (self.profile['examples'][0], 'included'), (self.profile['timeline'][0], 'included')]:
            before = target[key]
            for value in [1, 'false', None]:
                target[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): r.validate(self.data)
            target[key] = before

    def test_legacy_profile_stays_private_without_explicit_sharing_flags(self):
        self.profile.pop('shareOverview')
        for entry in self.profile['examples'] + self.profile['timeline']: entry.pop('included')
        self.data['journey']['current'] = 'practice'
        self.data['journey']['notes']['practice:watering-rota'] = 'Existing note'
        r.validate(self.data)
        before = copy.deepcopy(self.profile)
        self.assertNotIn('WITHHELD_', r.public_profile.preview(self.profile))
        self.assertEqual(r.public_profile.projection(self.profile)['examples'], [])
        self.assertEqual(r.public_profile.projection(self.profile)['timeline'], [])
        self.assertEqual(self.profile, before)
        self.assertNotIn('practice', r.guided_path.CORE_STEPS)

    def test_direction_and_details_need_their_own_selection(self):
        self.profile.update(direction='I want more practical community work.', shareDirection=False)
        example = self.profile['examples'][0]
        example.update(detail='DEEPER_CONTEXT: a neighbour arranged cover.', shareDetail=False)
        self.assertNotIn('DEEPER_CONTEXT', r.public_profile.preview(self.profile))
        self.assertNotIn('I want more', r.public_profile.preview(self.profile))
        example['shareDetail'] = True
        self.profile['shareDirection'] = True
        markup = r.public_profile.preview(self.profile)
        self.assertIn('DEEPER_CONTEXT', markup)
        self.assertIn('I want more', markup)
        example['included'] = False
        self.assertNotIn('DEEPER_CONTEXT', r.public_profile.preview(self.profile))
        self.assertIn('DEEPER_CONTEXT', example['detail'])

    def test_deeper_fields_are_bounded_and_selection_flags_are_boolean(self):
        for patch in [{'direction':'x'*1501}, {'shareDirection':1}]:
            data=copy.deepcopy(self.data); data['publicProfile'].update(patch)
            with self.subTest(patch=list(patch)), self.assertRaises(ValueError): r.validate(data)
        for patch in [{'detail':'x'*2501}, {'shareDetail':'yes'}]:
            data=copy.deepcopy(self.data); data['publicProfile']['examples'][0].update(patch)
            with self.subTest(patch=list(patch)), self.assertRaises(ValueError): r.validate(data)
