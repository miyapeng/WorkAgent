"""Source formats are parsed as inert data; audio/video are out of current scope."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from profile_files import parse_bytes
from common import DataError
from construct_workspace import discover_links


class FormatTests(unittest.TestCase):
    def test_tex_and_code_are_read_not_executed(self):
        for ext,mime,content in [('tex','application/x-tex',b'\\documentclass{article}\n\\begin{document}Example\\end{document}'),('py','text/x-python',b'raise RuntimeError("must not execute")'),('js','application/javascript',b'throw new Error("must not execute");')]:
            with patch('profile_files.subprocess.run',side_effect=AssertionError('No execution')):
                p=parse_bytes(content,'https://example.org/source.'+ext,mime)
            self.assertEqual(p['format'],ext);self.assertFalse(p['structure']['executed_or_compiled'])
            self.assertTrue(p['segments'])
    def test_notebook_read_only_and_existing_outputs_flagged(self):
        raw=json.dumps({'nbformat':4,'cells':[{'cell_type':'code','source':['1+1'],'outputs':[{'text':['2']}]}]}).encode()
        p=parse_bytes(raw,'https://example.org/a.ipynb','application/x-ipynb+json')
        self.assertEqual(p['format'],'ipynb');self.assertFalse(p['structure']['executed'])
        self.assertIn('notebook_contains_existing_outputs_review_for_answer_leakage',p['warnings'])
        with self.assertRaisesRegex(DataError,'invalid_notebook_structure'):
            parse_bytes(b'{}','https://example.org/a.ipynb','application/json')
    def test_tiff_actual_format_and_no_visual_claim(self):
        from PIL import Image
        raw=io.BytesIO();Image.new('RGB',(3,4)).save(raw,format='TIFF')
        p=parse_bytes(raw.getvalue(),'https://example.org/a.tiff','image/tiff')
        self.assertEqual(p['format'],'tiff');self.assertFalse(p['structure']['visual_content_verified'])
    def test_svg_parsed_without_rendering_or_active_content(self):
        p=parse_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect x="1" y="2" width="3" height="4"/></svg>','https://example.org/a.svg','image/svg+xml')
        self.assertEqual(p['format'],'svg');self.assertFalse(p['structure']['rendered']);self.assertFalse(p['structure']['visual_content_verified'])
        for bad in [b'<svg><script>alert(1)</script></svg>',b'<svg onload="bad"/>',b'<svg><image href="https://example.org/x"/></svg>',b'<!DOCTYPE svg [<!ENTITY x "x">]><svg/>']:
            with self.assertRaises(DataError):parse_bytes(bad,'https://example.org/a.svg','image/svg+xml')
    def test_audio_video_not_discovered_or_parsed(self):
        self.assertEqual(discover_links(b'<a href="a.mp4">video</a><a href="a.wav">audio</a>','https://example.org/'),[])
        for url,mime,raw in [('a.mp4','video/mp4',b'\0\0\0\0ftyp'),('a.mp3','audio/mpeg',b'ID3x')]:
            with self.assertRaisesRegex(DataError,'audio_video_out_of_scope'):parse_bytes(raw,'https://example.org/'+url,mime)


if __name__=='__main__':unittest.main()
