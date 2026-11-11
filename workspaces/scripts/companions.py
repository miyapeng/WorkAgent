"""Opt-in rendering of reviewed companion specifications, never silent fallback data."""
import csv
import io
import json
from pathlib import Path
from common import require, safe_relative, sha256
from profile_files import parse_bytes
from coverage import validate_origin


def render_companions(spec, plan, coverage, cache):
    require(coverage['usable_real_anchors'],'synthetic_requires_inspected_real_anchor')
    require(coverage['completion']['safe'] is True,'completion_not_safe')
    require(isinstance(spec,dict) and set(spec)=={'seed_id','plan_sha256','fictional_case','files'},'companion_spec_schema')
    from common import json_bytes
    require(spec['seed_id']==plan['seed_id'] and spec['plan_sha256']==sha256(json_bytes(plan)),'companion_plan_mismatch')
    require(isinstance(spec['fictional_case'],str) and spec['fictional_case'].startswith('Fictional '),'explicit_fictional_identity_required')
    require(isinstance(spec['files'],list) and 0<len(spec['files'])<=2,'companion_file_limit')
    missing={r['node_id'] for r in coverage['nodes'] if r['status']!='supported'}
    allowed=set(coverage['completion']['target_nodes']) & missing
    records=[]; profiles=[]
    for item in spec['files']:
        require(set(item)=={'filename','target_nodes','format','content'},'companion_file_schema')
        targets=item['target_nodes']
        require(isinstance(targets,list) and len(targets)==1 and set(targets)<=allowed,'companion_must_target_one_explicit_gap')
        filename=safe_relative(item['filename'])
        require(len(filename.parts)==1 and filename.name.startswith('SYNTHETIC_'),'synthetic_filename_disclosure')
        if item['format']=='json':
            require(filename.suffix=='.json' and isinstance(item['content'],dict),'companion_json_schema')
            body={'provenance':'SYNTHETIC SCENARIO INPUT; not records of any real organization.',
                  'case':spec['fictional_case'],'facts':item['content']}
            raw=(json.dumps(body,ensure_ascii=False,indent=2)+'\n').encode(); mime='application/json'
        elif item['format']=='csv':
            require(filename.suffix=='.csv' and isinstance(item['content'],dict)
                    and set(item['content'])=={'columns','rows'},'companion_csv_schema')
            value=item['content']; require(all(len(r)==len(value['columns']) for r in value['rows']),'companion_ragged_rows')
            out=io.StringIO(); writer=csv.writer(out)
            writer.writerow(['provenance','case']+value['columns'])
            for row in value['rows']: writer.writerow(['SYNTHETIC; not real business records',spec['fictional_case']]+row)
            raw=out.getvalue().encode(); mime='text/csv'
        else: raise ValueError('unsupported_companion_format')
        require(len(raw)<=100000,'companion_size_limit')
        p=parse_bytes(raw,'https://synthetic.invalid/'+filename.name,mime)
        require(not p['risk_signals'],'companion_contains_pii_or_answer_markers')
        blob=cache/'blobs'/sha256(raw); blob.parent.mkdir(parents=True,exist_ok=True); blob.write_bytes(raw)
        source={'file_id':p['file_id'],'sha256':sha256(raw),'origin':'synthetic','filename':filename.name,
                'anchor_file_ids':coverage['usable_real_anchors'],'target_nodes':targets,'fictional_case':spec['fictional_case'],
                'download_status':'not_applicable','license':{'status':'project_generated','redistribution_allowed':False},
                'generation_method':'reviewed_structured_facts_rendered_by_python'}
        validate_origin(source); p['origin']='synthetic'
        records.append(source); profiles.append(p)
    return records,profiles
