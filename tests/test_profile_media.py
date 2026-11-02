"""Public media selection, unsafe-link rejection and recoverable private drafts."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('media_trial', ROOT/'tools/build_nontechnical_trial.py')
trial = importlib.util.module_from_spec(spec); spec.loader.exec_module(trial)
r = trial.renderer


def png(color):
    def chunk(kind, body):
        return struct.pack('!I', len(body))+kind+body+struct.pack('!I', zlib.crc32(kind+body)&0xffffffff)
    raw = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(b'\0'+bytes(color)))+chunk(b'IEND', b'')
    return 'data:image/png;base64,'+base64.b64encode(raw).decode()


class ProfileMediaTests(unittest.TestCase):
    def setUp(self):
        self.packet = trial.packet(); self.p = self.packet['publicProfile']
        self.p.update(headline='Practical community work', northStar='Keep shared responsibilities clear.', shareNorthStar=True,
            media=[dict(id='picture', kind='image', title='Paper rota', caption='Synthetic reconstruction, not an original work record.', credit='Fictional demonstration', alt='Days and shared watering responsibilities', dataUrl=png((30,80,40)), included=True),
                   dict(id='withheld', kind='image', title='WITHHELD_IMAGE_TITLE', caption='WITHHELD_CAPTION', credit='', alt='Withheld screenshot', dataUrl=png((80,30,40)), included=False),
                   dict(id='clip', kind='video', title='Demonstration', caption='', credit='A collaborator recorded the demonstration.', url='https://example.org/watch?t=12', included=True),
                   dict(id='private-link', kind='video', title='WITHHELD_VIDEO', caption='', credit='', url='https://example.org/PRIVATE_URL', included=False)])

    def test_selected_media_only_and_no_private_metadata(self):
        r.validate(self.packet)
        visible=r.public_profile.projection(self.p)
        self.assertEqual(len(visible['media']),2)
        self.assertNotIn('id',visible['media'][0]);self.assertNotIn('included',visible['media'][0])
        markup=r.public_profile.preview(self.p)
        self.assertIn(self.p['media'][0]['dataUrl'],markup)
        self.assertNotIn(self.p['media'][1]['dataUrl'],markup)
        self.assertNotIn('WITHHELD',markup);self.assertNotIn('PRIVATE_URL',markup)
        self.assertIn('Keep shared responsibilities clear.',markup)
        self.assertIn('https://example.org/watch?t=12',markup)
        self.assertNotIn('<iframe',markup)
        self.p['shareNorthStar']=False;self.p['media'][0]['included']=False
        self.assertNotIn('Keep shared responsibilities clear.',r.public_profile.preview(self.p))
        self.assertNotIn(self.p['media'][0]['dataUrl'],r.public_profile.preview(self.p))

    def test_invalid_media_fails_closed_but_incomplete_private_link_survives(self):
        for url in ['javascript:alert(1)','http://example.org/video','https://user:pass'+'@'+'example.org/video','https://example.org/\nvideo','https://example.org\\@evil.test']:
            data=copy.deepcopy(self.packet);data['publicProfile']['media'][2]['url']=url
            with self.subTest(url=url), self.assertRaises(ValueError):r.validate(data)
            self.assertNotIn(url,r.public_profile.preview(data['publicProfile']))
        self.p['media'][2].update(url='unfinished draft',included=False);r.validate(self.packet)
        for data_url in ['data:image/svg+xml;base64,PHN2Zz4=', 'https://example.org/private.png','data:image/png;base64,YWJjZA==']:
            data=copy.deepcopy(self.packet);data['publicProfile']['media'][0]['dataUrl']=data_url
            with self.subTest(image=data_url),self.assertRaises(ValueError):r.validate(data)

    def test_full_html_and_archive_recover_withheld_images_and_links(self):
        spec=importlib.util.spec_from_file_location('media_archive',ROOT/'skills/career-context-sheet/scripts/archive_context.py')
        archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.json';source.write_text(json.dumps(self.packet),encoding='utf8')
            page=root/'context.html';r.render(source,page,guided=True)
            archive.build(page,root/'archive');out=root/'recovered.html';archive.export(root/'archive/career.sqlite',out)
            self.assertEqual(r.load_packet(out)['publicProfile'],self.p)
            self.assertEqual(page.read_bytes(),out.read_bytes())

    def test_media_bounds_and_selection_types(self):
        for change in [dict(included='yes'),dict(id='bad id'),dict(title='x'*201)]:
            data=copy.deepcopy(self.packet);data['publicProfile']['media'][0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):r.validate(data)
        self.p['media']*=3
        with self.assertRaises(ValueError):r.validate(self.packet)
