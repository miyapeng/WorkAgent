#!/usr/bin/env python3
"""Official Raw Seed -> minimal Blueprint DAG -> independent semantic admission."""
import argparse
from collections import defaultdict,deque,Counter
import csv
from pathlib import Path
from planning_common import REPO,DataError,require,schema,validate,load_llm,model_call,usage,save,read_jsonl,write_jsonl,sha256,json_bytes
from compile_blueprint import compile_blueprint, validate_formats, VOCABULARY
ROOT=REPO/'work-plans'


def validate_blueprint(plan,seed):
    validate(plan,schema(ROOT/'config/blueprint.schema.json'))
    require(plan['seed_id']==seed['seed_id'],'seed_id_mismatch')
    for output in plan['deliverables']:validate_formats(output['type'],output['preferred_formats'],'deliverables')
    for n in plan['information_nodes']:
        if n['type']=='external_input':
            validate_formats(n['kind'],n['preferred_formats'],'inputs')
            require((n['kind']=='text_instruction')==(n['supply_channel']=='task_instruction'),'instruction_kind_source_mismatch')
    nodes={n['id']:n for n in plan['information_nodes']};outputs={n['id'] for n in plan['deliverables']}
    ids=set(nodes)|outputs
    require(len(ids)==len(plan['information_nodes'])+len(plan['deliverables']),'duplicate_node_id')
    edges=[tuple(e) for e in plan['dependencies']];require(len(edges)==len(set(edges)),'duplicate_edge')
    children=defaultdict(set);parents=defaultdict(set)
    for a,b in edges:
        require(a in ids and b in ids and a!=b,'invalid_dependency_reference')
        require(a not in outputs,'deliverable_must_be_sink')
        require(b not in nodes or nodes[b]['type']!='external_input','external_input_must_be_root')
        children[a].add(b);parents[b].add(a)
    for ident in ids:
        if ident in outputs or nodes[ident]['type']!='external_input':require(bool(parents[ident]),'missing_premises:'+ident)
    degrees={i:len(parents[i]) for i in ids};queue=deque(sorted(i for i in ids if not degrees[i]));visited=[]
    while queue:
        i=queue.popleft();visited.append(i)
        for child in sorted(children[i]):
            degrees[child]-=1
            if degrees[child]==0:queue.append(child)
    require(len(visited)==len(ids),'cyclic_graph')
    serves=set(outputs)
    for i in reversed(visited):
        if children[i]&serves:serves.add(i)
    require(serves==ids,'unused_information_node')
    actual=set()
    for h in plan['modality_hypotheses']:
        n=nodes.get(h['node_id']);require(n and n['type']=='external_input','invalid_modality_node')
        require(h['modality_candidate'] in n['modality_candidates'],'modality_not_in_node')
        target=h['supports_node_id'];require(target in nodes and nodes[target]['type']!='external_input','invalid_modality_operation')
        reachable=set();queue=[h['node_id']]
        while queue:
            current=queue.pop()
            if current not in reachable:reachable.add(current);queue.extend(children[current])
        require(target in reachable,'modality_operation_not_dependent_on_input')
        pair=(h['node_id'],h['modality_candidate']);require(pair not in actual,'duplicate_modality_hypothesis');actual.add(pair)
    expected={(n['id'],m) for n in nodes.values() if n['type']=='external_input' for m in n['modality_candidates'] if m not in ('text','table')}
    require(actual==expected,'missing_modality_rationale')
    return {'schema':True,'seed_id':True,'dag':True,'roots_and_sinks':True,'all_nodes_serve_outputs':True,'modality_linkage':True}


def validate_review(review):
    validate(review,schema(ROOT/'config/review.schema.json'))
    require(review['accepted']==(all(review['checks'].values()) and not review['issues']),'inconsistent_semantic_review')


