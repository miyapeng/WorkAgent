import argparse
import json
from pathlib import Path

from .build import build_task
from .environment import WorkEnvironment
from .export import export_dataset
from .probe import probe
from .reference import run_reference


def main():
    parser = argparse.ArgumentParser(description="W001 最小端到端工作环境")
    parser.add_argument("command", choices=["build", "demo", "probe", "export"])
    parser.add_argument("--root", default="work_dataset", help="生成文件的目录")
    parser.add_argument("--design", default="examples/W001.json")
    parser.add_argument("--task", default="W001")
    parser.add_argument("--condition", choices=["full", "no_image"], default="full")
    args = parser.parse_args()
    if args.command == "build":
        print(build_task(args.design, args.root))
    elif args.command == "demo":
        package = Path(args.root) / "tasks" / args.task
        if not package.exists():
            built = build_task(args.design, args.root)
            if built.name != args.task:
                parser.error("--task 与 --design 中的 task_id 不一致")
        env = WorkEnvironment(args.root)
        env.reset(args.task, args.condition)
        result = run_reference(env)
        env.close()
        print(json.dumps({"run_directory": str(env.run_dir), **result}, ensure_ascii=False, indent=2))
        print("导出：", export_dataset(args.root))
    elif args.command == "probe":
        result = probe(args.root, args.task)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["passed"]:
            raise SystemExit(1)
    else:
        print(export_dataset(args.root))


if __name__ == "__main__":
    main()
