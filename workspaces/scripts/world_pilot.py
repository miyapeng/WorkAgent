#!/usr/bin/env python3
"""Opt-in, one-seed controlled-world experiment; does not change Stage 3 real admission."""
import argparse
import copy
import json
from pathlib import Path

from common import ROOT, REPO, DataError, require, sha256, json_bytes, save
from construct_workspace import load_inputs
from planning_common import schema, validate, load_llm, model_call, usage
from profile_files import parse_bytes
from world_contract import (VERSION, TABLES, METRICS, OUTPUT_COLUMNS, SCOPE, validate_world,
                            materialize, task_spec, oracle, visible_reference, grade_numeric,
                            verify_materialization, csv_bytes, grade_submission)

CHECKS = ['intent_preservation', 'information_sufficiency', 'cross_file_coherence',
          'professional_plausibility', 'task_verifier_alignment', 'no_answer_leakage', 'synthetic_disclosure']


def validate_review(review):
    validate(review, {'type':'object','additionalProperties':False,
        'required':['accepted','checks','issues','limitations'], 'properties':{
            'accepted':{'type':'boolean'},
            'checks':{'type':'object','additionalProperties':False,'required':CHECKS,
                      'properties':{k:{'type':'boolean'} for k in CHECKS}},
            'issues':{'type':'array','items':{'type':'string','minLength':1}},
            'limitations':{'type':'array','items':{'type':'string','minLength':1}}}})
    require(review['accepted'] == (all(review['checks'].values()) and not review['issues']), 'review_decision_mismatch')


def engineering_checks(workspace, world, hashes):
    verify_materialization(workspace, world, hashes)
    expected = oracle(world)
    rows = visible_reference(workspace)
    positive = grade_numeric(rows, expected)
    # Perturb every metric in every row, not only an easy hand-selected wrong answer.
    mutations = []
    for j,row in enumerate(rows):
        for metric in METRICS:
            bad = copy.deepcopy(rows)
            bad[j][metric] += 1
            mutations.append(grade_numeric(bad, expected)['passed'])
        bad = copy.deepcopy(rows); bad[j]['currency'] = 'EUR'
        mutations.append(grade_numeric(bad, expected)['passed'])
    duplicate_blocked = missing_blocked = False
    try: grade_numeric(rows + [rows[0]], expected)
    except DataError: duplicate_blocked = True
    try: grade_numeric(rows[:-1], expected)
    except DataError: missing_blocked = True
    require(positive['passed'] and not any(mutations) and duplicate_blocked and missing_blocked, 'verifier_self_check_failed')
    return {'kind':'engineering_reference_and_mutations_not_agent_probe',
            'visible_only_numeric_reference_passed':positive['passed'],
            'numeric_and_unit_mutations':len(mutations),'mutations_rejected':sum(not x for x in mutations),
            'duplicate_id_rejected':duplicate_blocked,'missing_id_rejected':missing_blocked,
            'semantic_quality_evaluated':False,'independent_agent_probe_run':False,
            'multimodal_ablation_run':False}


def coverage_records(plan, profiles):
    # An explicit, pinned one-family adapter, not semantic matching by the developer at runtime.
    files_by_node = {'i1':['context/project_brief.md'], 'i2':['records/baseline.csv'],
                     'i3':['records/baseline.csv'], 'i4':['records/actuals.csv'],
                     'i5':['records/actuals.csv'], 'i6':['context/monitoring_policy.md']}
    require({n['id'] for n in plan['information_nodes'] if n['type']=='external_input'} == set(files_by_node), 'family_input_mapping_changed')
    result = []
    for node,paths in files_by_node.items():
        evidence = []
        for path in paths:
            p = profiles[path]
            for segment in p['segments']:
                evidence.append({'file_id':p['file_id'],'path':path,'segment_id':segment['segment_id'],
                                 'locator':segment['locator'],'text':segment['text']})
        require(evidence, 'missing_materialized_input')
        result.append({'node_id':node, 'origin':'synthetic', 'status':'materialized_pending_semantic_review', 'evidence':evidence})
    return result