def load_raw(path):
    rows=read_jsonl(path);require(len(rows)==len({r['seed_id'] for r in rows}),'duplicate_seed_id')
    for r in rows:require(r['digital_label']=='DIGITAL' and r['task_text'],'non_digital_or_empty_seed')
    official={r['seed_id']:r for r in read_jsonl(REPO/'work-seeds/data/raw_work_seeds/digital_task_pool.jsonl')}
    require(all(official.get(r['seed_id'])==r for r in rows),'raw_seed_not_current_official_pool')
    return {r['seed_id']:r for r in rows}


def background(seed):
    with (REPO/'work-seeds/data/processed/occupations.csv').open() as s:occupations={r['occupation_code']:r['occupation_title'] for r in csv.DictReader(s)}
    with (REPO/'work-seeds/data/processed/dwas.csv').open() as s:dwas={r['dwa_id']:r['dwa_name'] for r in csv.DictReader(s)}
    require(occupations.get(seed['occupation_code'])==seed['occupation_title'],'official_occupation_mismatch')
    return {'occupation_title':occupations[seed['occupation_code']],'official_dwas':[{'dwa_id':d,'dwa_name':dwas[d]} for d in seed['dwa_ids']]}


def run(input_file,output_dir,cache,config_path,limit=None,offline=False):
    config=schema(config_path);llm=load_llm(config,config_path,offline);raw=load_raw(input_file)
    selected=config.get('pilot_seeds') or [{'seed_id':sid} for sid in raw]
    if limit is not None:require(limit>=0,'negative_limit');selected=selected[:limit]
    require(len(selected)==len({x['seed_id'] for x in selected}),'duplicate_pilot_seed')
    report={'interface':'raw-blueprint-v2','input_sha256':sha256(Path(input_file).read_bytes()),'config_sha256':sha256(Path(config_path).read_bytes()),'seeds':{},'limitations':['Independent review uses the same model family, not expert certification.','Task instruction requirements remain pending for Stage 4; they are not case facts.']}
    plans=[];calls=[]
    for item in selected:
        sid=item['seed_id'];require(sid in raw,'selected_seed_missing:'+sid);seed=raw[sid]
        record={'status':'failed','seed_sha256':sha256(json_bytes(seed)),'selection_reason':item.get('selection_reason','CLI input order'),'model_calls':[],'deterministic_checks':None,'semantic_review':None}
        checkpoint=cache/'planning'/(sha256(json_bytes({'seed':seed,'config':config,'prompts':{p.name:sha256(p.read_bytes()) for p in (ROOT/'prompts').glob('*.txt')},'schemas':{p.name:sha256(p.read_bytes()) for p in (ROOT/'config').glob('*.schema.json')},'code':sha256(Path(__file__).read_bytes()),'compiler':sha256((ROOT/'scripts/compile_blueprint.py').read_bytes()),'vocabulary':VOCABULARY}))+'.json')
        if checkpoint.exists():record=schema(checkpoint)
        else:
            stage='generation'
            try:
                context={'raw_seed':seed,'official_background':background(seed),'schema':schema(ROOT/'config/semantic_plan.schema.json'),'artifact_vocabulary':VOCABULARY}
                semantic,meta=model_call(llm,ROOT/'prompts'/config.get('planner_prompt','semantic_planner.v1.txt'),context,cache,offline)
                record['model_calls'].append(meta);record['semantic_plan']=semantic
                if config.get('format_correction') and 'failure_reason' not in semantic:
                    try:compile_blueprint(semantic,sid)
                    except DataError as error:
                        if not str(error).startswith(('schema:','format_not_allowed','empty_formats','unknown_artifact_kind')):raise
                        record['initial_structural_error']=str(error)
                        fixed,meta=model_call(llm,ROOT/'prompts/format_correction.v1.txt',
                            {**context,'previous_plan':semantic,'structural_error':str(error)},cache,offline)
                        record['model_calls'].append(meta)
                        def meaning(value):
                            if isinstance(value,dict):return {k:meaning(v) for k,v in value.items() if k not in ('kind','preferred_formats')}
                            if isinstance(value,list):return [meaning(v) for v in value]
                            return value
                        require(meaning(fixed)==meaning(semantic),'format_correction_changed_professional_content')
                        semantic=fixed;record['semantic_plan']=semantic
                if 'failure_reason' in semantic:
                    stage='planning_limitation';raise DataError('planning_failure:'+str(semantic['failure_reason']))
                stage='semantic_schema';validate(semantic,schema(ROOT/'config/semantic_plan.schema.json'));record['semantic_schema_passed']=True
                stage='graph_compilation';plan=compile_blueprint(semantic,sid);record['proposed_blueprint']=plan
                stage='graph_validation';record['deterministic_checks']=validate_blueprint(plan,seed)
                stage='semantic_review';review,meta=model_call(llm,ROOT/'prompts/blueprint_reviewer.v1.txt',{'raw_seed':seed,'blueprint':plan,'schema':schema(ROOT/'config/review.schema.json')},cache,offline)
                record['model_calls'].append(meta);validate_review(review);record['semantic_review']=review
                record['status']='accepted' if review['accepted'] else 'rejected'
                record['failure_stage']=None if review['accepted'] else stage
                record['failure_reasons']=review['issues']
                record['blueprint_sha256']=sha256(json_bytes(plan))
            except (OSError,ValueError,KeyError,TypeError) as exc:
                if getattr(exc,'model_metadata',None):record['model_calls'].append(exc.model_metadata)
                record.update(failure_stage=stage,failure_reasons=[str(exc) if isinstance(exc,DataError) else type(exc).__name__])
            # Preserve model/validation outcomes, but let transient transport/auth failures retry next run.
            if (('proposed_blueprint' in record and record.get('semantic_review') is not None)
                    or record.get('failure_stage') in ('planning_limitation','semantic_schema','graph_compilation','graph_validation') or record['status']=='accepted'):
                save(checkpoint,record)
        if record['status']=='accepted':
            validate_blueprint(record['proposed_blueprint'],seed);validate_review(record['semantic_review'])
            plans.append(record['proposed_blueprint'])
        report['seeds'][sid]=record;calls.extend(record['model_calls'])
        print(sid,record['status'],flush=True)
        write_jsonl(output_dir/'blueprints.jsonl',plans);save(output_dir/'planning_report.json',report)
    report['counts']={'input':len(selected),'generated':sum('semantic_plan' in r and 'failure_reason' not in r['semantic_plan'] for r in report['seeds'].values()),'semantic_schema_passed':sum(bool(r.get('semantic_schema_passed')) for r in report['seeds'].values()),'semantic_reviewed':sum(r['semantic_review'] is not None for r in report['seeds'].values()),'graph_passed':sum(bool(r['deterministic_checks']) for r in report['seeds'].values()),'accepted':len(plans),'rejected_or_failed':len(selected)-len(plans),'modality_candidate_plans':sum(bool(p['modality_hypotheses']) for p in plans)}
    write_jsonl(output_dir/'blueprints.jsonl',plans)
    report['counts']['semantic_review_attempted']=sum(any(c['prompt_version']=='blueprint_reviewer.v1' for c in r['model_calls']) for r in report['seeds'].values())
    report['model_usage']=usage(calls);report['blueprints_sha256']=sha256((output_dir/'blueprints.jsonl').read_bytes())
    save(output_dir/'planning_report.json',report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-file',type=Path,default=REPO/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl')
    p.add_argument('--output-dir',type=Path,default=ROOT/'data/semantic_pilot')
    p.add_argument('--cache-dir',type=Path,default=ROOT/'data/cache_graph')
    p.add_argument('--config',type=Path,default=ROOT/'config/blueprint_pilot.json')
    p.add_argument('--limit',type=int);p.add_argument('--offline',action='store_true')
    a=p.parse_args();r=run(a.input_file,a.output_dir,a.cache_dir,a.config,a.limit,a.offline);print(r['counts'])
if __name__=='__main__':main()
