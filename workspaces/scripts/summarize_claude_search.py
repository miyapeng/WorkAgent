#!/usr/bin/env python3
"""Summarize the saved Claude Code experiments, separating discovery from grounding."""
from common import ROOT,save
from planning_common import schema


def main():
    probes=[]
    paths=[ROOT/'data/claude_search_probe/probe_glm52.json',ROOT/'data/claude_search_probe/probe_glm52_fetch.json',ROOT/'data/claude_search_probe/raw_31_0_21094/probe_report.json']
    for p in paths:
        d=schema(p);t=d['trace']
        probes.append({'record':str(p.relative_to(ROOT)),'seed_id':d['seed_id'],'websearch_calls':t['websearch_calls'],
                       'webfetch_calls':t['webfetch_calls'],'unique_candidate_urls':len(t['candidates']),
                       'fetch_results':[r for r in t['tool_results'] if r['name']=='WebFetch'],
                       'billed_cost':None,'cli_cost_estimate_usd':t['final'].get('total_cost_usd')})
    pilot=schema(ROOT/'data/claude_search_pilot/pilot_report.json')
    workspace=pilot['workspaces'][0]
    folder=ROOT/'data/claude_search_pilot'/workspace['workspace_id']/'construction'
    trace=schema(folder/'search_trace.json');manifest=schema(folder/'source_manifest.json')
    events=trace['events']
    report={'scope':'Actual Claude Code + existing LLMCenter inference credential; no separate Search API key.',
            'model_requested':'GLM_ka48dn','claude_code_version':'2.1.299','probes':probes,
            'observed_websearch_calls':sum(p['websearch_calls'] for p in probes)+sum(e.get('tool_websearch_calls',0) for e in events),
            'observed_webfetch_calls':sum(p['webfetch_calls'] for p in probes)+sum(e.get('tool_webfetch_calls',0) for e in events),
            'underlying_search_backend_requests':None,
            'stage3':{'seed_id':workspace['seed_id'],'status':workspace['status'],'counts':workspace['counts'],
                      'selected_anchor':workspace['selected_anchor'],'failure_reasons':workspace['failure_reasons'],
                      'actual_downloads':[{'url':s['final_url'],'sha256':s['sha256'],'bytes':s['bytes'],'mime':s['mime'],'retrieved_at':s['retrieved_at'],'license_status':s['license_status']} for s in manifest['sources'].values()]},
            'billed_cost':None,
            'limitations':['A logged WebSearch invocation and returned URLs do not establish source relevance or truthful source contents.',
                           'The gateway/backend search implementation and underlying request count are not independently visible.',
                           'Many returned URLs are broad pages or appear truncated; URLs were not completed by guessing.',
                           'Client total_cost_usd is not a verified LLMCenter invoice; tool calls may consume inference quota.',
                           'Search snippets, WebFetch summaries and final model narratives never establish programmatic information coverage.',
                           'This experiment did not produce a ready Workspace or verified multimodal evidence.']}
    save(ROOT/'data/claude_search_pilot/experiment_report.json',report)
    print({'websearch_calls':report['observed_websearch_calls'],'webfetch_calls':report['observed_webfetch_calls'],'workspace':workspace['status']})


if __name__=='__main__':main()
