"""Explicit STATS19 pilot reference adapter. Recompute from frozen source bytes.

No solver outputs are used to create references. These statistics do not prove
professional accuracy, complete codebook compliance, or representativeness.
"""
import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path
from task_common import require, sha256


def stats19(workspace):
    workspace=Path(workspace);metrics={};details={};records={};sources={}
    for table in ('collision','vehicle','casualty'):
        paths=list(workspace.rglob('*statistics-'+table+'-2024.csv'))
        require(len(paths)==1,'stats19_reference_input_missing:'+table)
        path=paths[0];sources[table]={'path':path.relative_to(workspace).as_posix(),'sha256':sha256(path.read_bytes())}
        with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
        require(rows,'empty_reference_table');records[table]=rows
        fields=list(rows[0]);key=['collision_index']+(['vehicle_reference'] if table=='vehicle' else ['casualty_reference'] if table=='casualty' else [])
        counts=Counter(tuple(row[k] for k in key) for row in rows)
        def put(name,value,definition,unit='records',tolerance=0):
            metrics[table+'.'+name]={'value':str(value),'unit':unit,'definition':definition,'absolute_tolerance':tolerance}
        put('rows',len(rows),'All data rows excluding the CSV header; no filters or exclusions.')
        put('duplicate_key_excess',sum(n-1 for n in counts.values()),'Rows minus unique '+str(key)+' tuples.')
        put('wrong_year',sum(r['collision_year']!='2024' for r in rows),'Rows whose collision_year is not the literal 2024.')
        missing={f:{'empty':sum(r[f]=='' for r in rows),'minus_one':sum(r[f]=='-1' for r in rows)} for f in fields}
        freq={f:dict(Counter(r[f] for r in rows)) for f in fields if f in ('collision_severity','casualty_severity','vehicle_type','collision_injury_based','casualty_injury_based','collision_year')}
        details[table]={'columns':fields,'key':key,'missing_raw_codes':missing,'frequencies':freq,
                        'missing_note':'Empty and -1 are counted separately. Other missing/not-applicable codes require codebook interpretation.'}
        for f in fields:
            if '_adjusted_severity_' in f:
                values=[Decimal(r[f]) for r in rows if r[f] not in ('','-1')]
                valid=[v for v in values if 0<=v<=1]
                put(f+'.valid_probability_rows',len(valid),'Nonempty, non -1 numeric values in [0,1].')
                put(f+'.sum',sum(valid,Decimal(0)),'Sum of valid [0,1] adjustment probabilities, not raw record count.','expected_records',0.01)
                put(f+'.out_of_range',sum(v<0 or v>1 for v in values),'Numeric values outside [0,1], excluding -1 sentinel.')
        severity=table+'_severity'
        if severity in fields:
            adjustment=[f for f in fields if '_adjusted_severity_' in f]
            details[table]['adjustments_by_fatal_status']={}
            for group,predicate in [('fatal',lambda r:r[severity]=='1'),('nonfatal',lambda r:r[severity] in ('2','3'))]:
                selected=[r for r in rows if predicate(r)]
                detail={'rows':len(selected),'fields':{}}
                for f in adjustment:
                    counts=Counter(r[f] for r in selected)
                    detail['fields'][f]={'empty':counts[''],'minus_one':counts['-1'],'zero':counts['0'],'one':counts['1'],
                                         'nonempty':len(selected)-counts[''],'value_counts':dict(counts) if group=='fatal' else None}
                    put(f+'.'+group+'_empty',counts[''],'Empty strings in '+f+' among '+group+' rows, defined by '+severity+'.')
                    put(f+'.'+group+'_zero',counts['0'],'Literal zero in '+f+' among '+group+' rows, defined by '+severity+'.')
                if len(adjustment)==2:
                    detail['pair_sum_not_one']=sum(abs(sum(Decimal(r[f]) for f in adjustment)-1)>Decimal('0.0001') for r in selected if all(r[f] not in ('','-1') for f in adjustment))
                details[table]['adjustments_by_fatal_status'][group]=detail

        if severity in fields:
            for level,n in Counter(r[severity] for r in rows).items():
                put('severity_'+level,n,'Raw rows with '+severity+'='+level+'.')
    collision_keys={r['collision_index'] for r in records['collision']}
    vehicle_keys={(r['collision_index'],r['vehicle_reference']) for r in records['vehicle']}
    for table in ('vehicle','casualty'):
        n=sum(r['collision_index'] not in collision_keys for r in records[table])
        metrics[table+'.unmatched_collision']={'value':str(n),'unit':'records','absolute_tolerance':0,'definition':'Child rows whose collision_index does not occur in collision table; no filters.'}
    n=sum((r['collision_index'],r['vehicle_reference']) not in vehicle_keys for r in records['casualty'])
    metrics['casualty.unmatched_vehicle']={'value':str(n),'unit':'records','absolute_tolerance':0,'definition':'Casualty rows with no matching (collision_index, vehicle_reference) in vehicle table.'}
    for table,field in [('vehicle','number_of_vehicles'),('casualty','number_of_casualties')]:
        actual=Counter(r['collision_index'] for r in records[table])
        n=sum(int(r[field])!=actual[r['collision_index']] for r in records['collision'])
        metrics['collision.'+field+'_mismatch']={'value':str(n),'unit':'collisions','absolute_tolerance':0,'definition':'Collision rows whose stated '+field+' differs from linked child-row count.'}
    return {'adapter':'stats19-2024-v2','sources':sources,'metrics':metrics,'details':details,
            'scope':'independently_computed_subset_not_complete_professional_oracle'}
