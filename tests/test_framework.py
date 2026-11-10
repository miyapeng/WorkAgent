import tempfile
import unittest
from pathlib import Path

from workenv.build import build_task, read_json
from workenv.environment import WorkEnvironment
from workenv.export import export_dataset
from workenv.probe import probe
from workenv.reference import run_reference

DESIGN = Path(__file__).resolve().parents[1] / "examples" / "W001.json"


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        build_task(DESIGN, self.root)

    def test_positive_and_mutation_probes(self):
        result = probe(self.root)
        self.assertTrue(result["passed"], result)

    def test_demo_excluded_from_sft_and_images_replayable(self):
        env = WorkEnvironment(self.root)
        env.reset()
        self.assertTrue(run_reference(env)["success"])
        counts = export_dataset(self.root)
        self.assertEqual(counts, {"rollouts": 1, "sft_candidates": 0, "rl_tasks": 1})
        self.assertTrue((env.run_dir / "assets/dashboard.png").exists())
        self.assertFalse((env.workspace / "evaluation").exists())
        self.assertEqual(read_json(env.run_dir / "grade.json"), env.grade())
        with self.assertRaises(RuntimeError):
            env.step({"tool": "read_file", "path": "orders.xlsx"})

    def test_source_violation_persists_after_restoration(self):
        env = WorkEnvironment(self.root)
        env.reset()
        source = env.workspace / "report_requirements.md"
        original = source.read_bytes()
        source.write_text("tampered")
        env.step({"tool": "read_file", "path": source.name})
        source.write_bytes(original)
        result = run_reference(env)
        self.assertTrue(result["hard_gate_triggered"])
        self.assertEqual(result["reward"], 0)

    def test_budget_and_symlink(self):
        env = WorkEnvironment(self.root)
        env.reset()
        target = env.workspace / "report_requirements.md"
        target.unlink()
        target.symlink_to(env.package / "evaluation/oracle.json")
        result = env.step({"tool": "read_file", "path": target.name})
        self.assertIn("error", result["observation"])
        for _ in range(env.task["max_steps"] - 1):
            result = env.step({"tool": "unknown"})
        self.assertTrue(result["done"])
        self.assertTrue(result["observation"]["budget_exhausted"])

    def test_build_does_not_overwrite(self):
        with self.assertRaises(FileExistsError):
            build_task(DESIGN, self.root)


if __name__ == "__main__":
    unittest.main()
