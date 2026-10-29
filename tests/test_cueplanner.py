import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cueplanner.analysis import Settings, analyze
from cueplanner.score import Score, ScoreError
from cueplanner.mcp_bridge import ScoreMcpClient, BridgeError, verify_live
from fixture import make_score


class TestCueAnalysis(unittest.TestCase):
    def test_long_rest_and_cross_transposition(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'orchestra.mscx'
            original = make_score()
            path.write_bytes(original)
            result = analyze(path)
            self.assertEqual(result['stats']['entries_with_cues'], 1)
            c = result['candidates'][0]
            self.assertEqual(c['target'], 'Clarinet in B♭')
            self.assertEqual((c['rest_from'], c['rest_to'], c['cue_from'], c['cue_to'], c['entry_measure']), (1,11,10,11,12))
            self.assertEqual(c['target_staff_index'], 1)
            self.assertTrue(all(s['risk_flags'] for s in c['sources']))
            self.assertIn('target_instrument_transposition', c['sources'][0]['risk_flags'])
            self.assertEqual(path.read_bytes(), original)

    def test_same_transposition_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'a.mscx'
            path.write_bytes(make_score(transposed=True))
            result = analyze(path, Settings(allow_cross_transposition=False))
            self.assertEqual(result['candidates'], [])

    def test_candidate_ranking_and_complexity_gate(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'a.mscx'
            path.write_bytes(make_score(complex_source=True))
            result = analyze(path)
            self.assertEqual(result['stats']['entries_with_cues'], 1)
            self.assertEqual(result['candidates'][0]['sources'][0]['source'], 'Flute')
            self.assertGreater(result['stats']['skipped']['source_complex_timing_or_chords'], 0)

    def test_multivoice_target_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'a.mscx'
            path.write_bytes(make_score(target_multivoice=True))
            self.assertEqual(analyze(path)['candidates'], [])

    def test_form_marker_warns(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'a.mscx'
            path.write_bytes(make_score(repeat=True))
            c = analyze(path)['candidates'][0]
            self.assertIn('repeat_or_navigation_marking_nearby', c['sources'][0]['risk_flags'])

    def test_zip_with_assets(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'orchestra.mscz'
            with ZipFile(path, 'w') as z:
                z.writestr('score.mscx', make_score())
                z.writestr('Thumbnails/thumbnail.png', b'png')
            self.assertEqual(len(analyze(path)['candidates']), 1)
            with ZipFile(path) as z:
                self.assertEqual(z.read('Thumbnails/thumbnail.png'), b'png')


    def test_mscz_manifest_selects_score_not_style(self):
        # A real MuseScore 4 .mscz lists score_style.mss before score.mscx.
        manifest = ('<?xml version="1.0" encoding="utf-8"?>'
                    '<container><rootfiles>'
                    '<rootfile full-path="score_style.mss"/>'
                    '<rootfile full-path="real_score.mscx"/>'
                    '</rootfiles></container>')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'real.mscz'
            with ZipFile(path, 'w') as z:
                z.writestr('META-INF/container.xml', manifest)
                z.writestr('score_style.mss', '<museScore/>')
                z.writestr('real_score.mscx', make_score())
            self.assertEqual(Score(path).measure_count, 12)
            self.assertEqual(len(analyze(path)['candidates']), 1)

    def test_musescore4_excerpts_and_positional_part_staves(self):
        # Genuine 4.4+ files often leave Part/Staff/@id empty and package
        # dozens of separate Excerpts/*.mscx in the same archive.
        xml = ET.fromstring(make_score())
        for part_staff in xml.findall('./Score/Part/Staff'):
            part_staff.attrib.pop('id', None)
        manifest = ('<container><rootfiles><rootfile full-path="style.mss"/>'
                    '<rootfile full-path="main.mscx"/>'
                    '<rootfile full-path="Excerpts/1/part.mscx"/>'
                    '</rootfiles></container>')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'score.mscz'
            with ZipFile(path,'w') as z:
                z.writestr('META-INF/container.xml',manifest)
                z.writestr('style.mss',b'<style/>')
                z.writestr('Excerpts/1/part.mscx',make_score())
                z.writestr('main.mscx',ET.tostring(xml))
            parsed=Score(path)
            self.assertEqual(len(parsed.part_staves),3)
            self.assertIn('mapped Part/Staff by order',parsed.warnings[0])
            self.assertEqual(len(analyze(path)['candidates']),1)

    def test_musescore3_archive_rejected_before_large_xml_parse(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'old.mscz'
            with ZipFile(path,'w') as z:
                z.writestr('old.mscx',b'<?xml version="1.0"?><museScore version="3.02"/>' )
            with self.assertRaisesRegex(ScoreError,'Save As in MuseScore 4'):
                Score(path)

    def test_multistaff_part_not_spurious_independent_target(self):
        # A piano left hand has many rests while right hand plays; it must not
        # generate an independent long-rest/reentry cue for Piano LH.
        score = ET.fromstring(make_score())
        sc = score.find('Score')
        piano_part = ET.SubElement(sc, 'Part')
        ET.SubElement(piano_part, 'Staff', id='4')
        ET.SubElement(piano_part, 'Staff', id='5')
        ET.SubElement(piano_part, 'trackName').text = 'Piano'
        ET.SubElement(piano_part, 'Instrument')
        for sid in ['4','5']:
            staff = ET.SubElement(sc, 'Staff', id=sid)
            for i in range(12):
                m = ET.SubElement(staff, 'Measure', number=str(i + 1))
                voice = ET.SubElement(m, 'voice')
                if sid == '4' or i == 11:
                    c = ET.SubElement(voice, 'Chord')
                    ET.SubElement(c, 'durationType').text = 'whole'
                    nt = ET.SubElement(c, 'Note')
                    ET.SubElement(nt, 'pitch').text = '60'
                    ET.SubElement(nt, 'tpc').text = '14'
                else:
                    rest = ET.SubElement(voice, 'Rest')
                    ET.SubElement(rest, 'durationType').text = 'measure'
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'parts.mscx'
            path.write_bytes(ET.tostring(score, encoding='utf-8'))
            parsed = Score(path)
            self.assertEqual(parsed.part_count, 4)
            self.assertEqual(parsed.part_staves['4'], ['4','5'])
            self.assertTrue(all(x['target'] != 'Piano' for x in analyze(path)['candidates']))

    def test_key_change_has_specific_risk(self):
        root = ET.fromstring(make_score())
        second_staff = root.find("Score/Staff[@id='2']")
        entry = second_staff.findall('Measure')[-1]
        ET.SubElement(entry.find('voice'), 'KeySig')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'key.mscx'
            path.write_bytes(ET.tostring(root, encoding='utf-8'))
            result = analyze(path)
            self.assertIn('key_signature_change_nearby', result['candidates'][0]['sources'][0]['risk_flags'])
            self.assertNotIn('time_signature_change_nearby', result['candidates'][0]['sources'][0]['risk_flags'])

    def test_invalid_and_malicious_xml(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'a.mscx'
            path.write_text('<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "X">]><museScore/>')
            with self.assertRaises(ScoreError):
                Score(path)

    def test_input_parameters(self):
        with self.assertRaises(ValueError):
            Settings(min_rest=1).validate()
        with self.assertRaises(ValueError):
            Settings(cue_bars=7).validate()

    def test_cli_json_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'a.mscx'
            out = Path(d)/'plan.json'
            path.write_bytes(make_score())
            run = subprocess.run([sys.executable,'-m','cueplanner','analyze',str(path),'--output',str(out)],
                                 text=True,capture_output=True,cwd=str(ROOT))
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('candidates', out.read_text())
            again = subprocess.run([sys.executable,'-m','cueplanner','analyze',str(path),'--output',str(out)],
                                   text=True,capture_output=True,cwd=str(ROOT))
            self.assertNotEqual(again.returncode, 0)

    def test_mcp_mock_connect_and_select(self):
        fake = str(ROOT/'tests'/'fake_mcp.py')
        with ScoreMcpClient(sys.executable, [fake], timeout=3) as mcp:
            reply = mcp.connect()
            self.assertEqual(reply['live_score']['measure_count'], 12)
            sel = mcp.select_measure(10, 1)
            self.assertEqual(sel, {'measure':10, 'staff':1})
            with self.assertRaises(BridgeError):
                mcp.connect('8.8.8.8')
            self.assertFalse(verify_live({'measure_count':9, 'part_count':3}, reply['live_score'])['metadata_consistent'])

    def test_mcp_verify_and_focus_cli(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'a.mscx'
            path.write_bytes(make_score())
            fake = str(ROOT/'tests'/'fake_mcp.py')
            base = [sys.executable,'-m','cueplanner','focus',str(path),'--candidate','2@12',
                    '--mcp-exe',sys.executable, '--mcp-arg',fake]
            run = subprocess.run(base, text=True,capture_output=True,cwd=str(ROOT))
            self.assertEqual(run.returncode, 0, run.stderr)
            res = json.loads(run.stdout)
            self.assertEqual(res['selection']['measure'], 10)
            self.assertEqual(res['selection']['staff'], 1)
            self.assertFalse(res['verification']['identity_proven'])


if __name__ == '__main__':
    unittest.main()
