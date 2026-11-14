#!/usr/bin/env python3
"""Summarize recorded Agent retrieval and inspect cached bytes, without new network calls."""
import argparse
import csv
import io
from common import ROOT,save,require,sha256,json_bytes
from planning_common import schema


def summarize(output,cache,baseline,config_path):
    report=schema(output/'pilot_report.json')['workspaces'][0]
    config=schema(config_path)
    require(sha256(json_bytes(config))==report['config_sha256'],'comparison_config_changed')
    private=output/report['workspace_id']/'construction'
    trace=schema(private/'agent_trace.json')
    profiles={p['file_id']:p for p in schema(private/'file_profiles.json')}
    files=[]
    for fid,source in schema(private/'source_manifest.json')['sources'].items():
        raw=(cache/'blobs'/source['sha256']).read_bytes()
        require(sha256(raw)==source['sha256'],'downloaded_bytes_changed')
        item={k:source[k] for k in ('url','final_url','sha256','mime','bytes','license_status')}
        item['profile_type']=profiles[fid]['type']
        if raw.startswith(b'%PDF-'):
            item.update(actual_format_check='pdf_magic_and_parser',pages=profiles[fid]['structure']['pages'])
        elif '/ogpvp_download/csv/' in source['final_url']:
            rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
            require(len(rows)>1 and len(rows[0])>1 and all(len(r)==len(rows[0]) for r in rows),'endpoint_not_valid_rectangular_csv')
            item.update(actual_format_check='csv_rows_independently_parsed',data_rows=len(rows)-1,columns=rows[0])
        else:item['actual_format_check']=profiles[fid]['type']+'_parsed'
        files.append(item)
    original=schema(baseline/'pilot_report.json')['workspaces'][0]
    require(original['blueprint_sha256']==report['blueprint_sha256'],'comparison_blueprint_mismatch')
    result={'seed_id':report['seed_id'],'blueprint_sha256':report['blueprint_sha256'],
        'baseline':{'web_search':original['counts']['actual_search_requests'],'web_fetch':0,
                    'downloaded_files':original['counts']['downloaded_urls'],'status':original['status']},
        'agent':{'runtime':'Claude Code','model_requested':trace['run']['model_requested'],
                 'observed_web_search':trace['trace']['websearch_calls'],'observed_web_fetch':trace['trace']['webfetch_calls'],
                 'elapsed_seconds':trace['run']['elapsed_seconds'],'stop_reason':trace['trace']['final']['subtype'],
                 'configured_search_budget':config['search'].get('max_search_calls'),'configured_fetch_budget':config['search'].get('max_fetch_calls'),
                 'budget_overrun':any(config['search'].get(limit) is not None and trace['trace'][count]>config['search'][limit] for count,limit in [('websearch_calls','max_search_calls'),('webfetch_calls','max_fetch_calls')]),
                 'cli_cost_estimate_usd':trace['trace']['final'].get('total_cost_usd'),'billed_cost':None},
        'tool_free_closeout':{'additional_search_calls':0,'model_calls':report['model_usage'],'downloads':files,
                              'counts':report['counts'],'status':report['status'],'failure_reasons':report['failure_reasons']},
        'limits':['Same seed and blueprint, but different context, tool workflow and budget; no causal or generalization claim.',
                  'Observed tool calls do not identify underlying search backend request counts.',
                  'WebFetch summaries are provisional; downloads and actual hrefs were independently checked.',
                  'No ready workspace, synthetic data, Agent Probe or training admission.',
                  'Downloaded bytes and full profiles/audits remain private. MIME-mislabeled CSVs are parsed as text by the current profiler; this report separately verifies their CSV structure.']}
    save(output/'experiment_report.json',result)
    return result


if __name__=='__main__':
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,default=ROOT/'data/claude_agent_closeout')
    p.add_argument('--cache-dir',type=Path,default=ROOT/'data/cache_claude_agent')
    p.add_argument('--baseline',type=Path,default=ROOT/'data/world_pilot/real')
    p.add_argument('--config',type=Path,default=ROOT/'config/claude_agent_closeout.json')
    a=p.parse_args();r=summarize(a.output_dir,a.cache_dir,a.baseline,a.config)
    print(r['tool_free_closeout']['counts'])
