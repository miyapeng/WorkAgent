"""导出本地中间格式；具体训练器的数据适配留给下一阶段。"""

import json
from pathlib import Path

from .build import read_json


def export_dataset(root):
    root = Path(root).resolve()
    training = root / "training"
    training.mkdir(exist_ok=True)
    episodes = []
    demonstrations = []
    for run in sorted((root / "runs").glob("*/*")):
        if not (run / "grade.json").exists():
            continue
        metadata = read_json(run / "metadata.json")
        grade = read_json(run / "grade.json")
        events = [json.loads(line) for line in (run / "trajectory.jsonl").read_text().splitlines()]
        item = {**metadata, "run_directory": str(run.relative_to(root)), "grade": grade, "events": events}
        episodes.append(item)
        # 本版 reference 从不进入 SFT。后续接入真实 teacher 并人工审核后才可收录。
        review = run / "review.json"
        if (metadata["policy_kind"] == "teacher" and metadata["split"] == "train"
                and metadata["condition"] == "full" and grade["success"]
                and review.exists() and read_json(review).get("approved") is True):
            demonstrations.append(item)
    tasks = []
    for package in sorted((root / "tasks").iterdir()):
        task = read_json(package / "task.json")
        tasks.append({"task_id": task["task_id"], "family_id": task["family_id"], "split": task["split"],
                      "package": str(package.relative_to(root)),
                      "environment": "workenv.WorkEnvironment", "reward": "terminal"})
    for name, records in [("rollouts.jsonl", episodes), ("sft_candidates.jsonl", demonstrations),
                          ("rl_tasks.jsonl", tasks)]:
        (training / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    return {"rollouts": len(episodes), "sft_candidates": len(demonstrations), "rl_tasks": len(tasks)}
