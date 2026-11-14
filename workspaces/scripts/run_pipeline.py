#!/usr/bin/env python3
"""Single CLI: Raw Seeds -> Intent Graph -> asset bindings -> draft tasks."""
import argparse
import subprocess
import sys
from pathlib import Path
from common import ROOT,REPO
import plan_intents
from construct_workspace import run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed-file',type=Path,default=REPO/'work-seeds/data/raw_work_seeds/digital_task_pool.jsonl')
    p.add_argument('--planning-config',type=Path,default=REPO/'work-plans/config/asset_pilot.json')
    p.add_argument('--workspace-config',type=Path,default=ROOT/'config/asset_pilot.json')
    p.add_argument('--plan-dir',type=Path,default=REPO/'work-plans/data/asset_pilot_v2')
    p.add_argument('--output-dir',type=Path,default=ROOT/'data/asset_pilot_v4')
    p.add_argument('--cache-dir',type=Path,default=ROOT/'data/cache_assets')
    p.add_argument('--through-stage',type=int,choices=[2,3,4],default=4)
    p.add_argument('--task-dir',type=Path,default=REPO/'work-tasks/generated/asset_pilot')
    p.add_argument('--task-report-dir',type=Path,default=REPO/'work-tasks/data/asset_pilot_current')
    p.add_argument('--limit',type=int,default=10);p.add_argument('--offline',action='store_true')
    a=p.parse_args()
    planning=plan_intents.run(a.seed_file,a.plan_dir,REPO/'work-plans/data/cache_graph',a.planning_config,a.limit,a.offline)
    if a.through_stage==2:print(planning['counts']);return
    workspaces=run(a.plan_dir,a.seed_file,a.output_dir,a.cache_dir,a.workspace_config,a.offline)
    print({'blueprints':planning['counts'],'workspaces':workspaces['counts']})
    if a.through_stage==4:
        command=[sys.executable,str(REPO/'work-tasks/scripts/construct_tasks.py'),
            '--plan-dir',str(a.plan_dir),'--seed-file',str(a.seed_file),'--workspace-dir',str(a.output_dir),
            '--output-dir',str(a.task_dir),'--report-dir',str(a.task_report_dir),'--limit',str(a.limit)]
        if a.offline:command.append('--offline')
        subprocess.run(command,check=True)
if __name__=='__main__':main()
