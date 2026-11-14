"""Task construction from a checked asset graph; no model-authored executable checks."""
import shutil
import tempfile
from task_common import *
from task_verifier import compile_verifier
from asset_workspace import verify_asset_workspace


def evidence_graph(grounded, plan):
    nodes=[]
    for b in grounded['bindings']:
        if b['status']!='supported':continue
        nodes.append({'evidence_id':'binding_'+b['information_node_id'],
            'type':'commission_requirement' if b['origin']=='synthetic_instruction' else 'asset_binding',
            'information_node_id':b['information_node_id'],'description':b['instruction'] or b['rationale'],
            'references':b['references']})
    types={n['id']:n['type'] for n in plan['information_nodes']}
    for op in grounded['operations']:
        nodes.append({'evidence_id':'operation_'+op['node_id'],
            'type':'decision_requirement' if types[op['node_id']]=='professional_judgment' else 'derived_requirement',
            'information_node_id':op['node_id'],'description':op['description'],'references':[]})
    return {'interface':'asset-evidence-v1','seed_id':plan['seed_id'],'grounded_graph_sha256':digest(grounded),
            'assets':grounded['assets'],'nodes':nodes,'dependencies':grounded['dependencies'],
            'observation_policy':'VLM descriptions are fallible observations, never exact visual oracles.'}


def compile_task(design,graph,plan):
    schema('asset_task_plan',design)
    nodes={n['id'] for n in plan['information_nodes']};outputs={d['node_id']:d for d in graph['deliverables']}
    used=set();task={'instruction':design['instruction'],'deliverables':[], 'requirements':[]};items=[];mapping=[]
    evidence=evidence_graph(graph,plan)
    schema('asset_evidence',evidence)
    bindings={b['information_node_id']:b for b in graph['bindings'] if b['status']=='supported'}
    def ancestors(ids):
        result=set(ids)
        while True:
            new=result|{a for a,b in plan['dependencies'] if b in result}
            if new==result:return result
            result=new
    for i,(oid,d) in enumerate(outputs.items(),1):
        from artifact_checks import FORMATS
        from task_verifier import MIME
        require(d['format'] in FORMATS or d['format'] in MIME,'output_format_not_implemented')
        task['deliverables'].append({'deliverable_id':'d'+str(i),'plan_deliverable_id':oid,
            'path':'outputs/'+oid+'.'+d['format'],'format':d['format'],'description':d['description']})
    output_ids={d['plan_deliverable_id']:d['deliverable_id'] for d in task['deliverables']}
    for i,r in enumerate(design['requirements'],1):
        require(set(r['information_node_ids'])<=nodes,'unknown_task_operation')
        require(set(r['deliverable_node_ids'])<=set(outputs),'unknown_task_deliverable')
        used.update(r['information_node_ids']);rid='r'+str(i)
        related=ancestors(r['information_node_ids'])
        refs=['binding_'+n for n in sorted(related & set(bindings))]
        require(refs,'task_requirement_without_binding')
        task['requirements'].append({'requirement_id':rid,'description':r['description'],'kind':'outcome',
            'information_node_ids':r['information_node_ids'],'deliverable_ids':[output_ids[n] for n in r['deliverable_node_ids']],
            'unscored_reason':None})
        items.append({'rubric_id':'rubric_'+rid,'requirement_id':rid,'requirement':r['description'],
            'evidence_ids':refs,'verification_type':'semantic',
            'verification_spec':{'kind':'semantic_guide','full_credit':[r['description']]+r['full_credit'],
                'common_errors':r['common_errors'],'conflict_policy':r['conflict_policy']},'weight':4,'critical':r['critical']})
        mapping.append({'requirement_id':rid,'evidence_ids':refs})
    # A result criterion may cover the operations feeding it. Do not force an
    # extra scored process requirement for every intermediate planning node.
    require({o['node_id'] for o in graph['operations']}<=ancestors(used),'task_omits_professional_operation')
    require(len({r['description'].casefold().strip() for r in design['requirements']})==len(design['requirements']),'duplicate_task_requirement')
    # Keep authored user choices visible. They are not source facts or hidden rubric requirements.
    commission=[b['instruction'] for b in graph['bindings'] if b['origin']=='synthetic_instruction' and b['status']=='supported']
    if commission:task['instruction']+='\n\nCommission details (a hypothetical exercise using the supplied references):\n'+'\n'.join('- '+v for v in commission)
    for d in task['deliverables']:
        rid='artifact_'+d['deliverable_id'];description=f"Deliver a readable {d['format']} artifact at {d['path']}."
        linked=[r for r in task['requirements'] if d['deliverable_id'] in r['deliverable_ids']];require(linked,'deliverable_without_requirement')
        refs=sorted({e for m in mapping for e in m['evidence_ids'] if m['requirement_id'] in {r['requirement_id'] for r in linked}})
        ids=sorted({n for r in linked for n in r['information_node_ids']})
        task['requirements'].append({'requirement_id':rid,'description':description,'kind':'outcome',
            'information_node_ids':ids,'deliverable_ids':[d['deliverable_id']],'unscored_reason':None})
        items.append({'rubric_id':'check_'+rid,'requirement_id':rid,'requirement':description,'evidence_ids':refs,
            'verification_type':'programmatic','verification_spec':{'kind':'file_exists','path':d['path'],'format':d['format']},'weight':1,'critical':True})
        mapping.append({'requirement_id':rid,'evidence_ids':refs})
    for d in task['deliverables']:relative(d['path'],'outputs')
    known_paths={a['path'] for a in graph['assets']}
    for path in re.findall(r'workspace_init/[A-Za-z0-9_./-]+',json.dumps(task)):
        path=path.rstrip('.')
        require(path in known_paths or any(p.startswith(path.rstrip('/')+'/') for p in known_paths),'task_mentions_unknown_input_path')
    visible_text(task);schema('task',task);schema('rubric',{'items':items})
    return task,{'items':items},mapping,evidence


