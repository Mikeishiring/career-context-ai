"""Exercise actual video decoding and bounded frame/provenance output."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('video_samples', ROOT / 'skills/career-context-sheet/scripts/sample_video.py')
video = importlib.util.module_from_spec(spec); spec.loader.exec_module(video)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Optional FFmpeg tools are not installed')
class VideoEvidenceTests(unittest.TestCase):
    def test_sampling_preserves_source_and_records_exact_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'synthetic.mp4'
            subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                'testsrc2=duration=2:size=160x120:rate=10', '-c:v', 'mpeg4', str(source)], check=True, capture_output=True)
            original = source.read_bytes()
            result = video.sample(source, root / 'frames', times=[0.2, 1.6])
            self.assertEqual(result['sourceSha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual([x['seconds'] for x in result['candidates']], [0.2, 1.6])
            self.assertNotEqual(result['candidates'][0]['sha256'], result['candidates'][1]['sha256'])
            for record in result['candidates']:
                self.assertTrue((root / 'frames' / record['file']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
            with self.assertRaises(ValueError): video.sample(source, root / 'frames', times=[0.2, 1.6])
            for stamps in [[-1], [9], [float('nan')], [0.1, 0.1]]:
                with self.subTest(stamps=stamps), self.assertRaises(ValueError): video.sample(source, root / 'other', times=stamps)
