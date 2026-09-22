"""Unit tests and real FFmpeg integration tests. No API keys or source fixtures."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/autoedit-agent/scripts'))
import autoedit as ae


def blueprint():
    return {'schema_version': '2.0', 'project': {'name': '测试 project', 'width': 320, 'height': 240, 'fps': 30},
            'clips': [{'id': 'v1', 'media_type': 'video', 'source_path': 'camera.mov',
                       'source_in_seconds': 1, 'source_out_seconds': 2,
                       'timeline_in_seconds': 0, 'timeline_out_seconds': 1}],
            'captions': [{'start_seconds': 0.1, 'end_seconds': 0.8, 'text': 'A test 字幕'}]}


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / 'blueprint.json'
        self.data = blueprint()

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, data=None, check_media=False):
        self.path.write_text(json.dumps(data or self.data), encoding='utf-8')
        return ae.load_blueprint(self.path, check_media=check_media)[0]

    def test_relative_path_resolves_from_blueprint(self):
        data = self.load()
        self.assertEqual(data['clips'][0]['source_path'], str(self.root/'camera.mov'))

    def test_nan_rejected(self):
        self.data['clips'][0]['timeline_out_seconds'] = math.nan
        with self.assertRaises(ValueError): self.load()

    def test_bool_is_not_time(self):
        self.data['clips'][0]['source_in_seconds'] = True
        with self.assertRaises(ValueError): self.load()

    def test_speed_and_duration_must_match(self):
        self.data['clips'][0]['speed'] = 2
        with self.assertRaises(ValueError): self.load()

    def test_frame_alignment(self):
        self.data['clips'][0].update(timeline_out_seconds=1.01, source_out_seconds=2.01)
        with self.assertRaises(ValueError): self.load()

    def test_gap_rejected(self):
        self.data['clips'][0].update(timeline_in_seconds=.1, timeline_out_seconds=1.1)
        with self.assertRaises(ValueError): self.load()

    def test_overlap_rejected(self):
        second = dict(self.data['clips'][0], id='v2', timeline_in_seconds=.5, timeline_out_seconds=1.5)
        self.data['clips'].append(second)
        with self.assertRaises(ValueError): self.load()

    def test_duplicates_rejected(self):
        self.data['clips'].append(copy.deepcopy(self.data['clips'][0]))
        with self.assertRaises(ValueError): self.load()

    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError): self.load(check_media=True)

    def test_source_out_of_bounds(self):
        (self.root/'camera.mov').touch()
        with patch.object(ae, 'probe', return_value={'streams':[{'index':0,'codec_type':'video','duration':'1.5'}]}):
            with self.assertRaises(ValueError): self.load(check_media=True)

    def test_unknown_fields_not_silently_lost(self):
        self.data['clips'][0]['transition'] = 'dissolve'
        with self.assertRaises(ValueError): self.load()

    def test_remote_path_rejected(self):
        self.data['clips'][0]['source_path'] = 'https://example.com/a.mp4'
        with self.assertRaises(ValueError): self.load()

    def test_audio_may_not_extend_timeline(self):
        self.data['clips'].append(dict(self.data['clips'][0], id='a1', media_type='audio',
            source_path='music.wav', source_out_seconds=3, timeline_out_seconds=2))
        with self.assertRaises(ValueError): self.load()

    def test_caption_overlap_rejected(self):
        self.data['captions'].append({'start_seconds':.5,'end_seconds':.9,'text':'Second'})
        with self.assertRaises(ValueError): self.load()

    def test_image_uses_timeline_duration(self):
        self.data['clips'] = [{'id':'i1','media_type':'image','source_path':'a.jpg',
                              'timeline_in_seconds':0,'timeline_out_seconds':1}]
        self.assertEqual(self.load()['clips'][0]['volume'], 0)

    def test_v1_has_actionable_migration_error(self):
        self.data['schema_version']='1.0'
        with self.assertRaisesRegex(ValueError, 'migration'): self.load()

    def test_audio_filter_retime_and_fades(self):
        c = self.load()['clips'][0]
        c.update(speed=.25, fade_in_seconds=.1, fade_out_seconds=.1)
        text = ae.audio_filter(c)
        self.assertIn('atempo=0.5', text)
        self.assertIn('afade=t=in', text)
        self.assertIn('afade=t=out', text)

    def test_srt(self):
        self.assertIn('00:00:00,100 --> 00:00:00,800', ae.srt_text(self.data['captions']))
        self.assertIn('字幕', ae.srt_text(self.data['captions']))

    def test_no_media_probe_for_schema_only(self):
        with patch.object(ae, 'probe', side_effect=AssertionError('unexpected probe')):
            self.load()


@unittest.skipUnless(ae.doctor('ffmpeg')['ready'], 'FFmpeg + FFprobe required')
class FFmpegTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='autoedit-tests-')
        cls.root = Path(cls.tmp.name)
        # Real sources include Unicode, spaces, apostrophes and nonmatching dimensions/fps.
        cls.video = cls.root / "camera's 测试 clip.mp4"
        ae.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=24',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','3',
                '-c:v','libx264','-threads','2','-c:a','aac',str(cls.video)])
        cls.silent = cls.root/'silent.mp4'
        ae.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=240x320:r=25',
                '-t','2','-c:v','libx264','-threads','2',str(cls.silent)])
        cls.image = cls.root/'photo.png'
        ae.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=320x180',
                '-frames:v','1','-threads','1',str(cls.image)])
        cls.music = cls.root/'music.wav'
        ae.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=220:sample_rate=44100',
                '-t','3',str(cls.music)])
        cls.data = blueprint()
        cls.data['clips'][0]['source_path'] = str(cls.video)
        cls.data['clips'] += [
            {'id':'v2','media_type':'video','source_path':str(cls.silent),
             'source_in_seconds':0,'source_out_seconds':2,'speed':2,
             'timeline_in_seconds':1,'timeline_out_seconds':2,'fit':'crop'},
            {'id':'photo','media_type':'image','source_path':str(cls.image),
             'timeline_in_seconds':2,'timeline_out_seconds':3},
            {'id':'music','media_type':'audio','source_path':str(cls.music),
             'source_in_seconds':.1,'source_out_seconds':2.1,
             'timeline_in_seconds':.5,'timeline_out_seconds':2.5,'volume':.2,
             'fade_in_seconds':.1,'fade_out_seconds':.2}]
        cls.path = cls.root/'blueprint.json'
        cls.path.write_text(json.dumps(cls.data), encoding='utf-8')
        cls.hashes = {p: ae.hashlib.sha256(p.read_bytes()).hexdigest() for p in
                      (cls.video, cls.silent, cls.image, cls.music)}

    def test_extract_samples_real_media_without_modifying_sources(self):
        manifest = self.root/'extract-manifest.json'
        ae.scan([str(self.video), str(self.image)], manifest)
        out = self.root/'extracted-frames'
        result = ae.extract(manifest, out, every=1, maximum=2)
        self.assertEqual(result['frames'], 3)
        rows = json.loads((out/'frames-index.json').read_text())
        self.assertTrue(all(Path(row['image_path']).is_file() and row['ok'] for row in rows))
        times = [row['time_seconds'] for row in rows if row['source_path'] == str(self.video)]
        self.assertEqual(len(times), 2)
        self.assertGreater(max(times), 1.5)
        with self.assertRaises(FileExistsError):
            ae.extract(manifest, out, every=1, maximum=2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_real_render(self):
        out = self.root/'soft-output'
        result = ae.build(self.path, out, 'ffmpeg')
        self.assertEqual(result['status'], 'rendered_and_decode_checked')
        info = ae.probe(out/'final.mp4')
        self.assertEqual(ae.stream(info,'video')['nb_frames'], '90')
        self.assertIsNotNone(ae.stream(info,'subtitle'))
        self.assertAlmostEqual(float(info['format']['duration']), 3, delta=.1)
        for p, digest in self.hashes.items():
            self.assertEqual(ae.hashlib.sha256(p.read_bytes()).hexdigest(), digest)

    def test_burn_captions(self):
        filters = ae.run(['ffmpeg', '-hide_banner', '-filters'])
        if 'subtitles' not in filters: self.skipTest('libass absent')
        result = ae.build(self.path, self.root/'burn-output', 'ffmpeg', burn=True)
        self.assertEqual(result['subtitle_mode'], 'burn')
        self.assertIsNone(ae.stream(ae.probe(self.root/'burn-output/final.mp4'),'subtitle'))

    def test_dry_run_does_not_write(self):
        before = sorted(p.name for p in self.root.iterdir())
        result = ae.build(self.path, self.root/'not-created', 'auto', dry_run=True)
        self.assertEqual(result['backend'],'ffmpeg')
        self.assertEqual(before, sorted(p.name for p in self.root.iterdir()))

    def test_no_overwrite(self):
        out = self.root/'existing'
        out.mkdir()
        (out/'owned.txt').write_text('keep')
        with self.assertRaises(ValueError): ae.build(self.path, out, 'ffmpeg')
        self.assertEqual((out/'owned.txt').read_text(),'keep')

    def test_source_directory_is_protected(self):
        with self.assertRaises(ValueError): ae.build(self.path, self.root, 'ffmpeg')

    def test_failure_report(self):
        with patch.object(ae, 'ffmpeg_build', side_effect=ValueError('synthetic render failure')):
            with self.assertRaises(ValueError): ae.build(self.path, self.root/'failed', 'ffmpeg')
        self.assertTrue((self.root/'failed/FAILED.json').exists())
        self.assertFalse((self.root/'failed/final.mp4').exists())

    def test_jianying_missing_never_falls_back(self):
        data = copy.deepcopy(self.data)
        data['clips'][1]['fit']='pad'
        path = self.root/'jy.json'
        path.write_text(json.dumps(data))
        with patch.object(ae, 'doctor', return_value={'ready':False}):
            with self.assertRaises(ValueError): ae.build(path, self.root/'no-jy', 'jianying')
        self.assertFalse((self.root/'no-jy').exists())

    def test_jianying_rejects_unsupported_crop_before_write(self):
        with self.assertRaisesRegex(ValueError, 'fit=pad'):
            ae.build(self.path, self.root/'jy-crop', 'jianying')
        self.assertFalse((self.root/'jy-crop').exists())

    def test_scan(self):
        result = ae.scan([str(self.video), str(self.silent)], self.root/'manifest.json')
        self.assertEqual(result['files'], 2)
        self.assertEqual(result['errors'],0)

    @unittest.skipUnless(importlib.util.find_spec('pyJianYingDraft'), 'Optional pyJianYingDraft not installed')
    def test_real_jianying_draft(self):
        data = copy.deepcopy(self.data)
        data['clips'][1]['fit']='pad'
        path = self.root/'jy-real.json'
        path.write_text(json.dumps(data))
        result = ae.build(path, self.root/'jy-real', 'jianying')
        self.assertEqual(result['status'],'draft_written_not_editor_verified')
        saved = json.loads((Path(result['draft_directory'])/'draft_content.json').read_text())
        self.assertEqual(saved['duration'], 3000000)
        self.assertEqual(len([s for t in saved['tracks'] for s in t['segments']]), 5)


if __name__ == '__main__':
    unittest.main()
