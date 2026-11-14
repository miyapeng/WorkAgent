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

CSV=b'entity,period,unit,amount\nExample,FY2024,USD dollars,100\n\n'


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

    def test_explicit_download_retry_preserves_failure_and_offline_stays_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp);url='https://example.com/data.csv'
            limits={'download_bytes':1000,'timeout_seconds':1,'redirects':2,'retries':0}
            with patch.object(acquire,'https_request',side_effect=TimeoutError):
                with self.assertRaisesRegex(DataError,'TimeoutError'):acquire.download(url,cache,limits)
            receipt=cache/'downloads'/(sha256(url.encode())+'.json');failed=receipt.read_bytes()
            retry={**limits,'retry_failed_downloads':True}
            with patch.object(acquire,'https_request',side_effect=AssertionError('No network')):
                with self.assertRaisesRegex(DataError,'TimeoutError'):acquire.download(url,cache,limits)
                with self.assertRaisesRegex(DataError,'TimeoutError'):acquire.download(url,cache,retry,offline=True)
            record={'original_url':url,'final_url':url,'sha256':sha256(CSV),'bytes':len(CSV),'mime':'text/csv'}
            with patch.object(acquire,'https_request',return_value=(CSV,record)) as request:
                data,_=acquire.download(url,cache,retry)
                request.assert_called_once()
            self.assertEqual(data,CSV)
            archived=list((cache/'download_failures').glob('*.json'))
            self.assertEqual(len(archived),1)
            self.assertEqual(json.loads(archived[0].read_bytes()),json.loads(failed))
            with patch.object(acquire,'https_request',side_effect=AssertionError('No network')):
                self.assertEqual(acquire.download(url,cache,retry,offline=True)[0],CSV)


class ProfileTests(unittest.TestCase):
    def test_parser_subprocess_failure_retains_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'broken.pdf'; path.write_bytes(b'%PDF-broken')
            parsed=profile(path,'https://example.org/broken.pdf','application/pdf',root/'cache')
            self.assertEqual(parsed['parse_status'],'rejected')
            self.assertEqual(parsed['sha256'],sha256(path.read_bytes()))
            self.assertEqual(parsed['file_id'],'f_'+sha256(path.read_bytes())[:24])

    def test_csv_structure_locations_and_blank_line(self):
        p=parse_bytes(CSV,'https://example.org/input.csv','text/csv')
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



if __name__=="__main__":unittest.main()
