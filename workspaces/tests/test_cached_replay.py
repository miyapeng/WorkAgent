"""Optional real-cache regression. No model or Search API network calls are permitted."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from common import REPO
import plan_intents
import construct_workspace


class CachedPilotReplay(unittest.TestCase):
    @unittest.skipUnless((REPO / 'work-plans/data/cache_graph/llm').exists()
                         and (REPO / 'work-plans/data/semantic_pilot/planning_report.json').exists(),
                         'Local private model caches not present in a fresh clone')
    def test_current_pilot_replays_identically_without_network(self):
        seed = REPO / 'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl'
        def deny(*args, **kwargs):
            raise AssertionError('Network is forbidden during offline replay')
        with tempfile.TemporaryDirectory() as temp, \
                patch('socket.create_connection', side_effect=deny), \
                patch('socket.socket.connect', side_effect=deny), \
                patch('http.client.HTTPSConnection.connect', side_effect=deny):
            root = Path(temp)
            plan_intents.run(seed, root / 'plans', REPO / 'work-plans/data/cache_graph',
                             REPO / 'work-plans/config/blueprint_pilot.json', 10, True)
            construct_workspace.load_inputs(root / 'plans', seed)
            for output, saved in ((root / 'plans', REPO / 'work-plans/data/semantic_pilot'),):
                for file in output.rglob('*'):
                    if file.is_file():
                        relative = file.relative_to(output)
                        self.assertEqual(file.read_bytes(), (saved / relative).read_bytes(), str(relative))


if __name__ == '__main__':
    unittest.main()
