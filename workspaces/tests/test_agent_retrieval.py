"""Synthetic retrieval traces and bytes; never counted as real search experiments."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from common import DataError,ROOT,sha256,save
from planning_common import schema
from agent_retrieval import actual_links,Acquisition,parse_decision,retrieve,agent_context,build_agent
from test_graph_pipeline import plan,auditor


def trace():
    return {'candidates':[{'url':'https://example.org/project','discovered_by_tool_use_id':'search1'}],
            'tool_calls':[{'name':'WebSearch','input':{'query':'fixture project'}},
                          {'name':'WebFetch','input':{'url':'https://example.org/project'}}],
            'websearch_calls':1,'webfetch_calls':1,'final':{'is_error':False}}


def decision():
    return {'cases':[{'identity':'Synthetic test fixture','files':[{
        'url':'https://example.org/download?id=7','source_page':'https://example.org/project',
        'target_node_ids':['i1','i2'],'reason':'Fixture actual href to records'}], 'missing_information':[]}],
        'rejected_candidates':[],'stop_reason':'Fixture complete'}


def receipt():
    t=trace();t['final']['result']=json.dumps(decision())
    return {'run':{'returncode':0,'timed_out':False},'trace':t}


class AgentRetrievalTests(unittest.TestCase):
    def config(self):return schema(ROOT/'config/claude_agent_pilot.json')

    def test_endpoint_suffix_uses_verified_native_format(self):
        from construct_workspace import assemble
        from profile_files import parse_bytes
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);cache=root/'cache';(cache/'blobs').mkdir(parents=True)
            data=b'item,value\nfixture,10\n';h=sha256(data);(cache/'blobs'/h).write_bytes(data)
            url='https://example.org/export.action?format=csv'
            p=parse_bytes(data,url,'text/csv');fid=p['file_id']
            sources={fid:{'origin':'real_original','sha256':h,'final_url':url}}
            files=assemble(root/'workspace',sources,{fid:p},{'retained_file_ids':[fid]},cache)
            path=next(iter(files));self.assertTrue(path.endswith('.action.csv'))
            self.assertEqual((root/'workspace/workspace_init'/path).read_bytes(),data)

    def test_actual_links_preserve_query_and_relative_path_without_extension(self):
        raw=b'<a href="/download?id=7&amp;format=pdf">Download</a><a href="javascript:bad()">No</a>'
        self.assertEqual(actual_links(raw,'https://example.org/project'),{'https://example.org/download?id=7&format=pdf'})

    def test_full_context_contains_graph_and_adaptive_budget(self):
        c=agent_context(plan(),{'seed_id':'synthetic_test_fixture'},self.config())
        self.assertEqual(c['approved_blueprint'],plan())
        self.assertGreater(c['budget']['web_search_calls'],1)
        self.assertGreater(c['budget']['web_fetch_calls'],1)

    def test_autonomous_mode_has_no_tool_count_ceiling(self):
        config=schema(ROOT/'config/claude_agent_autonomous.json')
        self.assertIsNone(config['search']['max_turns'])
        c=agent_context(plan(),{'seed_id':'synthetic_test_fixture'},config)
        self.assertIsNone(c['budget']['web_search_calls']);self.assertIsNone(c['budget']['web_fetch_calls'])
        r=receipt();r['trace']['websearch_calls']=100;r['trace']['webfetch_calls']=200
        self.assertEqual(parse_decision(r,plan(),config),decision())
        prompt=(ROOT/'prompts'/config['retrieval_prompt']).read_text()
        self.assertIn('CONTINUATION AND STOPPING',prompt)
        self.assertNotIn('budget is exhausted',prompt)

    def test_single_json_handoff_with_preface_not_semantic_repair(self):
        r=receipt();r['trace']['final']['result']='Here is my handoff.\n\n```json\n'+json.dumps(decision())+'\n```'
        self.assertEqual(parse_decision(r,plan(),self.config()),decision())
        r['trace']['final']['result']+='\n```json\n{}\n```'
        with self.assertRaisesRegex(DataError,'ambiguous_agent_json'):parse_decision(r,plan(),self.config())

    def test_false_success_and_wrong_node_rejected(self):
        r=receipt();self.assertEqual(parse_decision(r,plan(),self.config()),decision())
        r['run']['timed_out']=True
        with self.assertRaisesRegex(DataError,'incomplete'):parse_decision(r,plan(),self.config())
        r=receipt();d=decision();d['cases'][0]['files'][0]['target_node_ids']=['invented']
        r['trace']['final']['result']=json.dumps(d)
        with self.assertRaisesRegex(DataError,'non_retrievable'):parse_decision(r,plan(),self.config())

    def test_fetch_and_selection_budget_checked(self):
        r=receipt();r['trace']['webfetch_calls']=11
        with self.assertRaisesRegex(DataError,'budget_exceeded'):parse_decision(r,plan(),self.config())
        r=receipt();d=decision();d['cases'][0]['files']*=7;r['trace']['final']['result']=json.dumps(d)
        with self.assertRaisesRegex(DataError,'file_budget'):parse_decision(r,plan(),self.config())

    def fake_download(self,url,cache,limits,offline):
        if url=='https://example.org/project':
            data=b'<html><body><a href="/download?id=7">Actual records</a></body></html>';mime='text/html'
        elif url=='https://example.org/download?id=7':
            data=b'item,value\nfixture,10\n';mime='text/csv'
        else:raise AssertionError('Unknown URL should not be downloaded')
        h=sha256(data);(cache/'blobs').mkdir(parents=True,exist_ok=True);(cache/'blobs'/h).write_bytes(data)
        return data,{'sha256':h,'final_url':url,'original_url':url,'mime':mime,'bytes':len(data),'retrieved_at':'fixture'}

    def test_summary_claim_or_guessed_url_cannot_authorize_download(self):
        with tempfile.TemporaryDirectory() as t,patch('agent_retrieval.download',side_effect=self.fake_download):
            acq=Acquisition(trace(),self.config(),Path(t),False)
            with self.assertRaisesRegex(DataError,'not_observed'):acq.get('https://example.org/invented.pdf','selected_material')
            acq.discover_fetch_chain(trace(),decision()['cases'][0]['files'])
            self.assertEqual(acq.known['https://example.org/download?id=7']['method'],'actual_html_href')
            data,transport=acq.get('https://example.org/download?id=7','selected_material')
            self.assertEqual(transport['mime'],'text/csv');self.assertIn(b'fixture',data)
            count=len(acq.events);acq.get('https://example.org/download?id=7','selected_material')
            self.assertEqual(len(acq.events),count)

    def test_actual_webfetch_visit_can_be_independently_downloaded(self):
        t=trace();t['candidates']=[]
        t['tool_results']=[{'name':'WebFetch','tool_use_id':'fetch1','input':{'url':'https://example.org/project'},
                           'page_access_status':'tool_response_requires_independent_download_check'}]
        with tempfile.TemporaryDirectory() as temp,patch('agent_retrieval.download',side_effect=self.fake_download) as download:
            acq=Acquisition(t,self.config(),Path(temp),False)
            self.assertEqual(acq.known['https://example.org/project']['method'],'WebFetch_attempt_requires_independent_http_verification')
            raw,transport=acq.get('https://example.org/project','discovery_page')
            self.assertEqual(download.call_count,1);self.assertEqual(transport['sha256'],sha256(raw))

    def test_unique_native_attachment_is_downloaded_from_actual_html(self):
        r=receipt();d=decision();d['cases'][0]['files'][0].update(url='https://example.org/project',source_page='https://example.org/project')
        r['trace']['final']['result']=json.dumps(d)
        def download(url,cache,limits,offline):
            data=b'<html><body><a href="/original.csv">Records</a></body></html>' if url.endswith('project') else b'item,value\nfixture,10\n'
            mime='text/html' if url.endswith('project') else 'text/csv'
            h=sha256(data);(cache/'blobs').mkdir(parents=True,exist_ok=True);(cache/'blobs'/h).write_bytes(data)
            return data,{'sha256':h,'final_url':url,'original_url':url,'mime':mime}
        def review(llm,prompt,context,cache,offline):
            return auditor({p['file_id']:p for p in context['file_profiles']}),{'request_sha256':'fixture','usage':{}}
        with tempfile.TemporaryDirectory() as t,patch('agent_retrieval.retrieve',return_value=r),patch('agent_retrieval.download',side_effect=download),patch('agent_retrieval.model_call',side_effect=review):
            root=Path(t);out=build_agent(plan(),{'seed_id':'synthetic_test_fixture'},self.config(),ROOT/'config/claude_agent_pilot.json',root/'cache',root/'workspace',True)
            self.assertEqual(out['counts']['parsed_unique_files'],1)
            self.assertEqual(out['counts']['retained_files'],1)
            self.assertTrue(all(p.suffix=='.csv' for p in (root/'workspace/workspace_init').rglob('*') if p.is_file()))
            self.assertEqual(out['counts']['downloaded_urls'],2)

    def test_receipt_replay_without_claude_process(self):
        with tempfile.TemporaryDirectory() as t:
            cache=Path(t)
            with patch('agent_retrieval.run_session',return_value=(receipt()['run'],receipt()['trace'])) as call:
                first=retrieve(plan(),{'seed_id':'fixture'},self.config(),cache)
                self.assertEqual(call.call_count,1)
            with patch('agent_retrieval.run_session',side_effect=AssertionError('No subprocess on replay')):
                self.assertEqual(retrieve(plan(),{'seed_id':'fixture'},self.config(),cache,True),first)

    def test_complete_fixture_uses_existing_coverage_gates(self):
        def review(llm,prompt,context,cache,offline):
            self.assertEqual(context['required_node_coverage_ids'],['i1','i2'])
            profiles={p['file_id']:p for p in context['file_profiles']}
            return auditor(profiles),{'request_sha256':'fixture','usage':{}}
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with patch('agent_retrieval.retrieve',return_value=receipt()),patch('agent_retrieval.download',side_effect=self.fake_download),patch('agent_retrieval.model_call',side_effect=review):
                r=build_agent(plan(),{'seed_id':'synthetic_test_fixture'},self.config(),ROOT/'config/claude_agent_pilot.json',root/'cache',root/'workspace',True)
            self.assertEqual(r['status'],'ready',r['failure_reasons'])
            self.assertEqual(r['counts']['download_attempts'],2)
            self.assertEqual(r['counts']['retained_files'],1)
            self.assertFalse(r['public_distribution_eligible'])

    def test_no_case_stays_incomplete_no_download_fallback(self):
        r=receipt();r['trace']['final']['result']=json.dumps({'cases':[],'rejected_candidates':[],'stop_reason':'No case found'})
        with tempfile.TemporaryDirectory() as t,patch('agent_retrieval.retrieve',return_value=r),patch('agent_retrieval.download') as download:
            root=Path(t)
            out=build_agent(plan(),{'seed_id':'synthetic_test_fixture'},self.config(),ROOT/'config/claude_agent_pilot.json',root/'cache',root/'workspace',True)
            self.assertEqual(out['status'],'incomplete');download.assert_not_called()

    def test_closeout_preserves_failed_session_even_if_files_cover_fixture(self):
        r=receipt();r['run']['returncode']=1;r['trace']['final'].update(is_error=True,subtype='error_max_turns',result=None)
        config=self.config();config['closeout_after_incomplete']=True
        handoff={'decision':decision(),'model_metadata':{'request_sha256':'handoff','usage':{}},'kind':'fixture'}
        def review(llm,prompt,context,cache,offline):
            return auditor({p['file_id']:p for p in context['file_profiles']}),{'request_sha256':'review','usage':{}}
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with patch('agent_retrieval.retrieve',return_value=r),patch('agent_retrieval.closeout',return_value=handoff),patch('agent_retrieval.download',side_effect=self.fake_download),patch('agent_retrieval.model_call',side_effect=review):
                out=build_agent(plan(),{'seed_id':'synthetic_test_fixture'},config,ROOT/'config/claude_agent_pilot.json',root/'cache',root/'workspace',True)
            self.assertEqual(out['status'],'incomplete')
            self.assertEqual(out['search_state'],'agent_stopped_with_handoff')
            self.assertEqual(out['counts']['retained_files'],1)
            self.assertIn('complete_evidence_but_incomplete_agent_session_requires_new_run',[f['reason'] for f in out['failure_reasons']])


if __name__=='__main__':unittest.main()
