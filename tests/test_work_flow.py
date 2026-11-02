"""Nontechnical work, complete routes, grouping and recoverable evidence."""
import copy
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nontechnical_trial', ROOT/'tools/build_nontechnical_trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)
r = trial.renderer


class Document(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=set(); self.practice=[]; self.preparation=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a: self.ids.add(a['id'])
        if tag=='a' and a.get('class')=='account-practice': self.practice.append(a['href'][1:])
        if tag=='button' and 'data-prepare-story' in a: self.preparation.append(a['data-prepare-story'])


class WorkFlowTests(unittest.TestCase):
    def setUp(self):
        self.packet=trial.packet()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)

    def render(self):
        source=self.folder/'context.json';output=self.folder/'context.html'
        source.write_text(json.dumps(self.packet),encoding='utf8')
        r.render(source,output,guided=True)
        return output

    def test_nontechnical_records_and_all_practice_routes_survive(self):
        output=self.render();data=r.load_packet(output);dom=Document();dom.feed(output.read_text(encoding='utf8'))
        self.assertEqual(data['accounts'],self.packet['accounts'])
        self.assertEqual(data['sources'],self.packet['sources'])
        self.assertEqual(len(dom.practice),4)
        self.assertTrue(set(dom.practice)<=dom.ids)
        self.assertEqual(set(dom.preparation),{'chair-repair','display-sketch','personal-background'})
        self.assertIsNone(data['interview']['target'])
        self.assertEqual(data['publicProfile']['overview'],'')
        self.assertEqual(data['publicProfile']['examples'],[])
        self.assertEqual(data['journey']['writing']['mode'],'own_skill')
        self.assertFalse(any(a.get('capabilities') for a in data['accounts']))

    def test_no_prepared_stories_still_has_a_real_continuation(self):
        self.packet.pop('interview')
        output=self.render();dom=Document();dom.feed(output.read_text(encoding='utf8'))
        self.assertEqual(set(dom.preparation),{a['id'] for a in self.packet['accounts']})
        self.assertNotIn('interview',r.load_packet(output))

    def test_grouping_rejects_loss_duplication_and_unknown_accounts(self):
        original=copy.deepcopy(self.packet['presentation']['workGroups'])
        for change in ['missing','duplicate','unknown','kind']:
            projection=copy.deepcopy(original)
            if change=='missing':projection['groups'].pop()
            elif change=='duplicate':projection['groups'][1]['accountIds'].append('watering-rota')
            elif change=='unknown':projection['groups'][0]['accountIds']=['unknown']
            else:projection['groups'][0]['kind']='role'
            self.packet['presentation']['workGroups']=projection
            with self.subTest(change=change),self.assertRaises(ValueError):r.validate(self.packet)

    def test_stale_groups_do_not_hide_or_reclassify_work(self):
        self.packet['presentation']['workGroups']['contextSha256']='0'*64
        output=self.render();data=r.load_packet(output)
        self.assertEqual(r.sections.work_groups(data),[])
        self.assertEqual(data['accounts'],self.packet['accounts'])
        self.assertNotIn('class="work-group"',output.read_text(encoding='utf8'))

    def test_complete_document_and_archive_roundtrip(self):
        output=self.render();rebuilt=self.folder/'rebuilt.html'
        r.render(output,rebuilt)
        self.assertEqual(output.read_bytes(),rebuilt.read_bytes())
        archive=r.load_helper('archive_context')
        result=archive.build(output,self.folder/'archive')
        recovered=self.folder/'recovered.html';archive.export(Path(result['database']),recovered)
        self.assertEqual(r.load_packet(recovered),r.load_packet(output))
