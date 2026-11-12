#!/usr/bin/env python3
"""Reparse two historical real downloads, without treating them as new search success."""
from pathlib import Path
from common import ROOT,sha256,save
from planning_common import schema
from profile_files import profile
from coverage import resolve_refs


def run():
    cache=ROOT/'data/cache';output=[]
    patterns=['eav_eac_en.csv','HMRC_Government_Major_Projects_Portofolio_AR_Data_March_2024.xlsx']
    for pattern in patterns:
        receipts=[schema(p) for p in (cache/'downloads').glob('*.json')]
        source=next((r for r in receipts if r.get('original_url','').endswith(pattern) and r.get('sha256')),None)
        if source is None:output.append({'source_suffix':pattern,'status':'cache_missing','new_search_requests':0});continue
        blob=cache/'blobs'/source['sha256'];assert sha256(blob.read_bytes())==source['sha256']
        p=profile(blob,source['final_url'],source['mime'],ROOT/'data/cache_graph')
        assert p['parse_status']=='parsed';fid=p['file_id'];refs=[{'file_id':fid,'segment_id':s['segment_id']} for s in p['segments'][:3]]
        restored=resolve_refs(refs,{fid:p});assert all(r['quote']==s['text'] and r['locator']==s['locator'] for r,s in zip(restored,p['segments']))
        output.append({'source_url':source['original_url'],'original_retrieved_at':source['retrieved_at'],'sha256':source['sha256'],
                       'status':'passed','file_type':p['type'],'segments':len(p['segments']),'checked_locators':[r['locator'] for r in restored],
                       'new_search_requests':0,'new_downloads':0,'semantic_coverage':'not_asserted','usage':'Real cached-source parser and stable-ID regression only, not a new pilot anchor.'})
    report={'real_cached_regressions':output,'does_not_increase_pilot_ready_or_anchor_counts':True}
    save(ROOT/'data/generated/regression_report.json',report);print(report)
if __name__=='__main__':run()
