"""Full-context Claude Code retrieval session + independently verified acquisition.

The Agent chooses queries, fetches and candidate cases. Python verifies actual link
discovery, bytes, profiles and the existing real-workspace coverage gates.
"""
from html.parser import HTMLParser
import json
from urllib.parse import urljoin
import re

from common import ROOT, DataError, require, sha256, json_bytes, save
from planning_common import schema, validate, load_llm, model_call, usage
from claude_search import run_session
from acquire import download, public_url
from profile_files import profile
from coverage import external_nodes, empty_coverage, check_audit


def agent_context(plan,seed,config):
    return {'raw_seed':seed,'approved_blueprint':plan,
            'retrievable_node_ids':[n['id'] for n in external_nodes(plan)],
            'budget':{'web_search_calls':config['search'].get('max_search_calls'),
                      'web_fetch_calls':config['search'].get('max_fetch_calls'),
                      'total_selected_files':config['limits']['selected_files']}}


def retrieve(plan,seed,config,cache,offline=False):
    prompt=(ROOT/'prompts'/config.get('retrieval_prompt','claude_retrieval_agent.v1.txt')).read_text()+'\nINPUT:\n'+json.dumps(agent_context(plan,seed,config),ensure_ascii=False,sort_keys=True)
    key=sha256(json_bytes({'prompt':prompt,'search_config':config['search']}))
    receipt=cache/'agent_sessions'/(key+'.json')
    if receipt.exists():
        stored=schema(receipt)
        require(stored['receipt_sha256']==sha256(json_bytes(stored['result'])),'agent_receipt_changed')
        return stored['result']
    require(not offline,'offline_agent_receipt_missing')
    report,trace=run_session(prompt,config['search'],cache/'sessions',offline)
    result={'run':report,'trace':trace}
    save(receipt,{'result':result,'receipt_sha256':sha256(json_bytes(result))})
    return result


def closeout(receipt,plan,seed,config,config_path,cache,offline):
    """One tool-free handoff of observed results; never erases failed session status."""
    original=cache/'sessions'/receipt['run']['request_sha256']/'stdout.jsonl'
    observations=[]
    for line in original.read_text().splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        if row.get('type')!='user':continue
        for block in row.get('message',{}).get('content',[]):
            if block.get('type')!='tool_result':continue
            content=block.get('content','')
            text=content if isinstance(content,str) else json.dumps(content,ensure_ascii=False)
            observations.append({'tool_use_id':block['tool_use_id'],'is_error':block.get('is_error',False),
                                 'text':text[:6000],'truncated':len(text)>6000})
    require(sha256(original.read_bytes())==receipt['run']['transcript_sha256'],'claude_transcript_hash_changed')
    value,meta=model_call(load_llm(config,config_path,offline),ROOT/'prompts/agent_handoff.v1.txt',{
        **agent_context(plan,seed,config), 'tool_calls':receipt['trace']['tool_calls'],
        'tool_observations':observations,'schema':schema(ROOT/'config/agent_retrieval.schema.json')},cache,offline)
    return {'decision':value,'model_metadata':meta,'kind':'tool_free_closeout_of_incomplete_session'}


def parse_decision(receipt,plan,config):
    report,trace=receipt['run'],receipt['trace']
    if receipt.get('handoff'):
        require(config.get('closeout_after_incomplete'),'handoff_not_enabled')
        decision=receipt['handoff']['decision']
    else:
        require(not report['timed_out'] and report['returncode']==0 and not trace['final'].get('is_error'), 'agent_session_incomplete')
        for count,limit in (('websearch_calls','max_search_calls'),('webfetch_calls','max_fetch_calls')):
            maximum=config['search'].get(limit)
            require(maximum is None or trace[count]<=maximum,'agent_budget_exceeded')
        text=trace['final'].get('result','').strip()
        # CLI may prefix its single structured handoff with a short explanation.
        # Extract exactly one fenced JSON value; never guess between multiple blocks.
        blocks=re.findall(r"```(?:json)?\s*\n(.*?)\n```",text,re.S)
        if blocks:
            require(len(blocks)==1,'ambiguous_agent_json_blocks')
            text=blocks[0].strip()
        try:decision=json.loads(text)
        except ValueError:
            # A single JSON object after plain introductory prose is still an
            # unambiguous handoff. No bracket repair or model content changes.
            start=re.search(r'(?m)^\{',text)
            require(start is not None,'agent_result_not_json')
            try:
                decision,end=json.JSONDecoder().raw_decode(text[start.start():])
                require(not text[start.start()+end:].strip(),'ambiguous_agent_json_tail')
            except ValueError:raise DataError('agent_result_not_json')
    validate(decision,schema(ROOT/'config/agent_retrieval.schema.json'))
    nodes={n['id'] for n in external_nodes(plan)}
    require(sum(len(c['files']) for c in decision['cases'])<=config['limits']['selected_files'],'selected_file_budget_exceeded')
    for case in decision['cases']:
        urls=[]
        for f in case['files']:
            urls.append(public_url(f['url']));public_url(f['source_page'])
            require(set(f['target_node_ids'])<=nodes,'candidate_targets_non_retrievable_node')
        require(len(urls)==len(set(urls)),'duplicate_case_url')
    return decision


