"""运行端：受控文件工具接口。没有任意 Shell/Python 执行权限。"""

import base64
import copy
import json
import shutil
import uuid
from pathlib import Path

from .artifacts import FIELDS, pdf_text, read_xlsx, write_report, write_xlsx
from .build import read_json, write_json
from .verify import source_hashes, verify


class WorkEnvironment:
    def __init__(self, dataset_root="work_dataset", policy_kind="manual_reference"):
        self.root = Path(dataset_root).resolve()
        self.policy_kind = policy_kind
        self.run_dir = None
        self.done = True

    def _record(self, event):
        with (self.run_dir / "trajectory.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def reset(self, task_id="W001", condition="full"):
        if not task_id.isalnum() or condition not in ("full", "no_image"):
            raise ValueError("无效的 task_id 或 condition")
        # reset 总是创建新 episode；保留旧轨迹便于对比。
        self.package = self.root / "tasks" / task_id
        self.task = read_json(self.package / "task.json")
        self.run_dir = self.root / "runs" / task_id / uuid.uuid4().hex[:12]
        self.workspace = self.run_dir / "workspace"
        shutil.copytree(self.package / "workspace_init", self.workspace)
        if condition == "no_image":
            (self.workspace / "dashboard.png").unlink()
        self.baseline = source_hashes(self.workspace, self.task["inputs"])
        self.violated = False
        self.steps = 0
        self.done = False
        self.result = None
        self.metadata = {"task_id": task_id, "family_id": self.task["family_id"],
                         "split": self.task["split"], "condition": condition,
                         "policy_kind": self.policy_kind, "run_id": self.run_dir.name}
        write_json(self.run_dir / "metadata.json", self.metadata)
        observation = {"instruction": self.task["instruction"],
                       "files": sorted(p.name for p in self.workspace.iterdir()),
                       "tools": ["read_file", "view_image", "write_summary", "write_report", "finish"],
                       "max_steps": self.task["max_steps"]}
        self._record({"type": "reset", "observation": observation})
        return observation

    def _path(self, name):
        # 只允许公开输入及指定交付物；禁止目录穿越和符号链接。
        if name not in self.task["inputs"] + self.task["deliverables"]:
            raise ValueError("只能访问公开的输入和交付物")
        path = self.workspace / name
        if path.is_symlink() or path.resolve().parent != self.workspace.resolve():
            raise ValueError("不允许符号链接或工作空间外的路径")
        return path

    def _rows(self, rows):
        if not isinstance(rows, list) or len(rows) != 4:
            raise ValueError("W001 需要四行区域数据")
        import math
        for row in rows:
            if set(row) != set(FIELDS) or row["region"] not in ("A", "B", "C", "D"):
                raise ValueError("字段或区域不符合交付约定")
            if type(row["anomaly"]) is not bool:
                raise ValueError("anomaly 必须为 bool")
            if not all(type(row[k]) in (int, float) and math.isfinite(row[k]) for k in FIELDS[1:-1]):
                raise ValueError("数值必须有限")
            if row["revenue"] < 0:
                raise ValueError("收入必须非负")
        return rows

    def step(self, action):
        if self.done:
            raise RuntimeError("episode 已结束，请 reset")
        self.steps += 1
        self.violated |= source_hashes(self.workspace, self.baseline) != self.baseline
        try:
            tool = action["tool"]
            if tool == "read_file":
                path = self._path(action["path"])
                if path.suffix == ".xlsx":
                    observation = {"rows": read_xlsx(path)}
                elif path.suffix == ".pdf":
                    observation = {"text": pdf_text(path)}
                elif path.suffix == ".md":
                    observation = {"text": path.read_text(encoding="utf-8")}
                else:
                    raise ValueError("图片请使用 view_image")
            elif tool == "view_image":
                path = self._path(action["path"])
                if path.suffix != ".png":
                    raise ValueError("当前只接受 PNG")
                data = path.read_bytes()
                assets = self.run_dir / "assets"
                assets.mkdir(exist_ok=True)
                shutil.copyfile(path, assets / path.name)
                observation = {"mime_type": "image/png", "asset": f"assets/{path.name}",
                               "data_base64": base64.b64encode(data).decode("ascii")}
            elif tool == "write_summary":
                path = self._path("sales_summary.xlsx")
                write_xlsx(path, FIELDS, self._rows(action["rows"]))
                observation = {"created": path.name}
            elif tool == "write_report":
                narrative = action["narrative"]
                if not isinstance(narrative, str) or not 80 <= len(narrative) <= 1200 or not narrative.isascii():
                    raise ValueError("V0 分析文字需要 80–1200 个 ASCII 字符")
                path = self._path("quarterly_brief.pdf")
                write_report(path, self._rows(action["rows"]), narrative)
                observation = {"created": path.name}
            elif tool == "finish":
                self.done = True
                observation = {"submitted": True}
            else:
                raise ValueError(f"未知工具：{tool}")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            observation = {"error": str(exc)}
        self.violated |= source_hashes(self.workspace, self.baseline) != self.baseline
        if self.steps >= self.task["max_steps"]:
            self.done = True
            observation["budget_exhausted"] = True
        logged = {key: value for key, value in observation.items() if key != "data_base64"}
        self._record({"type": "step", "index": self.steps, "action": action,
                      "observation": logged, "done": self.done})
        return {"observation": observation, "done": self.done}

    def grade(self):
        if self.run_dir is None:
            raise RuntimeError("请先 reset")
        if self.result is None:
            self.done = True  # terminal reward，防止反复查询隐藏答案后继续解题。
            self.result = verify(self.package, self.workspace, self.baseline, self.violated)
            write_json(self.run_dir / "grade.json", self.result)
            self._record({"type": "grade", "result": self.result})
        return copy.deepcopy(self.result)

    def close(self):
        self.done = True  # 保留产物和轨迹；无后台进程需要回收。
