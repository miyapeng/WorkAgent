"""Compile asset bindings without inventing premises, locations or perceptual truth."""
from common import ROOT, require, sha256, json_bytes
from planning_common import schema, validate


def case_schema(plan):
    spec=schema(ROOT/'config/asset_case.schema.json')
    groups={'inputs':[n['id'] for n in plan['information_nodes'] if n['type']=='external_input'],
            'operations':[n['id'] for n in plan['information_nodes'] if n['type']!='external_input'],
            'deliverables':[d['id'] for d in plan['deliverables']]}
    for group,ids in groups.items():
        field=spec['properties'][group];field.update(minItems=len(ids),maxItems=len(ids))
        field['items']['properties']['node_id']={'enum':ids}
    return spec


def assemble_case(value,plan):
    """Project contract fields; unused model notes remain in the raw receipt.

    Missing professional fields still fail. Only the non-applicable instruction
    slot defaults to None; an instruction-channel input cannot pass that way.
    """
    def project(v,spec):
        if isinstance(v,list):return [project(x,spec.get('items',{})) for x in v]
        if isinstance(v,dict):
            return {k:project(v[k],child) for k,child in spec.get('properties',{}).items() if k in v}
        return v
    result=project(value,case_schema(plan))
    for b in result.get('inputs',[]):b.setdefault('instruction',None)
    return result


def model_handles(views,sources):
    """Short local citation handles; canonical IDs and locations remain untouched."""
    fs={fid:'file'+str(i) for i,fid in enumerate(sorted(views),1)}
    ss={s['segment_id']:'s'+str(i) for i,s in enumerate((s for fid in sorted(views) for s in views[fid]['segments']),1)}
    forward=fs|ss;reverse={v:k for k,v in forward.items()}
    def encode(v):
        if isinstance(v,dict):return {forward.get(k,k):encode(x) for k,x in v.items()}
        if isinstance(v,list):return [encode(x) for x in v]
        return forward.get(v,v) if isinstance(v,str) else v
    def decode(v):
        if isinstance(v,dict):return {k:(reverse.get(x,x) if k in ('file_id','segment_id') and isinstance(x,str) else decode(x)) for k,x in v.items()}
        if isinstance(v,list):return [decode(x) for x in v]
        return v
    return encode(list(views.values())),encode(sources),decode


def compile_binding(case, plan, profiles, sources):
    validate(case, case_schema(plan))
    nodes={n['id']:n for n in plan['information_nodes']}
    inputs={k:n for k,n in nodes.items() if n['type']=='external_input'}
    operations=set(nodes)-set(inputs)
    require(len(case['inputs'])==len(inputs) and {b['node_id'] for b in case['inputs']}==set(inputs),'case_input_set_changed')
    require(len(case['operations'])==len(operations) and {o['node_id'] for o in case['operations']}==operations,'case_operation_set_changed')
    outputs={d['id']:d for d in plan['deliverables']}
    require(len(case['deliverables'])==len(outputs) and {d['node_id'] for d in case['deliverables']}==set(outputs),'case_deliverable_set_changed')
    bindings=[]; used=set()
    for b in case['inputs']:
        n=inputs[b['node_id']];refs=[];seen=set()
        for ref in b['references']:
            fid,sid=ref['file_id'],ref['segment_id']
            require((fid,sid) not in seen,'duplicate_binding_reference');seen.add((fid,sid))
            require(fid in profiles and fid in sources,'unknown_asset_id')
            p=profiles[fid];require(p['parse_status']=='parsed','unparsed_asset')
            require(p['sha256']==sources[fid]['sha256'],'asset_source_hash_mismatch')
            matches=[s for s in p['segments'] if s['segment_id']==sid]
            require(len(matches)==1,'unknown_segment_id');s=matches[0]
            refs.append({'file_id':fid,'segment_id':sid,'locator':s['locator'],'content':s['text'],
                         'verification_status':s['verification_status'],'evidence_method':s['evidence_method'],
                         **{k:s[k] for k in ('box','image_sha256','timestamp_seconds','frame_sha256') if k in s}})
            used.add(fid)
        instruction=n['supply_channel']=='task_instruction'
        if instruction:
            # References may motivate a hypothetical commission (e.g. reference
            # image dimensions); origin remains synthetic_instruction, not fact.
            require(b['status']!='supported' or bool(b['instruction']),'missing_instruction_value')
        else:
            require(b['instruction'] is None,'synthetic_fact_in_real_input')
            require(b['status']!='supported' or refs,'supported_without_asset')
            if b['status']=='supported' and set(n.get('modality_candidates',[])) & {'image','spatial','video'}:
                require(any(r['evidence_method']=='model_visual_observation' for r in refs),'visual_input_not_inspected')
            require(b['status']!='supported' or 'audio' not in n.get('modality_candidates',[]),'audio_content_not_inspected')
        bindings.append({'information_node_id':b['node_id'],'status':b['status'],'references':refs,
                         'instruction':b['instruction'],'origin':'synthetic_instruction' if instruction else 'real_original',
                         'rationale':b['rationale']})
    require(used,'no_real_anchor')
    # Formats are preferences. Choosing an actual format changes no professional operation.
    from compile_blueprint import VOCABULARY
    allowed={f for fs in VOCABULARY['deliverables'].values() for f in fs}
    for d in case['deliverables']:require(d['format'] in allowed,'unsupported_case_output_format')
    graph={'interface':'asset-grounded-graph-v1','seed_id':plan['seed_id'],
           'blueprint_sha256':sha256(json_bytes(plan)),'case_title':case['case_title'],'case_objective':case['case_objective'],
           'assets':[{'file_id':fid,'path':sources[fid]['workspace_path'],'sha256':sources[fid]['sha256']} for fid in sorted(used)],
           'bindings':bindings,'operations':case['operations'],'deliverables':case['deliverables'],
           'dependencies':plan['dependencies'],'limitations':case['limitations']}
    validate(graph,schema(ROOT/'config/grounded_graph.schema.json'))
    return graph


def binding_gaps(graph,plan):
    critical={n['id'] for n in plan['information_nodes'] if n['type']=='external_input' and n['critical']}
    return [b['information_node_id'] for b in graph['bindings'] if b['information_node_id'] in critical and b['status']!='supported']


def validate_review(review):
    validate(review,schema(ROOT/'config/asset_review.schema.json'))
    require(review['accepted']==(all(review['checks'].values()) and not review['issues']),'inconsistent_case_review')
    return review['accepted']
