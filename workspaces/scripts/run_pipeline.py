#!/usr/bin/env python3
"""Single CLI: current Raw Seeds -> reviewed blueprints -> bounded real retrieval."""
import argparse
from pathlib import Path
from common import ROOT,REPO
import plan_intents
from construct_workspace import run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed-file',type=Path,default=REPO/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl')
    p.add_argument('--planning-config',type=Path,default=REPO/'work-plans/config/blueprint_pilot.json')
    p.add_argument('--workspace-config',type=Path,default=ROOT/'config/graph_pipeline.json')
    p.add_argument('--plan-dir',type=Path,default=REPO/'work-plans/data/generated')
    p.add_argument('--output-dir',type=Path,default=ROOT/'data/generated')
    p.add_argument('--limit',type=int,default=10);p.add_argument('--offline',action='store_true')
    a=p.parse_args()
    planning=plan_intents.run(a.seed_file,a.plan_dir,REPO/'work-plans/data/cache_graph',a.planning_config,a.limit,a.offline)
    workspaces=run(a.plan_dir,a.seed_file,a.output_dir,ROOT/'data/cache_graph',a.workspace_config,a.offline)
    print({'blueprints':planning['counts'],'workspaces':workspaces['counts']})
if __name__=='__main__':main()
