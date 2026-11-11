"""Unit fixtures are synthetic and temporary; they are never pilot evidence."""
import copy
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from common import DataError, sha256, json_bytes, save
import acquire
from profile_files import parse_bytes, checked_zip, profile
from coverage import check_audit, admission, verify_quote, validate_origin
from construct_workspace import load_inputs, selection_valid, assemble, verify_workspace, get_search
from companions import render_companions

CSV=b'entity,period,unit,amount\nExample,FY2024,USD dollars,100\n\n'


def fixtures():
    p=parse_bytes(CSV,'https://example.org/input.csv','text/csv'); p['origin']='real_original'
    fid=p['file_id']; ref={'file_id':fid,'locator':'row:2','quote':'Example | FY2024 | USD dollars | 100'}
    plan={'seed_id':'seed_fixture','information_nodes':[{'id':'i1','type':'external_input','description':'Input amounts'}]}
    audit={'files':[{'file_id':fid,'case_role':'anchor','scope':{'entity':'Example','period':'FY2024','currency':'USD','units':'dollars','version':'unknown'},
        'scope_evidence':[ref],'applicability':'Same example case.','privacy_risk':False,'answer_leakage':'none'}],
        'coverage':[{'node_id':'i1','status':'supported','evidence':[ref],'reason':'Located input.','unverified_assumptions':[]}],
        'coherence':{'status':'consistent','reason':'Single case.','evidence':[ref],'unverified_assumptions':[]},
        'completion':{'safe':False,'reason':'No gap.','target_nodes':[]}}
    return p,plan,audit


class NetworkTests(unittest.TestCase):
    def test_url_restrictions(self):
        for u in ['http://example.com','file:///etc/passwd','https://localhost/a','https://127.0.0.1/a',
                  'https://[::1]/','https://169.254.169.254/latest','https://10.0.0.1','https://u:p@example.com',
                  'https://example.com:8443/','https://example.com/\nheader']:
            with self.subTest(url=u),self.assertRaises((DataError,ValueError)):
                acquire.public_url(u)
        self.assertEqual(acquire.public_url('https://example.com/a#fragment'),'https://example.com/a')

    def test_all_dns_answers_must_be_public(self):
        records=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443)),
                 (socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch('socket.getaddrinfo',return_value=records),self.assertRaisesRegex(DataError,'private_dns'):
            acquire.public_addresses('example.com')

    def test_redirect_target_and_size_are_checked(self):
        class Response:
            status=302
            def getheader(self,k,default=None): return 'https://127.0.0.1/secret' if k=='Location' else default
        class Connection:
            sock=None
            def __init__(self,*args): pass
            def request(self,*args,**kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        with patch.object(acquire,'PinnedHTTPS',Connection),patch.object(acquire,'public_addresses',return_value=['8.8.8.8']):
            with self.assertRaisesRegex(DataError,'private_address'): acquire.https_request('https://example.com/')
        Response.status=200
        Response.getheader=lambda self,k,default=None: '999' if k=='Content-Length' else default
        with patch.object(acquire,'PinnedHTTPS',Connection),patch.object(acquire,'public_addresses',return_value=['8.8.8.8']):
            with self.assertRaisesRegex(DataError,'too_large'): acquire.https_request('https://example.com/',max_bytes=10)

    def test_dns_pinned_connection_and_tls_hostname(self):
        with patch.object(acquire.socket,'create_connection') as connect,patch.object(acquire.ssl,'create_default_context') as ctx:
            c=acquire.PinnedHTTPS('example.com','8.8.8.8',5); c.connect()
            connect.assert_called_once_with(('8.8.8.8',443),timeout=5)
            ctx.return_value.wrap_socket.assert_called_once_with(connect.return_value,server_hostname='example.com')

    def test_cache_hash_and_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp);limits={'download_bytes':1000,'timeout_seconds':1,'redirects':2,'retries':0}
            def fetch(url,**kwargs): return CSV,{'original_url':url,'final_url':url,'sha256':sha256(CSV),'bytes':len(CSV),'mime':'text/csv','retrieved_at':'test','redirects':[]}
            with patch.object(acquire,'https_request',side_effect=fetch):
                acquire.download('https://example.com/one.csv',cache,limits)
                acquire.download('https://example.com/two.csv',cache,limits)
            self.assertEqual(len(list((cache/'blobs').iterdir())),1)
            with patch.object(acquire,'https_request',side_effect=AssertionError('No network')):
                acquire.download('https://example.com/one.csv',cache,limits,offline=True)
            (cache/'blobs'/sha256(CSV)).write_bytes(b'corrupt')
            with self.assertRaisesRegex(DataError,'cache_corrupt'): acquire.download('https://example.com/one.csv',cache,limits,offline=True)

    def test_download_failures_replay_without_fake_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp); limits={'download_bytes':1000,'timeout_seconds':1,'redirects':2,'retries':1}
            with patch.object(acquire,'https_request',side_effect=DataError('http_status:404')) as request:
                with self.assertRaisesRegex(DataError,'http_status:404'): acquire.download('https://example.com/missing',cache,limits)
                self.assertEqual(request.call_count,2)
            with patch.object(acquire,'https_request',side_effect=AssertionError('No network')):
                with self.assertRaisesRegex(DataError,'http_status:404'): acquire.download('https://example.com/missing',cache,limits,offline=True)
            self.assertFalse((cache/'blobs').exists())


