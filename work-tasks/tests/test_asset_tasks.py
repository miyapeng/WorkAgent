"""Positive/negative verifier fixtures. These are not solver rollouts or real pilots."""
from pathlib import Path
import copy
import io
import sys
import tempfile
import unittest
import zipfile
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from task_common import DataError
from asset_tasks import compile_task
from artifact_checks import inspect_output
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'workspaces/tests'))
from test_asset_binding import fixture
from asset_binding import compile_binding


def design():
    return {'instruction':'Compare the supplied records for the requested purpose.',
        'requirements':[{'description':'Derive differences from the source records.',
            'information_node_ids':['i3'],'deliverable_node_ids':['out1'],'full_credit':['Ground each comparison in the source values.'],
            'common_errors':['Invented source values.'],'conflict_policy':'Unsupported claims receive no credit.','critical':True}]}


class AssetTaskTests(unittest.TestCase):
    def test_public_task_private_criteria_and_binding_alignment(self):
        plan,case,profiles,sources=fixture();g=compile_binding(case,plan,profiles,sources)
        a=compile_task(design(),g,plan);self.assertEqual(a,compile_task(design(),g,plan))
        task,rubric,mapping,evidence=a
        self.assertIn('hypothetical exercise',task['instruction'])
        self.assertNotIn('binding_i1',str(task));self.assertEqual(len(rubric['items']),2)
        self.assertEqual({m['requirement_id'] for m in mapping},{r['requirement_id'] for r in task['requirements']})
        self.assertEqual(evidence['nodes'][0]['type'],'asset_binding')
    def test_unknown_operation_omitted_operation_hidden_leak_and_duplicate(self):
        plan,case,profiles,sources=fixture();g=compile_binding(case,plan,profiles,sources)
        for mutation in ('unknown','omitted','hidden','duplicate','unknown_path'):
            with self.subTest(mutation=mutation):
                d=design()
                if mutation=='unknown':d['requirements'][0]['information_node_ids']=['invented']
                if mutation=='omitted':d['requirements'][0]['information_node_ids']=['i1']
                if mutation=='hidden':d['instruction']='Read evaluation/rubric.json.'
                if mutation=='duplicate':d['requirements'].append(copy.deepcopy(d['requirements'][0]))
                if mutation=='unknown_path':d['instruction']='Read workspace_init/invented.csv.'
                with self.assertRaises(DataError):compile_task(d,g,plan)
    def test_native_artifact_positive_and_negative_pairs(self):
        pairs={'html':(b'<html><body><h1>Fixture</h1></body></html>',b'not html'),
            'obj':(b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n',b'v 0 0 0\nf 1 2 9\n'),
            'gltf':(b'{"asset":{"version":"2.0"},"meshes":[{"primitives":[{"attributes":{"POSITION":0}}]}],"accessors":[{"count":3}]}',b'{"asset":{"version":"2.0"}}')}
        with tempfile.TemporaryDirectory() as tmp:
            for fmt,(good,bad) in pairs.items():
                with self.subTest(fmt=fmt):
                    p=Path(tmp)/('artifact.'+fmt);p.write_bytes(good);self.assertTrue(inspect_output(p,fmt))
                    p.write_bytes(bad)
                    with self.assertRaises((ValueError,KeyError)):inspect_output(p,fmt)
            p=Path(tmp)/'artifact.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('index.html',pairs['html'][0])
            self.assertEqual(inspect_output(p,'zip')['entries'],['index.html'])
            with zipfile.ZipFile(p,'w') as z:z.writestr('../escape.py','print(1)')
            with self.assertRaisesRegex(DataError,'archive_path_traversal'):inspect_output(p,'zip')
    def test_video_is_decoded_not_accepted_from_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=32x32:d=0.3','-pix_fmt','yuv420p',str(p)],check=True,capture_output=True,timeout=30)
            self.assertEqual(inspect_output(p,'mp4')['width'],32)
            p.write_bytes(b'fake mp4')
            with self.assertRaisesRegex(DataError,'unreadable_media'):inspect_output(p,'mp4')


if __name__=='__main__':unittest.main()
