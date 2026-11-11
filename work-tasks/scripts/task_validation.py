"""Structural alignment first, independent model judgment second; neither bypasses the other."""
from task_common import *
from task_evidence import verify_graph
from task_verifier import validate_spec


def validate_proposal(value,graph,snapshot):
    schema('proposal',value);verify_graph(graph,snapshot)
    task=value['task'];visible_text(task)
    plan=snapshot['plan']; info={n['id']:n for n in plan['information_nodes']}
    facts=unique(graph['nodes'],'evidence_id')
    requirements=unique(task['requirements'],'requirement_id')
    delivers=unique(task['deliverables'],'deliverable_id')
    require(len({d['path'] for d in delivers.values()})==len(delivers),'duplicate_deliverable_path')
    plan_outputs={d['id'] for d in plan['deliverables']}
    require({d['plan_deliverable_id'] for d in delivers.values()}==plan_outputs,'plan_deliverables_not_preserved')
    for d in delivers.values():
        path=relative(d['path'],'outputs');require(path.suffix.lower()=='.'+d['format'],'deliverable_extension_mismatch')
    grounding=unique(value['grounding'],'requirement_id')
    require(set(grounding)==set(requirements),'requirements_without_grounding')
    rubrics=unique(value['rubric']['items'],'rubric_id')
    descriptions=set();specs=set();covered_info=set();covered_deliverables=set()
    def ancestors(node):
        found={node}; pending=[node]
        while pending:
            current=pending.pop()
            for a,b in plan['dependencies']:
                if b==current and a not in found: found.add(a);pending.append(a)
        return found
    for rid,r in requirements.items():
        require(set(r['information_node_ids'])<=set(info),'unrelated_information_requirement')
        require(set(r['deliverable_ids'])<=set(delivers),'unknown_requirement_deliverable')
        covered_info.update(r['information_node_ids']); covered_deliverables.update(r['deliverable_ids'])
        refs=grounding[rid]['evidence_ids'];require(set(refs)<=set(facts),'invalid_evidence_id')
        supported_info=set().union(*(ancestors(n) for n in r['information_node_ids']))
        require(all(facts[e]['information_node_id'] in supported_info for e in refs),'requirement_evidence_unrelated_to_information')
        require(any(facts[e]['type']=='source_fact' for e in refs),'requirement_without_source_fact')
        own=[x for x in rubrics.values() if x['requirement_id']==rid]
        require(bool(own) or bool(r['unscored_reason']),'unscored_requirement_without_reason')
        require(not own or r['unscored_reason'] is None,'scored_requirement_marked_unscored')
    core={n['id'] for n in info.values() if n['type']!='external_input'}
    require(core<=covered_info,'core_intent_information_omitted')
    require(covered_deliverables==set(delivers),'unrequired_deliverable')
    for r in rubrics.values():
        rid=r['requirement_id'];require(rid in requirements,'rubric_outside_task')
        require(set(r['evidence_ids'])<=set(grounding[rid]['evidence_ids']),'rubric_evidence_not_task_grounding')
        require(any(facts[e]['type']=='source_fact' for e in r['evidence_ids']),'rubric_without_source_fact')
        key=' '.join(r['requirement'].lower().split())
        require(key not in descriptions,'duplicate_rubric_requirement');descriptions.add(key)
        key=digest(r['verification_spec']);require(key not in specs,'duplicate_verification_spec');specs.add(key)
        if r['verification_type']=='process':require(requirements[rid]['kind']=='constraint','process_without_task_constraint')
        validate_spec(r,graph,snapshot,{d['path']:d for d in delivers.values()})
    # Paths mentioned in natural language must also name actual visible inputs / declared outputs.
    import re
    allowed={s['workspace_path'] for s in snapshot['sources'].values()} | {d['path'] for d in delivers.values()}
    for path in re.findall(r'(?:workspace_init|outputs)/[A-Za-z0-9_./-]+',json.dumps(task)):
        require(path.rstrip('.') in allowed,'instruction_invented_file_path')
    return {'passed':True,'requirements':len(requirements),'rubrics':len(rubrics),'source_facts':sum(f['type']=='source_fact' for f in facts.values())}


def validate_audit(audit,proposal,graph):
    schema('audit',audit)
    requirements=unique(proposal['task']['requirements'],'requirement_id')
    rubrics=unique(proposal['rubric']['items'],'rubric_id');facts=unique(graph['nodes'],'evidence_id')
    ar=unique(audit['requirements'],'requirement_id');br=unique(audit['rubrics'],'rubric_id')
    require(set(ar)==set(requirements) and set(br)==set(rubrics),'audit_reverse_review_incomplete')
    ground={g['requirement_id']:set(g['evidence_ids']) for g in proposal['grounding']}
    for rid,row in ar.items(): require(set(row['evidence_ids'])<=ground[rid],'audit_requirement_evidence_mismatch')
    for bid,row in br.items():
        require(row['requirement_id']==rubrics[bid]['requirement_id'],'audit_rubric_requirement_mismatch')
        require(set(row['evidence_ids'])<=set(rubrics[bid]['evidence_ids']),'audit_rubric_evidence_mismatch')
    decisions=list(audit['dimensions'].items())+list(ar.items())+list(br.items())
    for _,row in decisions:
        require(set(row['evidence_ids'])<=set(facts),'audit_unknown_evidence')
        require(any(facts[e]['type']=='source_fact' for e in row['evidence_ids']),'audit_missing_source_evidence')
    return {'passed':all(row['passed'] for _,row in decisions),
            'failures':[{'check':key,'reason':row['reason']} for key,row in decisions if not row['passed']],
            'qualification':'Independent model call, not independent expert certification; execution not tested.'}
