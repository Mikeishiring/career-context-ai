import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('explore_renderer',ROOT/'skills/career-context-sheet/scripts/render_context.py')
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)

class TimelineExplorerTests(unittest.TestCase):
    def setUp(self):
        self.packet=json.loads((ROOT/'examples/complete-context.json').read_text())
        self.basis=renderer.sections.evidence_fingerprint(self.packet)
        self.selection={'contextSha256':self.basis,'updatedAt':1,'fromId':self.packet['timeline'][0]['id'],'toId':self.packet['timeline'][-1]['id'],'purpose':'patterns'}
        self.packet.setdefault('presentation',{})['timelineSelection']=self.selection

    def test_selection_roundtrip_and_source_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'context.json';output=Path(folder)/'context.html'
            source.write_text(json.dumps(self.packet));renderer.render(source,output)
            saved=renderer.load_packet(output);html=output.read_text(encoding='utf-8')
            self.assertEqual(saved['presentation']['timelineSelection'],self.selection)
            self.assertEqual(renderer.sections.evidence_fingerprint(saved),self.basis)
            for marker in ['timeline-year','timeline-from','timeline-to','Copy prompt','source-search','source-kind','source-scope','source-used-by','sources document-view']:
                self.assertIn(marker,html)
            self.assertIn('data-evidence="'+self.basis+'"',html)
            self.assertEqual(saved['sources'],self.packet['sources'])

    def test_invalid_selection_rejected(self):
        for change in [{'fromId':'missing'},{'purpose':'fake'},{'updatedAt':True},{'updatedAt':-1},{'contextSha256':'wrong'},{'fromId':self.selection['toId'],'toId':self.selection['fromId']}]:
            data=copy.deepcopy(self.packet);data['presentation']['timelineSelection'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):renderer.validate(data)

    def test_empty_timeline_has_no_dead_range_controls(self):
        data=copy.deepcopy(self.packet);data.pop('timeline');data['presentation'].pop('timelineSelection')
        rendered=renderer.sections.timeline_html(data)
        self.assertIn('No dated career timeline',rendered)
        self.assertNotIn('timeline-copy',rendered)

    def test_reading_retains_evidence_and_ignores_stale_projection(self):
        period=self.packet['timeline'][0]
        extra=next(a['id'] for a in self.packet['accounts'] if a['id'] not in period['accountIds'])
        reading={'contextSha256':self.basis,'years':{'2030':{'title':'Year reading','bullets':['Year limit.']}},'periods':{period['id']:{'title':'Short reading','bullets':['Reading limit.'],'accountIds':[extra]}}}
        self.packet['presentation']['timelineReading']=reading
        renderer.validate(self.packet)
        rendered=renderer.sections.timeline_html(self.packet)
        self.assertIn('Full period record',rendered)
        self.assertIn('Short reading',rendered)
        self.assertIn('data-overview-year="2030"',rendered)
        self.assertIn('href="#account-'+extra+'"',rendered.split('id="quarter-'+period['id']+'"')[1].split('class="quarter-reading"')[0])
        self.assertEqual(renderer.sections.evidence_fingerprint(self.packet),self.basis)
        reading['contextSha256']='0'*64
        rendered=renderer.sections.timeline_html(self.packet)
        self.assertNotIn('Short reading',rendered)
        self.assertNotIn('Year reading',rendered)
        self.packet.pop('timeline')
        self.packet.pop('interview')
        self.packet['presentation'].pop('timelineSelection')
        renderer.validate(self.packet)
        self.assertEqual(renderer.sections.timeline_reading(self.packet),{})

    def test_reading_rejects_unknown_links_and_unbounded_copy(self):
        key=self.packet['timeline'][0]['id']
        valid={'title':'A title','bullets':['A supported point.'],'accountIds':[]}
        for change in [{'accountIds':['missing']},{'accountIds':[1]},{'title':' '},{'bullets':['x']*4},{'bullets':['x'*601]}]:
            data=copy.deepcopy(self.packet)
            data['presentation']['timelineReading']={'contextSha256':self.basis,'periods':{key:{**valid,**change}},'years':{}}
            with self.subTest(change=change),self.assertRaises(ValueError):renderer.validate(data)
