"""Synthetic fixtures, fake HTTP/model adapters; never counted as live pilot results."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from common import DataError,sha256,save,REPO,json_bytes,write_jsonl
from profile_files import parse_bytes,add_segment_ids
from coverage import check_audit,resolve_refs
from construct_workspace import build_one,verify_workspace,validate_search,load_inputs,discover_links
from search_provider import search


def plan():
    return {'seed_id':'synthetic_test_fixture','work_objective':'Compare two source values.','deliverables':[{'id':'out1','type':'comparison','description':'Comparison'}],
            'information_nodes':[{'id':i,'type':'external_input','description':'Input '+i,'supply_channel':'workspace','critical':True,'modality_candidates':['table'],'modality_rationale':'Tabular values'} for i in ('i1','i2')],
            'dependencies':[['i1','out1'],['i2','out1']],'modality_hypotheses':[]}


def auditor(profiles,complete=True):
    fids=list(profiles);refs=[{'file_id':fid,'segment_id':profiles[fid]['segments'][0]['segment_id']} for fid in fids]
    return {'file_assessments':[{'file_id':fid,'retain':True,'role':'anchor' if j==0 else 'supporting','reason':'Fixture only','sensitive':False,'answer_leakage':False,'license':{'status':'unknown','reason':'Not asserted','evidence':[]}} for j,fid in enumerate(fids)],
            'node_coverage':[{'node_id':nid,'status':'supported' if complete or j==0 else 'missing','evidence':[refs[min(j,len(refs)-1)]] if complete or j==0 else [],'reason':'Fixture','unverified_assumptions':[]} for j,nid in enumerate(('i1','i2'))],
            'selected_anchor':{'identity':'Synthetic fixture case','file_ids':[fids[0]],'evidence':[refs[0]],'scope':'test'},
            'cross_file_coherence':{'status':'coherent','reason':'Fixture case','evidence':refs,'unverified_assumptions':[]},'suspected_answer_leakage':False,
            'unresolved_information_gaps':[] if complete else ['i2 missing'],'recommendation':'ready' if complete else 'continue_search'}


def sources(profiles):return {fid:{'origin':'real_original','sha256':p['sha256']} for fid,p in profiles.items()}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        p=parse_bytes(b'item,value\nfixture,10\n','https://example.org/data.csv','text/csv');self.profiles={p['file_id']:p};self.audit=auditor(self.profiles)
    def test_exact_source_recovered_by_id_no_llm_quote(self):
        value=check_audit(self.audit,plan(),self.profiles,sources(self.profiles))
        self.assertEqual(value['status'],'ready');self.assertEqual(value['nodes'][0]['evidence'][0]['quote'],'item | value')
        self.assertFalse(value['public_distribution_eligible'])
    def test_unknown_segment_and_tampered_locator(self):
        a=copy.deepcopy(self.audit);a['node_coverage'][0]['evidence'][0]['segment_id']='invented'
        with self.assertRaisesRegex(DataError,'unknown_segment'):check_audit(a,plan(),self.profiles,sources(self.profiles))
        p=next(iter(self.profiles.values()));p['segments'][0]['locator']='row:999'
        with self.assertRaisesRegex(DataError,'segment_hash'):check_audit(self.audit,plan(),self.profiles,sources(self.profiles))
    def test_conflicts_and_missing_evidence_block_ready(self):
        a=copy.deepcopy(self.audit);a['cross_file_coherence']['status']='conflicted'
        self.assertEqual(check_audit(a,plan(),self.profiles,sources(self.profiles))['status'],'rejected')
        a=copy.deepcopy(self.audit);a['node_coverage'][0].update(status='missing',evidence=[])
        self.assertEqual(check_audit(a,plan(),self.profiles,sources(self.profiles))['status'],'incomplete')
    def test_excluded_file_cannot_support_node(self):
        a=copy.deepcopy(self.audit);a['file_assessments'][0].update(retain=False,role='excluded')
        with self.assertRaisesRegex(DataError,'excluded'):check_audit(a,plan(),self.profiles,sources(self.profiles))
    def test_answer_leakage_sensitive_synthetic_labels_fail(self):
        for field in ('sensitive','answer_leakage'):
            a=copy.deepcopy(self.audit);a['file_assessments'][0][field]=True
            with self.assertRaisesRegex(DataError,'unsafe'):check_audit(a,plan(),self.profiles,sources(self.profiles))
        source=sources(self.profiles);next(iter(source.values()))['origin']='synthetic'
        with self.assertRaisesRegex(DataError,'invalid_real'):check_audit(self.audit,plan(),self.profiles,source)
    def test_vlm_observation_is_never_ground_truth(self):
        p=next(iter(self.profiles.values()));p['segments'][0]['evidence_method']='model_visual_observation';add_segment_ids(p)
        a=auditor(self.profiles)
        # The anchor identity must itself be programmatically located, not a VLM claim.
        with self.assertRaisesRegex(DataError,'anchor_identity'):check_audit(a,plan(),self.profiles,sources(self.profiles))
    def test_segment_ids_stable_and_audio_metadata_not_transcription(self):
        p=next(iter(self.profiles.values()));self.assertEqual(add_segment_ids(copy.deepcopy(p)),p)
        data=io.BytesIO()
        with wave.open(data,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*8000)
        media=parse_bytes(data.getvalue(),'https://example.org/a.wav','audio/wav')
        self.assertEqual(media['structure']['duration_seconds'],1);self.assertEqual(media['segments'],[])
    def test_links_only_come_from_downloaded_hrefs(self):
        results=discover_links(b'<a href="/a.pdf">real href</a><a href="http://localhost/x.csv">bad</a>','https://example.org/page')
        self.assertEqual([r['url'] for r in results],['https://example.org/a.pdf'])


class SearchTests(unittest.TestCase):
    def test_missing_key_is_awaiting_not_success(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{},clear=True),patch('search_provider.https_request') as request:
            r=search('query',{'provider':'tavily','api_key_env':'TAVILY_API_KEY'},Path(temp))
            self.assertEqual(r['status'],'awaiting_search');request.assert_not_called()
    def test_provider_payloads_cache_and_secret_not_recorded(self):
        for provider,body in [('tavily',{'results':[{'url':'https://example.org/a.csv','title':'A','content':'data'}]}),('brave',{'web':{'results':[{'url':'https://example.org/a.csv','title':'A','description':'data'}]}}),('serper',{'organic':[{'link':'https://example.org/a.csv','title':'A','snippet':'data'}]})]:
            with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'TEST_SEARCH_KEY':'fixture_secret'}),patch('search_provider.https_request',return_value=(json.dumps(body).encode(),{'retrieved_at':'fixture','sha256':'fixture'})) as request:
                config={'provider':provider,'api_key_env':'TEST_SEARCH_KEY'};r=search('actual query',config,Path(temp));self.assertEqual(len(r['results']),1)
                self.assertNotIn('fixture_secret',json.dumps(r));self.assertEqual(search('actual query',config,Path(temp),True),r);self.assertEqual(request.call_count,1)
    def test_query_targets_and_budget(self):
        q={'strategy':'anchor_search','queries':[{'query':'case records','target_node_ids':['out1'],'reason':'test','desired_source_type':'data'}],'stop_reason':None}
        with self.assertRaisesRegex(DataError,'non_retrievable'):validate_search(q,plan(),2,None)
        q['queries'][0]['target_node_ids']=['i1']
        with self.assertRaisesRegex(DataError,'budget'):validate_search(q,plan(),0,None)


class LoopTests(unittest.TestCase):
    def test_upstream_review_and_hash_cannot_be_bypassed(self):
        raw=REPO/'work-seeds/data/raw_work_seeds/sampled_raw_seeds.jsonl'
        plans,seeds,report=load_inputs(REPO/'work-plans/data/generated',raw)
        for change in ('file_hash','review','seed_hash'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);r=copy.deepcopy(report)
                write_jsonl(root/'blueprints.jsonl',plans)
                if change=='file_hash':r['blueprints_sha256']='wrong'
                elif change=='review':r['seeds'][plans[0]['seed_id']]['semantic_review']['accepted']=False
                else:r['seeds'][plans[0]['seed_id']]['seed_sha256']='wrong'
                save(root/'planning_report.json',r)
                with self.assertRaises(DataError):load_inputs(root,raw)
    def test_two_round_fixture_and_hash_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cache=root/'cache';calls=[]
            config={'limits':{'anchor_queries':1,'anchor_candidates':1,'gap_rounds':1,'queries_per_gap':1,'files_per_gap':1,'download_bytes':10000,'timeout_seconds':1,'redirects':1,'max_profile_chars':10000,'max_segments_per_file':20},'search':{'provider':'fixture'},'vision':None}
            def model(llm,path,context,cache,offline):
                calls.append(path.name)
                if path.name.startswith('search_planner'):
                    anchor=context['existing_anchor'];value={'strategy':'gap_filling' if anchor else 'anchor_search','queries':[{'query':'second' if anchor else 'first','target_node_ids':['i2'] if anchor else ['i1','i2'],'desired_source_type':'csv','reason':'fixture'}],'stop_reason':None}
                elif path.name.startswith('candidate_selector'):value={'selected':[{'candidate_id':r['candidate_id'],'reason':'fixture'} for r in context['candidates']],'rejected':[]}
                else:
                    profiles={p['file_id']:p for p in context['file_profiles']};value=auditor(profiles,len(profiles)==2)
                return value,{'request_sha256':str(len(calls)),'usage':{}}
            def find(query,config,cache,offline):
                return {'query':query,'provider':'synthetic_test_fixture','status':'searched','results':[{'candidate_id':query,'url':'https://example.org/'+query+'.csv','source_page':'https://example.org','title':query,'snippet':'fixture'}],'search_api_called':True}
            def fetch(url,cache,limits,offline):
                raw=('item,value\nfixture,'+('10' if 'first' in url else '20')+'\n').encode();h=sha256(raw);blob=cache/'blobs'/h;blob.parent.mkdir(parents=True,exist_ok=True);blob.write_bytes(raw)
                return raw,{'original_url':url,'final_url':url,'sha256':h,'mime':'text/csv','retrieved_at':'fixture','bytes':len(raw),'redirects':[]}
            with patch('construct_workspace.load_llm',return_value={}),patch('construct_workspace.model_call',side_effect=model),patch('construct_workspace.search',side_effect=find),patch('construct_workspace.download',side_effect=fetch):
                r=build_one(plan(),{'seed_id':'synthetic_test_fixture','task_text':'Synthetic test only'},config,root/'config.json',cache,root/'workspace')
            self.assertEqual(r['status'],'ready');self.assertEqual(r['counts']['actual_search_requests'],2);self.assertEqual(r['counts']['retained_files'],2)
            self.assertFalse(any(p.name.endswith('.json') for p in (root/'workspace/workspace_init').rglob('*')))
            verify_workspace(root/'workspace',plan())
            next(p for p in (root/'workspace/workspace_init').rglob('*') if p.is_file()).write_text('changed')
            with self.assertRaisesRegex(DataError,'hash_changed'):verify_workspace(root/'workspace',plan())
if __name__=='__main__':unittest.main()
