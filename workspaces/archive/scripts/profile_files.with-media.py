"""Parse bytes as data only. No macros, downloaded code, or shell commands run."""
import csv
import io
import json
import re
import subprocess
import shutil
import sys
import tempfile
import wave
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from common import DataError, require, normalized, sha256, save

VERSION = 'native-profiles-v2-segment-ids'
MAX_SEGMENTS = 100000


def checked_zip(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    entries = z.infolist()
    require(len(entries) <= 5000 and sum(i.file_size for i in entries) <= 100_000_000, 'archive_expansion_limit')
    for i in entries:
        p = Path(i.filename)
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename, 'archive_path_traversal')
        require((i.external_attr >> 16) & 0o170000 != 0o120000, 'archive_symlink')
        require(not i.flag_bits & 1, 'encrypted_archive')
        require(i.file_size <= 20_000_000 and i.file_size / max(i.compress_size, 1) <= 200, 'archive_compression_limit')
        require(not re.search(r'vbaProject|activeX|embeddings/', i.filename, re.I), 'active_office_content')
    return z


def detect(data, url, mime):
    suffix = Path(urlsplit(url).path).suffix.lower()
    if data.startswith(b'%PDF-'):
        kind = 'pdf'
    elif data.startswith(b'PK\x03\x04'):
        with checked_zip(data) as z:
            names = set(z.namelist())
            kind = 'xlsx' if 'xl/workbook.xml' in names else 'docx' if 'word/document.xml' in names else 'pptx' if 'ppt/presentation.xml' in names else 'repository_zip'
    elif data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')):
        kind = 'image'
    elif (data[:4]==b'RIFF' and data[8:12]==b'WAVE') or data.startswith((b'ID3',b'OggS',b'fLaC')) or data[4:8]==b'ftyp':
        kind = 'media'
    else:
        text = data.decode('utf-8-sig')
        require('\x00' not in text, 'binary_or_invalid_text')
        if re.search(r'<(?:!doctype\s+html|html|head|body)\b', text[:2000], re.I):
            kind = 'html'
        elif suffix == '.json' or mime == 'application/json':
            json.loads(text); kind = 'json'
        elif suffix in ('.csv', '.tsv') or mime in ('text/csv', 'text/tab-separated-values'):
            kind = 'csv'
        elif suffix in ('.md', '.markdown', '.rst'):
            kind = 'markdown'
        else:
            kind = 'text'
    native = {'pdf': 'application/pdf', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'}
    allowed = {'application/octet-stream', 'binary/octet-stream', 'application/zip', 'application/x-zip-compressed'}
    if kind in native:
        require(mime == native[kind] or mime in allowed, 'mime_magic_mismatch')
    elif kind == 'image':
        require(mime.startswith('image/') or mime in allowed, 'mime_magic_mismatch')
    elif kind == 'media':
        require(mime.startswith(('audio/','video/')) or mime in allowed,'mime_magic_mismatch')
    else:
        require(mime.startswith('text/') or mime in allowed | {'application/json', 'application/xhtml+xml'}, 'mime_magic_mismatch')
    declared = {'.pdf':'pdf', '.xlsx':'xlsx', '.docx':'docx', '.pptx':'pptx', '.json':'json', '.csv':'csv'}
    if suffix in declared:
        require(kind == declared[suffix], 'extension_magic_mismatch')
    return kind


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript'): self.skip += 1
        if tag in ('p','div','li','h1','h2','h3','tr','br'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
        if tag in ('p','div','li','h1','h2','h3','tr'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def parse_bytes(data, url, mime):
    kind = detect(data, url, mime)
    segments = []; structure = {}; warnings = []
    def add(locator, text):
        text = normalized(str(text))
        if text:
            require(len(segments) < MAX_SEGMENTS, 'too_many_profile_segments')
            segments.append({'locator':locator, 'text':text})
    if kind == 'pdf':
        import pdfplumber
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        require(not reader.is_encrypted, 'encrypted_pdf')
        require(len(reader.pages) <= 150, 'pdf_page_limit')
        root = reader.trailer['/Root']
        require(not any(k in root for k in ('/OpenAction','/AA')) and '/JavaScript' not in root.get('/Names',{}), 'active_pdf_content')
        images = 0; table_count = 0; empty = []
        with pdfplumber.open(io.BytesIO(data)) as doc:
            for number, page in enumerate(doc.pages, 1):
                text = page.extract_text() or ''
                if len(text.strip()) < 20: empty.append(number)
                for line, value in enumerate(text.splitlines(), 1): add(f'page:{number}:line:{line}', value)
                for ti, table in enumerate(page.extract_tables(), 1):
                    table_count += 1
                    for ri, row in enumerate(table, 1): add(f'page:{number}:table:{ti}:row:{ri}', ' | '.join(str(v or '') for v in row))
                images += len(page.images)
        structure = {'pages':len(reader.pages), 'extracted_tables':table_count, 'images':images, 'textless_pages':empty,
                     'visual_content_verified':False}
        if empty: warnings.append('pages_require_visual_inspection')
    elif kind == 'xlsx':
        from openpyxl import load_workbook
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        structure={'sheets':[]}; cells=0
        for sheet in book:
            require(sheet.max_row * sheet.max_column <= 250000, 'worksheet_cell_limit')
            types=set(); numeric=[]; formulas=0
            for row_number,row in enumerate(sheet,1):
                present=[]
                for cell in row:
                    if cell.value is None: continue
                    cells += 1; require(cells <= 250000, 'workbook_cell_limit')
                    types.add(type(cell.value).__name__)
                    if cell.data_type == 'f': formulas += 1
                    if isinstance(cell.value,(int,float)): numeric.append(cell.value)
                    add(f'sheet:{sheet.title}!{cell.coordinate}', cell.value)
                    present.append(f'{cell.coordinate}={cell.value}')
                if present: add(f'sheet:{sheet.title}:row:{row_number}', ' | '.join(present))
            structure['sheets'].append({'name':sheet.title,'rows':sheet.max_row,'columns':sheet.max_column,
                'cell_types':sorted(types),'numeric_range':[min(numeric),max(numeric)] if numeric else None,
                'formula_cells':formulas,'formulas_executed':False})
        book.close()
    elif kind == 'csv':
        text=data.decode('utf-8-sig'); dialect = csv.Sniffer().sniff(text[:8192],delimiters=',;\t|')
        rows=list(csv.reader(io.StringIO(text),dialect)); require(rows and len(rows[0])>1, 'invalid_csv')
        require(len(rows)<=100000 and all(not r or len(r)==len(rows[0]) for r in rows), 'ragged_or_oversized_csv')
        types=[set() for _ in rows[0]]; ranges=[[] for _ in rows[0]]
        for ri,row in enumerate(rows,1):
            if not row: continue
            require(not any(v.lstrip().startswith(('=','@')) for v in row),'csv_formula_injection')
            add(f'row:{ri}', ' | '.join(row))
            if ri>1:
                for j,v in enumerate(row):
                    try: n=float(v); types[j].add('number'); ranges[j].append(n)
                    except ValueError: types[j].add('missing' if not v else 'text')
        structure={'rows':sum(bool(r) for r in rows)-1,'blank_rows':sum(not r for r in rows),'columns':rows[0], 'types':[sorted(t) for t in types],
                   'numeric_ranges':[[min(v),max(v)] if v else None for v in ranges], 'delimiter':dialect.delimiter}
    elif kind in ('docx','pptx'):
        with checked_zip(data) as z:
            names=['word/document.xml'] if kind=='docx' else sorted(n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n))
            tables=0
            for name in names:
                raw=z.read(name); require(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw, 'xml_entity_forbidden')
                tree=ET.fromstring(raw)
                for i,p in enumerate((e for e in tree.iter() if e.tag.rsplit('}',1)[-1]=='p'),1):
                    add(f'{name}:paragraph:{i}', ' '.join(e.text or '' for e in p.iter() if e.tag.rsplit('}',1)[-1]=='t'))
                for i,row in enumerate((e for e in tree.iter() if e.tag.rsplit('}',1)[-1]=='tr'),1):
                    tables+=1; add(f'{name}:table_row:{i}', ' | '.join(e.text or '' for e in row.iter() if e.tag.rsplit('}',1)[-1]=='t'))
            structure={'parts':names, 'table_rows':tables, 'visual_layout_verified':False}
    elif kind == 'repository_zip':
        structure={'files':[], 'executed':False}
        with checked_zip(data) as z:
            require(len(z.infolist())<=300, 'repository_file_limit')
            for name in sorted(z.namelist()):
                if name.endswith('/'): continue
                raw=z.read(name); structure['files'].append({'path':name,'sha256':sha256(raw),'bytes':len(raw)})
                try: text=raw.decode('utf-8')
                except UnicodeError: warnings.append('uninspected_binary:'+name); continue
                for i,line in enumerate(text.splitlines(),1): add(f'file:{name}:line:{i}',line)
    elif kind == 'image':
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            require(im.width*im.height<=25_000_000,'image_pixel_limit')
            im.load(); structure={'width':im.width,'height':im.height,'format':im.format,'visual_content_verified':False}
        warnings.append('visual_inspection_required')
    elif kind == 'media':
        if data[:4]==b'RIFF' and data[8:12]==b'WAVE':
            with wave.open(io.BytesIO(data)) as sound:
                structure={'duration_seconds':sound.getnframes()/sound.getframerate(),'channels':sound.getnchannels(),
                           'sample_rate':sound.getframerate(),'media_type':'audio','perception_verified':False}
        elif shutil.which('ffprobe'):
            with tempfile.NamedTemporaryFile() as stream:
                stream.write(data);stream.flush()
                result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',stream.name],capture_output=True,timeout=15,check=True)
                info=json.loads(result.stdout)
            structure={'duration_seconds':float(info.get('format',{}).get('duration',0)),
                       'streams':[{k:s[k] for k in ('codec_type','codec_name','width','height','sample_rate','channels') if k in s} for s in info.get('streams',[])],
                       'media_type':'video' if any(s.get('codec_type')=='video' for s in info.get('streams',[])) else 'audio','perception_verified':False}
        else:
            structure={'media_type':'video' if mime.startswith('video/') else 'audio','metadata_status':'ffprobe_unavailable','perception_verified':False}
        warnings.append('audio_video_perception_required')
    elif kind == 'json':
        obj=json.loads(data.decode('utf-8-sig'))
        def visit(v,path):
            if isinstance(v,dict):
                for k,x in v.items(): visit(x,path+'/'+str(k).replace('~','~0').replace('/','~1'))
            elif isinstance(v,list):
                for i,x in enumerate(v): visit(x,path+'/'+str(i))
            else: add('json:'+path,json.dumps(v,ensure_ascii=False))
        visit(obj,''); structure={'root_type':type(obj).__name__,'root_keys':list(obj) if isinstance(obj,dict) else None}
    else:
        text=data.decode('utf-8-sig')
        if kind=='html':
            parser=HTMLText(); parser.feed(text); text=''.join(parser.parts)
            warnings.append('html_discovery_only_no_browser_execution')
        for i,line in enumerate(text.splitlines(),1): add(f'line:{i}',line)
        structure={'lines':len(text.splitlines())}
    require(segments or kind in ('image','media'), 'no_readable_content')
    full='\n'.join(s['text'] for s in segments)
    signals=[]
    if re.search(r'\b\d{3}-\d{2}-\d{4}\b|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',full): signals.append('potential_personal_identifiers')
    if re.search(r'\b(?:variance|over budget|under budget|recommendations?|RAG rating)\b',full,re.I): signals.append('possible_precomputed_analysis')
    return add_segment_ids({'file_id':'f_'+sha256(data)[:24], 'sha256':sha256(data),'type':kind,'parse_status':'parsed',
            'structure':structure,'segments':segments,'warnings':warnings,'risk_signals':signals,
            'profiling_version':VERSION})


def add_segment_ids(profile):
    from common import json_bytes
    for segment in profile.get('segments',[]):
        segment.setdefault('evidence_method','programmatic_extraction')
        segment['verification_status']='model_observation_unverified' if segment['evidence_method'].startswith('model_') else 'source_located'
        content={k:v for k,v in segment.items() if k!='segment_id'}
        segment['segment_id']='seg_'+sha256(json_bytes({'file_sha256':profile['sha256'],'segment':content}))[:24]
    require(len(profile.get('segments',[]))==len({s['segment_id'] for s in profile.get('segments',[])}),'duplicate_segment_id')
    return profile


def profile(path, url, mime, cache):
    data=path.read_bytes()
    key=sha256((sha256(data)+url+mime+VERSION+sha256(Path(__file__).read_bytes())).encode())
    record=cache/'profiles'/(key+'.json')
    if record.exists(): return json.loads(record.read_text())
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(path.resolve()),url,mime],
                              capture_output=True,timeout=55,check=False)
        require(result.returncode==0,'parser_process_failed')
        value=json.loads(result.stdout)
        # Child failures still need identity so rejected files remain traceable.
        value.update(file_id='f_'+sha256(data)[:24],sha256=sha256(data))
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
        value={'file_id':'f_'+sha256(data)[:24],'sha256':sha256(data),'parse_status':'rejected',
               'reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__}
    save(record,value); return value


if __name__=='__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(45,45))
    resource.setrlimit(resource.RLIMIT_AS,(2_000_000_000,2_000_000_000))
    try: value=parse_bytes(Path(sys.argv[1]).read_bytes(),sys.argv[2],sys.argv[3])
    except Exception as exc:
        value={'parse_status':'rejected','reason':str(exc) if isinstance(exc,DataError) else type(exc).__name__}
    print(json.dumps(value,ensure_ascii=False,allow_nan=False))