def actual_links(raw,final_url):
    """Extract actual HTML hrefs, including download endpoints without extensions."""
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.links=set()
        def handle_starttag(self,tag,attrs):
            if tag!='a':return
            href=dict(attrs).get('href')
            if not href:return
            try:self.links.add(public_url(urljoin(final_url,href)))
            except ValueError:pass
    parser=Links();parser.feed(raw.decode('utf-8-sig',errors='replace'));return parser.links


class Acquisition:
    def __init__(self,trace,config,cache,offline):
        self.known={public_url(c['url']):{'method':'WebSearch_tool_result','tool_use_id':c['discovered_by_tool_use_id']} for c in trace['candidates']}
        # Agents may navigate an official homepage directly. A matched tool visit is
        # a candidate acquisition attempt, not evidence or a claimed search result.
        # Python must still fetch the URL and inspect real bytes; assistant prose
        # alone never establishes this provenance.
        for result in trace.get('tool_results',[]):
            if result['name']=='WebFetch' and result.get('page_access_status')=='tool_response_requires_independent_download_check' and result['input'].get('url'):
                url=public_url(result['input']['url'])
                self.known.setdefault(url,{'method':'WebFetch_attempt_requires_independent_http_verification','tool_use_id':result['tool_use_id']})
        self.config=config;self.cache=cache;self.offline=offline;self.downloaded={};self.attempted=set();self.events=[];self.discovery_attempts=0

    def get(self,url,role):
        url=public_url(url)
        require(url in self.known,'url_not_observed_in_search_or_actual_href')
        if url in self.downloaded:return self.downloaded[url]
        require(url not in self.attempted,'prior_download_failed')
        if role=='discovery_page':
            require(self.discovery_attempts<self.config['limits']['discovery_pages'],'discovery_page_budget_exhausted')
            self.discovery_attempts+=1
        self.attempted.add(url)
        try:
            raw,transport=download(url,self.cache,self.config['limits'],self.offline)
            record={'url':url,'role':role,'status':'downloaded',**transport,'discovery':self.known[url]}
            self.events.append(record);self.downloaded[url]=(raw,transport)
            # A redirect to a directory is recorded as such, never upgraded to PDF by title.
            if transport['mime'].split(';')[0] in ('text/html','application/xhtml+xml'):
                for target in actual_links(raw,transport['final_url']):
                    self.known.setdefault(target,{'method':'actual_html_href','source_page':transport['final_url'],
                                                  'source_sha256':transport['sha256']})
            self.known.setdefault(public_url(transport['final_url']),self.known[url])
            return raw,transport
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.events.append({'url':url,'role':role,'status':'failed','reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__})
            raise

    def discover_fetch_chain(self,trace,files):
        # Fetch summaries cannot prove an href. Re-read the pages in discovery order.
        pending=list(dict.fromkeys([f['source_page'] for f in files if public_url(f['url']) not in self.known]+
            [c['input']['url'] for c in trace['tool_calls'] if c['name']=='WebFetch' and c['input'].get('url')]))
        pending=[public_url(u) for u in pending]
        wanted={public_url(f['url']) for f in files}
        while pending and not wanted<=self.known.keys():
            progress=False
            for url in list(pending):
                if wanted<=self.known.keys():break
                if url not in self.known:continue
                pending.remove(url);progress=True
                try:self.get(url,'discovery_page')
                except (OSError,ValueError,KeyError,TypeError):pass
            if not progress:break


def build_agent(plan,seed,config,config_path,cache,directory,offline=False,stage='all'):
    from construct_workspace import profile_view,assemble,verify_workspace
    require(stage=='all','agent_mode_supports_all_or_verify_only')
    construction=directory/'construction';sources={};profiles={};calls=[];failures=[];audits=[]
    coverage=empty_coverage(plan,'agent_not_completed');receipt=None;decision=None;acquisition=None
    try:
        receipt=retrieve(plan,seed,config,cache,offline)
        save(construction/'agent_trace.json',receipt)
        if config.get('closeout_after_incomplete') and (receipt['run']['timed_out'] or receipt['trace']['final'].get('subtype')=='error_max_turns'):
            failures.append({'stage':'agent_retrieval','reason':'original_session_incomplete_handoff_for_inspection_only'})
            receipt['handoff']=closeout(receipt,plan,seed,config,config_path,cache,offline)
            calls.append(receipt['handoff']['model_metadata'])
            save(construction/'agent_handoff.json',receipt['handoff'])
        decision=parse_decision(receipt,plan,config)
        save(construction/'agent_decision.json',decision)
        acquisition=Acquisition(receipt['trace'],config,cache,offline)
        requested=[f for c in decision['cases'] for f in c['files']]
        acquisition.discover_fetch_chain(receipt['trace'],requested)
        options=[]
        for case in decision['cases']:
            fids=[]
            pending=list(case['files']);case_urls={public_url(f['url']) for f in pending}
            for f in pending:
                try:
                    raw,transport=acquisition.get(f['url'],'selected_material')
                    # A single native attachment on an inspected landing page can
                    # be followed without inventing an address or another selector.
                    # Multiple links remain visible as a gap; do not arbitrarily pick.
                    if transport['mime'].split(';')[0] in ('text/html','application/xhtml+xml'):
                        attachments=sorted(u for u in actual_links(raw,transport['final_url']) if re.search(r'\.(pdf|csv|xlsx|docx|json)(?:\?|$)',u,re.I))
                        if len(attachments)==1 and attachments[0] not in case_urls and len(acquisition.attempted)<config['limits']['selected_files']+config['limits']['discovery_pages']:
                            pending.append({'url':attachments[0],'source_page':transport['final_url'],
                                'target_node_ids':f['target_node_ids'],'reason':'Unique native attachment href in the independently downloaded landing page; content not yet verified.'})
                            case_urls.add(attachments[0])
                    fid='f_'+transport['sha256'][:24]
                    if fid not in profiles:
                        require(len(profiles)<config['limits']['selected_files'],'profiled_material_budget_exceeded')
                        p=profile(cache/'blobs'/transport['sha256'],transport['final_url'],transport['mime'],cache)
                        require(p['parse_status']=='parsed','file_parse_rejected:'+p.get('reason','unknown'))
                        if p['type']=='html':
                            failures.append({'stage':'material_selection','url':f['url'],'reason':'html_discovery_only'})
                            continue
                        sources[fid]={**f,**transport,'file_id':fid,'origin':'real_original','license_status':'unknown',
                                      'discovery':acquisition.known[public_url(f['url'])]}
                        profiles[fid]=p
                    if fid not in fids:fids.append(fid)
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    failures.append({'stage':'download_or_profile','url':f['url'],'reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__})
            if not fids:continue
            try:
                views={fid:profile_view(profiles[fid],plan,config['limits']) for fid in fids}
                llm=load_llm(config,config_path,offline)
                audit,meta=model_call(llm,ROOT/'prompts'/config.get('audit_prompt','evidence_auditor.v2.txt'),{
                    'raw_seed':seed,'blueprint':plan,'existing_anchor':None,
                    'provisional_case_identity':case['identity'],
                    'required_node_coverage_ids':[n['id'] for n in external_nodes(plan)],
                    'instruction_nodes_are_not_retrieval_targets':True,
                    'file_profiles':list(views.values()),'sources':{fid:sources[fid] for fid in fids},
                    'schema':schema(ROOT/'config/audit.schema.json')},cache,offline)
                calls.append(meta)
                entry={'case':case['identity'],'audit':audit};audits.append(entry)
                # Save invalid audit responses too; no silent repair or lowered gate.
                save(construction/'coverage_audits.json',audits)
                checked=check_audit(audit,plan,views,sources);entry['program_status']=checked['status']
                options.append(checked)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                if getattr(exc,'model_metadata',None):calls.append(exc.model_metadata)
                failures.append({'stage':'evidence_audit','reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__})
        grounded=[o for o in options if o['selected_anchor'] and o['status']!='rejected']
        if grounded:coverage=max(grounded,key=lambda o:(o['status']=='ready',sum(n['status']=='supported' for n in o['nodes'])))
        elif options:coverage=options[0]
    except (OSError,ValueError,KeyError,TypeError) as exc:
        failures.append({'stage':'agent_retrieval','reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__})
    if not coverage['selected_anchor']:failures.append({'stage':'anchor_discovery','reason':'no_grounded_anchor'})
    if receipt and receipt.get('handoff') and coverage['status']=='ready':
        coverage['status']='incomplete'
        failures.append({'stage':'admission','reason':'complete_evidence_but_incomplete_agent_session_requires_new_run'})
    workspace_files=assemble(directory,sources,profiles,coverage,cache)
    for assessment in coverage['file_assessments']:sources[assessment['file_id']]['license_status']=assessment['license']['status']
    trace=receipt['trace'] if receipt else {};events=acquisition.events if acquisition else []
    critical=[n for n in external_nodes(plan) if n['critical']]
    supported=[n['node_id'] for n in coverage['nodes'] if n['status']=='supported']
    report={'interface':'grounded-workspace-v2','mode':'claude_code_agent', 'seed_id':seed['seed_id'],
        'seed_sha256':sha256(json_bytes(seed)),'blueprint_sha256':sha256(json_bytes(plan)),
        'work_objective_sha256':sha256(plan['work_objective'].encode()),'config_sha256':sha256(json_bytes(config)),
        'selected_anchor':coverage['selected_anchor'],'status':coverage['status'],
        'search_state':'agent_stopped_with_handoff' if receipt and receipt.get('handoff') else ('agent_completed' if decision is not None else 'agent_failed'),
        'stage4_interface':'requires_new_adapter_not_legacy_eligible','workspace_files':workspace_files,
        'retrieved_files':list(sources),'search_queries':[c['input'].get('query') for c in trace.get('tool_calls',[]) if c['name']=='WebSearch'],
        'supported_nodes':supported,'missing_nodes':coverage['missing_critical_nodes'],
        'cross_file_coherence':coverage['cross_file_coherence'],'modality_evidence':coverage['modality_evidence'],
        'public_distribution_eligible':coverage['public_distribution_eligible'],
        'counts':{'actual_search_requests':trace.get('websearch_calls',0),'actual_webfetch_calls':trace.get('webfetch_calls',0),
                  'download_attempts':len(events),'downloaded_urls':sum(e['status']=='downloaded' for e in events),
                  'parsed_unique_files':len(profiles),'retained_files':len(workspace_files),
                  'critical_external_nodes':len(critical),'supported_critical_nodes':sum(n['id'] in supported for n in critical),
                  'critical_coverage':sum(n['id'] in supported for n in critical)/len(critical) if critical else None,
                  'synthetic_files':0,'independently_verified_visual_evidence':0},
        'failure_reasons':failures,'model_calls':calls,'model_usage':usage(calls),
        'agent_model_usage':trace.get('final',{}).get('usage'),
        'search_cost':{'billed_cost':None,'cli_estimate_usd':trace.get('final',{}).get('total_cost_usd'),
                       'note':'Client estimate is not a LLMCenter invoice. Calls count observed tools, not backend requests.'},
        'limits':config['limits'],
        'limitations':['Agent final narrative is provisional, not file evidence.',
                       'WebFetch is a summarized view; Python independently downloads selected materials and discovery pages.',
                       'This is Claude Code with GLM-5.2, not a Claude-model capability evaluation.',
                       'Context, tool workflow, prompts and larger budget differ from the query-only baseline; this is not a controlled causal test.',
                       ('Per-tool fetch budget is prompt-enforced and checked after execution; wall time and turn count bound the process.'
                        if config['search'].get('max_fetch_calls') is not None else
                        'No explicit turn/search/fetch count limit; wall-clock timeout and materialization limits still apply.')]}
    save(construction/'acquisition_trace.json',events);save(construction/'coverage_audits.json',audits)
    save(construction/'source_manifest.json',{'sources':sources});save(construction/'file_profiles.json',list(profiles.values()))
    save(construction/'information_coverage.json',coverage);save(construction/'construction_report.json',report)
    verify_workspace(directory,plan)
    return report