def process_asset_workspace(directory,plan,seed,hashes,cache,output,model,stage='all'):
    record={'workspace_id':directory.name,'seed_id':seed['seed_id'],'interface':'asset-task-v1','model_calls':[]}
    try:
        report=verify_asset_workspace(directory,plan,seed)
        require(report['status']=='ready' and report['stage4_eligible'],'asset_workspace_not_ready:'+report['status'])
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return record|{'status':'blocked_upstream','reasons':[str(exc)]}
    if stage=='eligibility':return record|{'stage_complete':'eligibility'}
    c=directory/'construction';graph=read(c/'grounded_graph.json')
    try:
        evidence=evidence_graph(graph,plan)
        if stage=='evidence':return record|{'stage_complete':'evidence','evidence_graph':evidence}
        context={'raw_seed':seed,'intent_graph':plan,'grounded_graph':graph,
            'schema':read(ROOT/'config/asset_task_plan.schema.json')}
        prompt=ROOT/'prompts'/model.config.get('asset_task_prompt','asset_task.v2.txt')
        design=model(prompt.read_text(),context,prompt.stem)
        task,rubric,mapping,evidence=compile_task(design,graph,plan)
        prompt=ROOT/'prompts'/model.config.get('asset_task_review_prompt','asset_task_review.v2.txt')
        audit=model(prompt.read_text(),{
            'raw_seed':seed,'intent_graph':plan,'grounded_graph':graph,'task':task,'rubric':rubric,'requirement_mapping':mapping,
            'evidence_graph':evidence,'schema':read(ROOT/'config/asset_task_review.schema.json')},prompt.stem)
        schema('asset_task_review',audit)
        require(audit['accepted']==(all(audit['checks'].values()) and not audit['issues']),'inconsistent_task_audit')
        record.update(model_calls=model.calls,semantic_audit=audit)
        if not audit['accepted']:return record|{'status':'rejected','reasons':audit['issues']}
        if stage in ('generate','audit'):return record|{'stage_complete':stage,'task':task}
        require(verify_asset_workspace(directory,plan,seed)==report,'upstream_changed_during_task_generation')
        tid='TASK_'+digest({'task':task,'graph':graph,'rubric':rubric})[:24];target=output/tid;output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.asset-task-',dir=output) as tmp:
            d=Path(tmp);save(d/'task.json',task);save(d/'evaluation/evidence_graph.json',evidence)
            save(d/'evaluation/rubric.json',rubric);save(d/'evaluation/verifier_spec.json',compile_verifier(rubric))
            save(d/'construction/audit_report.json',record|{'requirement_mapping':mapping,'deterministic_checks':'passed'})
            for path,h in report['workspace_files'].items():
                src=confined(directory,'workspace_init/'+path);raw=src.read_bytes();require(sha256(raw)==h,'input_hash_changed')
                dest=d/'workspace_init'/relative(path);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
            sources=read(c/'source_manifest.json')['sources']
            manifest={'interface':'asset-task-v1','task_id':tid,'seed_id':seed['seed_id'],'workspace_id':directory.name,
                'status':'draft','data_provenance':'real_assets_with_synthetic_commission','upstream_hashes':hashes,
                'plan_sha256':digest(plan),'grounded_graph_sha256':digest(graph),'workspace_files':report['workspace_files'],
                'package_files':{p.relative_to(d).as_posix():sha256(p.read_bytes()) for p in d.rglob('*') if p.is_file()},
                'sources':[sources[a['file_id']] for a in graph['assets']],
                'agent_access':['task.json','workspace_init/','outputs/'],'public_redistribution_allowed':False,
                'execution_probe_performed':False,'multimodal_necessity':'not_established',
                'verification_limits':'Programmatic checks establish artifact readability only; substantive criteria require semantic/visual evaluation. No exact visual oracle or successful rollout is claimed.'}
            save(d/'manifest.json',manifest)
            if target.exists():
                require({p.relative_to(target).as_posix():sha256(p.read_bytes()) for p in target.rglob('*') if p.is_file()}==
                        {p.relative_to(d).as_posix():sha256(p.read_bytes()) for p in d.rglob('*') if p.is_file()},'existing_asset_task_changed')
            else:shutil.copytree(d,target)
        return record|{'status':'draft','task_id':tid,'package_path':str(target),'reasons':[]}
    except (ValueError,OSError,KeyError,TypeError) as exc:
        return record|{'status':'rejected','reasons':[str(exc)],'model_calls':model.calls}
