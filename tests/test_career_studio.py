"""Output discovery must not invent evidence or change sharing selection."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('studio_renderer', ROOT/'skills/career-context-sheet/scripts/render_context.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
studio = r.load_helper('career_studio')


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads((ROOT/'examples/complete-context.json').read_text(encoding='utf-8'))
        self.packet['journey'] = r.guided_path.initial_state(self.packet, r.sections.evidence_fingerprint(self.packet))

    def test_projection_uses_actual_artifacts_without_mutation(self):
        account = self.packet['accounts'][0]
        account['artifacts'] = [{'id':'sample','title':'Prototype <not shipped>','caption':'Historical capture','embeddedId':'artifact-sample'}]
        before = copy.deepcopy(self.packet)
        rendered = studio.render(self.packet)
        self.assertIn('data-studio-image="artifact-sample"', rendered)
        self.assertIn('Prototype &lt;not shipped&gt;', rendered)
        self.assertEqual(self.packet, before)

    def test_no_fabricated_visuals_or_empty_gallery(self):
        for a in self.packet['accounts']: a.pop('artifacts', None)
        rendered = studio.render(self.packet)
        self.assertNotIn('<img', rendered)
        self.assertNotIn('id="studio-examples-title"', rendered)

    def test_reviewed_artifact_destination_is_visible_and_private(self):
        account = self.packet['accounts'][0]
        account['artifacts'] = [{'id':'demo','title':'Actual input','caption':'Synthetic input, observed result',
                                 'embeddedId':'artifact-demo','link':{'label':'Try prototype','url':'https://example.com/demo'}}]
        original_basis = r.sections.evidence_fingerprint(self.packet)
        r.validate(self.packet)
        rendered = studio.render(self.packet)
        self.assertIn('href="https://example.com/demo"', rendered)
        self.assertIn('Try prototype', rendered)
        self.assertIn('rel="noopener noreferrer"', rendered)
        account['artifacts'][0]['link']['url'] = 'https://example.com/revised'
        self.assertEqual(original_basis, r.sections.evidence_fingerprint(self.packet))
        # Public projection is separately authored; private destinations never enter it.
        self.assertNotIn('https://example.com', json.dumps(self.packet.get('publicProfile', {})))

    def test_artifact_link_rejects_script_credentials_and_access_tokens(self):
        self.packet['accounts'][0]['artifacts'] = [{'id':'demo','title':'Actual input','caption':'Test',
                                                  'link':{'label':'Try prototype','url':''}}]
        for url in ['javascript:alert(1)', 'http://example.com', 'https://user:secret@' + 'example.com',
                    'https://example.com/?token=secret', 'https://example.com/#access_token=secret',
                    'https://example.com/\nsecret']:
            with self.subTest(url=url):
                self.packet['accounts'][0]['artifacts'][0]['link']['url'] = url
                with self.assertRaises(ValueError): r.validate(self.packet)

    def test_output_note_is_saved_authored_work(self):
        old = r.guided_path.review_fingerprint(self.packet)
        self.packet['journey']['notes']['output'] = 'Requested output: a resume draft. Use account alpha.'
        r.validate(self.packet)
        self.assertNotEqual(old, r.guided_path.review_fingerprint(self.packet))

    def test_no_dead_actions_without_guided_path(self):
        del self.packet['journey']
        rendered = studio.render(self.packet)
        self.assertNotIn('data-studio-kind', rendered)
        self.assertNotIn('href="#path', rendered)

    def test_personal_view_is_private_review_input_and_changes_story_selection(self):
        packet = self.packet
        key = packet['accounts'][-1]['id']
        basis = r.sections.evidence_fingerprint(packet)
        original = r.guided_path.review_fingerprint(packet)
        review = dict(decision='pending', draft='', reason='', sourceRefs=[], depth='pending', practised=False)
        packet['journey']['reviews'][key] = review
        self.assertEqual(original, r.guided_path.review_fingerprint(packet))
        review.update(importance='minor', emphasis='over', interest='lead', missingContext='I enjoyed making the prototype.')
        packet['journey']['notes']['missingWork'] = 'A separate handover project.'
        r.validate(packet)
        self.assertEqual(basis, r.sections.evidence_fingerprint(packet))
        self.assertNotEqual(original, r.guided_path.review_fingerprint(packet))
        self.assertEqual(r.load_helper('agent_context').account_bundle(packet,key)['review'], review)
        self.assertEqual(r.load_helper('agent_context').briefing(packet)['missingWork'], 'A separate handover project.')
        self.assertNotIn('missingContext', json.dumps(r.load_helper('context_selection').select(packet,[key])))
        profile = r.public_profile.initial_state(packet, basis)
        self.assertNotIn('separate handover', json.dumps(r.public_profile.projection(profile)))
        packet['interview']['stories'] = [s for s in packet['interview']['stories'] if s['id'] != key]
        shortlist = studio.render(packet).split('id="studio-stories"',1)[1].split('</section>',1)[0]
        self.assertIn('#prep-story-'+key, shortlist.split('</li>',1)[0])
        review['interest'] = 'reserve'
        self.assertNotIn('#prep-story-'+key, studio.render(packet))
        review['emphasis'] = 'verified'
        with self.assertRaises(ValueError):
            r.guided_path.validate(packet,r.check_text,r.keys)

    def test_database_does_not_appear_as_prepared_draft(self):
        self.packet['presentation'] = {'files':[{'label':'Resume','path':'RESUME.html'},{'label':'Database','path':'career.sqlite'}]}
        rendered = studio.render(self.packet)
        self.assertIn('href="RESUME.html"', rendered)
        self.assertNotIn('href="career.sqlite"', rendered)


if __name__ == '__main__': unittest.main()