class ProfileTests(unittest.TestCase):
    def test_parser_subprocess_failure_retains_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'broken.pdf'; path.write_bytes(b'%PDF-broken')
            parsed=profile(path,'https://example.org/broken.pdf','application/pdf',root/'cache')
            self.assertEqual(parsed['parse_status'],'rejected')
            self.assertEqual(parsed['sha256'],sha256(path.read_bytes()))
            self.assertEqual(parsed['file_id'],'f_'+sha256(path.read_bytes())[:24])

    def test_csv_structure_locations_and_blank_line(self):
        p,_,_=fixtures()
        self.assertEqual(p['structure']['rows'],1);self.assertEqual(p['structure']['blank_rows'],1)
        self.assertEqual(p['structure']['columns'],['entity','period','unit','amount'])
        self.assertEqual(p['segments'][1]['locator'],'row:2')

    def test_corrupt_and_spoofed_files(self):
        for data,url,mime in [(b'<html>error</html>','https://e.org/a.pdf','application/pdf'),
            (b'%PDF-broken','https://e.org/a.pdf','application/pdf'),(b'a,b\n1,2,3','https://e.org/a.csv','text/csv'),
            (b'a,b\n=cmd,2','https://e.org/a.csv','text/csv')]:
            with self.subTest(url=url),self.assertRaises(Exception): parse_bytes(data,url,mime)

    def test_archive_path_and_macro_rejection(self):
        for filename in ['../escape','xl/vbaProject.bin']:
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w') as z:z.writestr(filename,b'content')
            with self.assertRaises(DataError): checked_zip(buffer.getvalue())

    def test_docx_and_repository_are_parsed_not_executed(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('word/document.xml','<w:document xmlns:w="urn:w"><w:p><w:r><w:t>Readable policy paragraph</w:t></w:r></w:p></w:document>')
        p=parse_bytes(b.getvalue(),'https://e.org/a.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        self.assertEqual(p['segments'][0]['text'],'Readable policy paragraph')
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('project/setup.py','raise RuntimeError("DO NOT EXECUTE")')
        p=parse_bytes(b.getvalue(),'https://e.org/repo.zip','application/zip')
        self.assertFalse(p['structure']['executed'])

    def test_image_is_not_claimed_visually_verified(self):
        from PIL import Image
        b=io.BytesIO();Image.new('RGB',(10,10)).save(b,format='PNG')
        p=parse_bytes(b.getvalue(),'https://e.org/a.png','image/png')
        self.assertFalse(p['structure']['visual_content_verified'])
        self.assertIn('visual_inspection_required',p['warnings'])

    def test_xlsx_cells_and_formula_not_executed(self):
        from openpyxl import Workbook
        book=Workbook();sheet=book.active;sheet.title='Inputs';sheet.append(['Category','Amount']);sheet.append(['Operating',100]);sheet['B3']='=B2*2'
        b=io.BytesIO();book.save(b)
        p=parse_bytes(b.getvalue(),'https://example.org/input.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertEqual(p['structure']['sheets'][0]['formula_cells'],1)
        self.assertFalse(p['structure']['sheets'][0]['formulas_executed'])
        self.assertTrue(any(s['locator']=='sheet:Inputs!B2' and s['text']=='100' for s in p['segments']))

    def test_pdf_text_locations(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
        writer=PdfWriter();page=writer.add_blank_page(width=600,height=800)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 50 700 Td (Official test policy paragraph with readable context) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        b=io.BytesIO();writer.write(b)
        p=parse_bytes(b.getvalue(),'https://example.org/input.pdf','application/pdf')
        self.assertEqual(p['structure']['pages'],1)
        self.assertTrue(any(s['locator']=='page:1:line:1' and 'policy paragraph' in s['text'] for s in p['segments']))


class CoverageTests(unittest.TestCase):
    def test_located_coverage_and_incomplete_gate(self):
        p,plan,a=fixtures(); profiles={p['file_id']:p}
        c=check_audit(a,plan,profiles);self.assertEqual(admission(c)[0],'ready')
        a['coverage'][0]['status']='partial';c=check_audit(a,plan,profiles)
        self.assertEqual(admission(c)[0],'incomplete')

    def test_wrong_locations_and_unverified_assumptions_downgrade(self):
        p,plan,a=fixtures();a['coverage'][0]['evidence'][0]=dict(a['coverage'][0]['evidence'][0],locator='row:99')
        c=check_audit(a,plan,{p['file_id']:p})
        self.assertEqual(c['nodes'][0]['status'],'missing')
        p,plan,a=fixtures();a['coverage'][0]['unverified_assumptions']=['Assume approval.']
        self.assertEqual(check_audit(a,plan,{p['file_id']:p})['nodes'][0]['status'],'partial')

    def test_source_mismatch_and_answer_leakage(self):
        p,plan,a=fixtures();p2=copy.deepcopy(p);p2['file_id']='f_other';p2['sha256']='a'*64
        f=copy.deepcopy(a['files'][0]);f['file_id']=p2['file_id'];f['scope']['entity']='Different entity'
        f['scope_evidence']=[dict(f['scope_evidence'][0],file_id=p2['file_id'])];a['files'].append(f)
        c=check_audit(a,plan,{p['file_id']:p,p2['file_id']:p2});self.assertEqual(admission(c)[0],'rejected')
        p,plan,a=fixtures();a['files'][0]['answer_leakage']='present'
        c=check_audit(a,plan,{p['file_id']:p});self.assertFalse(c['retained_file_ids'])

    def test_missing_nodes_and_unknown_files_not_accepted(self):
        p,plan,a=fixtures();a['coverage']=[]
        with self.assertRaises(DataError):check_audit(a,plan,{p['file_id']:p})
        p,plan,a=fixtures();a['files'][0]['file_id']='invented'
        with self.assertRaises(DataError):check_audit(a,plan,{p['file_id']:p})

    def test_origin_labels(self):
        for r in [{'origin':'real_original','synthetic':True,'original_url':'https://e.org','sha256':'x'},
                  {'origin':'synthetic','original_url':'https://fabricated.invalid/file'},
                  {'origin':'real_adapted','sha256':'x'}]:
            with self.assertRaises(DataError): validate_origin(r)

    def test_companions_need_anchor_explicit_gap_and_disclosure(self):
        p,plan,a=fixtures();c=check_audit(a,plan,{p['file_id']:p})
        spec={'seed_id':plan['seed_id'],'plan_sha256':sha256(json_bytes(plan)),'fictional_case':'Fictional Example',
              'files':[{'filename':'SYNTHETIC_context.json','target_nodes':['i1'],'format':'json','content':{'scope':'illustrative context'}}]}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DataError):render_companions(spec,plan,c,Path(tmp))
            c['nodes'][0]['status']='missing';c['completion']={'safe':True,'reason':'Fixture','target_nodes':['i1']}
            sources,profiles=render_companions(spec,plan,c,Path(tmp))
            self.assertEqual(sources[0]['origin'],'synthetic')
            self.assertIn('SYNTHETIC',(Path(tmp)/'blobs'/sources[0]['sha256']).read_text())
            c['usable_real_anchors']=[]
            with self.assertRaises(DataError):render_companions(spec,plan,c,Path(tmp))

    def test_only_stage2_accepted_inputs(self):
        repo=Path(__file__).resolve().parents[2]
        plans,_,_=load_inputs(repo/'work-plans/data/pilot',repo/'work-seeds/data/work_seed_pilot_v2')
        self.assertEqual(len(plans),2)
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            (d/'work_plans.jsonl').write_text(json.dumps(plans[0])+'\n')
            save(d/'planning_report.json',{'seeds':{plans[0]['seed_id']:{'status':'audit_rejected'}}})
            with self.assertRaises(DataError):load_inputs(d,repo/'work-seeds/data/work_seed_pilot_v2')

    def test_modified_approved_plan_fails_checkpoint_binding(self):
        repo=Path(__file__).resolve().parents[2]
        source=repo/'work-plans/data/pilot'
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);plans=[json.loads(line) for line in (source/'work_plans.jsonl').read_text().splitlines()]
            plans[0]['work_objective']='A different but structurally valid professional work objective.'
            (d/'work_plans.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in plans))
            (d/'planning_report.json').write_bytes((source/'planning_report.json').read_bytes())
            with self.assertRaisesRegex(DataError,'approved_checkpoint'):load_inputs(d,repo/'work-seeds/data/work_seed_pilot_v2')

    def test_search_manifest_missing_query_is_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);save(root/'urls.json',{'searches':[]})
            values,receipt=get_search('a real query','seed',1,{'provider':'url_manifest','manifest':'urls.json'},root,root/'cache')
            self.assertEqual(values,[]);self.assertEqual(receipt['status'],'awaiting_external_search')

    def test_http_search_adapter_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config={'provider':'http_search','endpoint':'https://example.org/search'}
            raw=json.dumps({'results':[{'url':'https://example.org/file.csv','title':'Observed candidate'},
                                       {'url':'https://127.0.0.1/private'}]}).encode()
            with patch('construct_workspace.https_request',return_value=(raw,{'retrieved_at':'fixture','sha256':sha256(raw)})) as call:
                values,_=get_search('actual query','seed',1,config,root,root/'cache')
                self.assertEqual(len(values),1);self.assertEqual(call.call_count,1)
            with patch('construct_workspace.https_request',side_effect=AssertionError('No network')):
                again,_=get_search('actual query','seed',1,config,root,root/'cache',offline=True)
                self.assertEqual(values,again)

    def test_selection_cannot_invent_candidate_ids(self):
        candidates=[{'candidate_id':'c1'}]
        with self.assertRaises(DataError):selection_valid({'selected':[{'candidate_id':'invented','reason':'x'}],'rejected':[]},candidates,1)

    def test_assembly_copy_hash_and_no_hidden_metadata(self):
        p,plan,a=fixtures();c=check_audit(a,plan,{p['file_id']:p})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'cache';directory=root/'WS001';(cache/'blobs').mkdir(parents=True)
            (cache/'blobs'/sha256(CSV)).write_bytes(CSV)
            sources=[{'file_id':p['file_id'],'sha256':sha256(CSV),'origin':'real_original','original_url':'https://example.org/data.csv','download_status':'downloaded'}]
            files=assemble(directory,sources,{p['file_id']:p},c,cache)
            save(directory/'construction/source_manifest.json',{'sources':sources})
            save(directory/'construction/information_coverage.json',c)
            (directory/'construction/file_profiles.jsonl').write_text(json.dumps(p)+'\n')
            save(directory/'construction/construction_report.json',{'status':'ready','stage4_eligible':True,'objective_preserved':True,'workspace_files':files})
            self.assertEqual(verify_workspace(directory)['file_count'],1)
            self.assertEqual(set(files),{next((directory/'workspace_init/tables').iterdir()).relative_to(directory/'workspace_init').as_posix()})
            (directory/'workspace_init/hidden_graph.json').write_text('{}')
            with self.assertRaises(DataError):verify_workspace(directory)


if __name__=='__main__': unittest.main()