def run(args):
    plans,seeds,_ = load_inputs(args.plan_dir, args.seed_file)
    config = schema(args.config)
    require(config['family'] == VERSION, 'unsupported_world_family')
    plan = next((p for p in plans if p['seed_id']==config['seed_id']), None)
    require(plan is not None, 'seed_not_accepted')
    require(sha256(json_bytes(plan)) == config['blueprint_sha256'], 'family_blueprint_changed')
    seed = seeds[plan['seed_id']]
    private = args.output_dir / 'construction'
    code_paths = [Path(__file__), ROOT/'scripts/world_contract.py', ROOT/'config/world.schema.json',
                  ROOT/'prompts/world_generator.v1.txt', ROOT/'prompts/world_reviewer.v1.txt']
    binding = {'seed_sha256':sha256(json_bytes(seed)), 'blueprint_sha256':config['blueprint_sha256'],
               'config_sha256':sha256(json_bytes(config)),
               'implementation_sha256':sha256(b''.join(p.read_bytes() for p in code_paths))}
    if (private/'binding.json').exists():
        require(schema(private/'binding.json') == binding, 'experiment_changed_use_new_output_directory')
    save(private/'binding.json',binding)
    report = {'route':'controlled_synthesis', 'family':VERSION, 'seed_id':seed['seed_id'], **binding,
              'status':'incomplete', 'stage4_eligible':False, 'training_admitted':False,
              'real_anchor_count':0, 'synthetic_files':0, 'model_calls':[], 'failure_reasons':[],
              'limitations':['One task-family prototype, not generalized world synthesis.',
                            'A hidden world is a synthetic reference, not external factual truth.',
                            'Narrative quality, independent Agent execution and multimodal necessity remain untested.']}
    calls = report['model_calls']
    stage = 'world_generation'
    try:
        llm = load_llm(config, args.config, args.offline)
        world,meta = model_call(llm, ROOT/'prompts/world_generator.v1.txt',
            {'raw_seed':seed,'approved_blueprint':plan,'schema':schema(ROOT/'config/world.schema.json'),
             'scenario_number':config['scenario_number'], 'family':VERSION, 'scope':SCOPE,
             'metric_contract':METRICS,'materialized_tables':TABLES}, args.cache_dir, args.offline)
        calls.append(meta); save(private/'hidden_world.json',world)
        stage = 'world_constraints'; validate_world(world)
        stage = 'materialization'
        files = materialize(world); workspace = args.output_dir/'workspace_init'
        hashes = {name:sha256(data) for name,data in files.items()}
        if workspace.exists():
            actual = {p.relative_to(workspace).as_posix():sha256(p.read_bytes()) for p in workspace.rglob('*') if p.is_file()}
            require(actual == hashes, 'existing_workspace_changed')
        profiles = {}
        for name,data in files.items():
            path = workspace/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
            # No network or fake source URL: the parser accepts a local relative locator.
            profiles[name] = parse_bytes(path.read_bytes(), name, 'text/csv' if name.endswith('.csv') else 'text/markdown')
            require(profiles[name]['parse_status']=='parsed', 'materialized_file_unreadable')
        save(private/'file_profiles.json',list(profiles.values()))
        save(private/'source_manifest.json',{'origin':'synthetic','real_sources':[], 'files':[
            {'path':name,'sha256':hashes[name],'file_id':profiles[name]['file_id'], 'origin':'synthetic',
             'generator':VERSION,'world_sha256':sha256(json_bytes(world)),
             'redistribution_note':'Generated fictional research material; not a downloaded real source.'} for name in files]})
        coverage = coverage_records(plan,profiles)
        task = task_spec(world)
        numeric_oracle = oracle(world)
        # Evaluation remains outside workspace_init and is never included in a worker export.
        save(args.output_dir/'evaluation/numeric_reference.json',numeric_oracle)
        verifier = {'family':VERSION,'numeric_metrics':METRICS,'columns':OUTPUT_COLUMNS,
                    'absolute_tolerance':'0.01','unit_policy':'USD and hours as stated in column names',
                    'numeric_evaluator':'world_contract.grade_submission',
                    'semantic':{'status':'not_executed','criteria':task['deliverables'][1]['requirements']},
                    'process':'Final-state input hashes only; no claim of unmodified execution history.',
                    'total_reward':None}
        save(args.output_dir/'evaluation/verifier_spec.json',verifier)
        stage = 'engineering_checks'
        checks = engineering_checks(workspace,world,hashes); save(private/'engineering_checks.json',checks)
        report.update(synthetic_files=len(files), workspace_files=hashes, parsed_files=len(profiles),
                      external_inputs_materialized=len(coverage), engineering_checks=checks)
        stage = 'semantic_review'
        review,meta = model_call(llm, ROOT/'prompts/world_reviewer.v1.txt',
            {'raw_seed':seed,'approved_blueprint':plan,'hidden_world':world,
             'actual_file_contents':{k:v.decode() for k,v in files.items()},
             'task':task,'verifier':verifier}, args.cache_dir,args.offline)
        calls.append(meta); save(private/'semantic_review.json',review); validate_review(review)
        report['semantic_review'] = review
        for node in coverage:
            node['status'] = 'supported_synthetic' if review['accepted'] else 'pending_rejected_review'
        report['supported_synthetic_nodes'] = len(coverage) if review['accepted'] else 0
        if review['accepted']:
            report['status'] = 'experimental_draft'
            save(args.output_dir/'task.json',task)
        else:
            report['status'] = 'rejected'
            report['failure_reasons'].append({'stage':stage,'reason':review['issues']})
            save(private/'proposed_task.json',task)
        save(private/'information_coverage.json',coverage)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if getattr(exc,'model_metadata',None):calls.append(exc.model_metadata)
        report['failure_reasons'].append({'stage':stage,'reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__})
    report['model_usage'] = usage(calls)
    save(private/'construction_report.json',report)
    return report


def compare(output):
    world = schema(output/'world/construction/construction_report.json')
    real_path = output/'real/pilot_report.json'
    real = None
    if real_path.exists():
        candidates = schema(real_path)['workspaces']
        real = next((r for r in candidates if r['seed_id']==world['seed_id']),None)
    require(real is None or real['blueprint_sha256']==world['blueprint_sha256'], 'comparison_blueprint_mismatch')
    report = {'seed_id':world['seed_id'],'blueprint_sha256':world['blueprint_sha256'],
        'real_evidence':None if real is None else {k:real[k] for k in ('status','counts','failure_reasons','model_usage','search_cost')},
        'controlled_synthesis':{k:world.get(k) for k in ('status','synthetic_files','supported_synthetic_nodes','engineering_checks','semantic_review','failure_reasons','model_usage')},
        'interpretation':'One paired feasibility experiment. Routes have different provenance and admission criteria; no success-rate or realism superiority claim. No independent Agent Probe on either route.'}
    save(output/'comparison_report.json',report)
    return report


def export_agent(package,destination):
    report = schema(package/'construction/construction_report.json')
    require(report['status']=='experimental_draft','only_experimental_draft_export')
    require(not destination.exists(),'export_destination_exists')
    world = schema(package/'construction/hidden_world.json')
    verify_materialization(package/'workspace_init',world,report['workspace_files'])
    task = schema(package/'task.json')
    require(task==task_spec(world),'task_changed')
    save(destination/'task.json',task)
    for name in report['workspace_files']:
        target = destination/'workspace_init'/name; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((package/'workspace_init'/name).read_bytes())
    (destination/'outputs').mkdir()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan-dir',type=Path,default=REPO/'work-plans/data/semantic_pilot')
    p.add_argument('--seed-file',type=Path,default=REPO/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl')
    p.add_argument('--config',type=Path,default=ROOT/'config/world_pilot.json')
    p.add_argument('--output-dir',type=Path,default=ROOT/'data/world_pilot/world')
    p.add_argument('--cache-dir',type=Path,default=ROOT/'data/cache_world')
    p.add_argument('--offline',action='store_true')
    p.add_argument('--compare',type=Path)
    p.add_argument('--export-agent',type=Path)
    p.add_argument('--grade-submission',type=Path)
    a=p.parse_args()
    if a.compare:print(json.dumps(compare(a.compare),indent=2));return
    if a.export_agent:export_agent(a.output_dir,a.export_agent);print('Exported experimental worker inputs only.');return
    if a.grade_submission:
        world=schema(a.output_dir/'construction/hidden_world.json')
        report=schema(a.output_dir/'construction/construction_report.json')
        require(report['status']=='experimental_draft','not_an_experimental_draft')
        verify_materialization(a.grade_submission/'workspace_init',world,report['workspace_files'])
        print(json.dumps(grade_submission(a.grade_submission,oracle(world)),indent=2));return
    result=run(a);print(json.dumps({k:result[k] for k in ('status','synthetic_files','failure_reasons','model_usage')},indent=2))


if __name__=='__main__':main()
