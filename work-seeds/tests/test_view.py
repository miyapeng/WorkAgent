"""The browser must expose the complete current pool, never the archived baseline."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_view import build_view, ROOT, read_jsonl
from build_onet import DataError


class ViewTests(unittest.TestCase):
    def test_full_pool_exports_and_revision_translation_follow_current_text(self):
        source=ROOT/'data/raw_work_seeds'
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            output=Path(temp)
            payload=build_view(source,output)
            digital=[r for r in payload['tasks'] if r['digital_label']=='DIGITAL']
            self.assertEqual(digital,read_jsonl(source/'digital_task_pool.jsonl'))
            self.assertEqual(payload['sampled_ids'],[r['seed_id'] for r in read_jsonl(source/'sampled_raw_seeds.jsonl')])
            for name in ('effective_tasks.jsonl','digital_task_pool.jsonl','sampled_raw_seeds.jsonl','stage1_report.json'):
                self.assertEqual((source/name).read_bytes(),(output/name).read_bytes())
            self.assertEqual(payload['validation']['digital_translated'],len(digital))
            for r in digital:
                if r['task_source']=='emerging_revision':
                    self.assertIn(r['task_text'],payload['zh'])
                    self.assertNotIn(r['original_task_id'],payload['zh'])

    def test_truncated_digital_pool_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()):
            source=Path(temp)/'input';shutil.copytree(ROOT/'data/raw_work_seeds',source)
            path=source/'digital_task_pool.jsonl';path.write_text('\n'.join(path.read_text().splitlines()[:-1])+'\n')
            with self.assertRaisesRegex(DataError,'complete DIGITAL subset'):
                build_view(source,Path(temp)/'output')
            self.assertFalse((Path(temp)/'output/catalog.js').exists())


if __name__=='__main__':unittest.main()
