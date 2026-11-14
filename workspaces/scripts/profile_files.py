"""Parse bytes as data only. No macros, downloaded code, or shell commands run."""
import csv
import io
import json
import re
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from common import DataError, require, normalized, sha256, save

VERSION = 'native-profiles-v5-streaming-csv'
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
    require(not mime.startswith(('audio/','video/')) and suffix not in ('.wav','.mp3','.mp4','.mov','.ogg','.flac','.webm'), 'audio_video_out_of_scope')
    if data.startswith(b'%PDF-'):
        kind = 'pdf'
    elif data.startswith(b'PK\x03\x04'):
        with checked_zip(data) as z:
            names = set(z.namelist())
            kind = 'xlsx' if 'xl/workbook.xml' in names else 'docx' if 'word/document.xml' in names else 'pptx' if 'ppt/presentation.xml' in names else 'repository_zip'
    elif data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'II*\x00', b'MM\x00*')):
        kind = 'image'
    elif (data[:4]==b'RIFF' and data[8:12]==b'WAVE') or data.startswith((b'ID3',b'OggS',b'fLaC')) or data[4:8]==b'ftyp':
        raise DataError('audio_video_out_of_scope')
    else:
        text = data.decode('utf-8-sig')
        require('\x00' not in text, 'binary_or_invalid_text')
        leading=re.sub(r'^(?:\s|<!--.*?-->|<\?xml.*?\?>)*','',text,flags=re.S)
        if re.search(r'<(?:!doctype\s+html|html|head|body)\b', text[:2000], re.I) or re.match(r'<(?:table|div|main|article|section|p|h[1-6]|script|style|form|iframe|span)\b',leading,re.I):
            kind = 'html'
        elif suffix == '.svg' or mime == 'image/svg+xml' or re.search(r'<svg\b',text[:2000],re.I):
            kind = 'svg'
        elif suffix in ('.json','.ipynb') or mime in ('application/json','application/x-ipynb+json'):
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
    elif kind == 'svg':
        require(mime in allowed | {'image/svg+xml','text/xml','application/xml','text/plain'},'mime_magic_mismatch')
    else:
        require(mime.startswith('text/') or mime in allowed | {'application/json', 'application/xhtml+xml','application/x-ipynb+json','application/x-tex','application/x-latex','application/javascript','application/x-python'}, 'mime_magic_mismatch')
    declared = {'.pdf':'pdf', '.xlsx':'xlsx', '.docx':'docx', '.pptx':'pptx', '.json':'json', '.ipynb':'json', '.svg':'svg', '.csv':'csv'}
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
        text=data.decode('utf-8-sig'); dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t|')
        reader=csv.reader(io.StringIO(text),dialect,strict=True)
        columns=next(reader,[]); require(len(columns)>1,'invalid_csv')
        types=[set() for _ in columns]; ranges=[None for _ in columns]
        count=0;blanks=0;stored=0;add('row:1',' | '.join(columns))
        for ri,row in enumerate(reader,2):
            require(ri<=1_000_001,'oversized_csv')
            if not row:blanks+=1;continue
            require(len(row)==len(columns),'ragged_or_oversized_csv')
            require(not any(v.lstrip().startswith(('=','@')) for v in row),'csv_formula_injection')
            count+=1
            # Only the private evidence index is bounded. Every source record is parsed,
            # and the original file bytes delivered to the Agent remain complete.
            if stored<1024:add(f'row:{ri}',' | '.join(row));stored+=1
            for j,v in enumerate(row):
                try:
                    n=float(v)
                    import math
                    if not math.isfinite(n):types[j].add('nonfinite_number');continue
                    types[j].add('number');ranges[j]=[n,n] if ranges[j] is None else [min(ranges[j][0],n),max(ranges[j][1],n)]
                except ValueError:types[j].add('missing' if not v else 'text')
        structure={'rows':count,'blank_rows':blanks,'columns':columns,'types':[sorted(t) for t in types],
                   'numeric_ranges':ranges,'delimiter':dialect.delimiter,
                   'parsed_data_rows':count,'indexed_data_rows':stored,'content_fully_segmented':stored==count}
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
    elif kind == 'svg':
        require(b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(), 'xml_entity_forbidden')
        tree=ET.fromstring(data)
        require(tree.tag.rsplit('}',1)[-1]=='svg','invalid_svg_root')
        for i,e in enumerate(tree.iter(),1):
            tag=e.tag.rsplit('}',1)[-1]
            require(tag.lower() not in ('script','foreignobject'),'active_svg_content')
            for key,value in e.attrib.items():
                key=key.rsplit('}',1)[-1].lower()
                require(not key.startswith('on') and (key!='href' or value.startswith('#')) and 'url(' not in value.lower(),'active_svg_reference')
            require('url(' not in (e.text or '').lower(),'active_svg_reference')
            add(f'svg:element:{i}',json.dumps({'tag':tag,'attributes':e.attrib,'text':e.text or ''},ensure_ascii=False,sort_keys=True))
        structure={'elements':sum(1 for _ in tree.iter()),'viewBox':tree.attrib.get('viewBox'),'visual_content_verified':False,'rendered':False}
        warnings.append('svg_structure_only_visual_inspection_required')
    elif kind == 'json':
        obj=json.loads(data.decode('utf-8-sig'))
        def visit(v,path):
            if isinstance(v,dict):
                for k,x in v.items(): visit(x,path+'/'+str(k).replace('~','~0').replace('/','~1'))
            elif isinstance(v,list):
                for i,x in enumerate(v): visit(x,path+'/'+str(i))
            else: add('json:'+path,json.dumps(v,ensure_ascii=False))
        visit(obj,''); structure={'root_type':type(obj).__name__,'root_keys':list(obj) if isinstance(obj,dict) else None}
        if Path(urlsplit(url).path).suffix.lower()=='.ipynb':
            require(isinstance(obj,dict) and isinstance(obj.get('cells'),list) and obj.get('nbformat')==4,'invalid_notebook_structure')
            require(all(isinstance(c,dict) and c.get('cell_type') in ('code','markdown','raw') and isinstance(c.get('source'),(str,list)) for c in obj['cells']),'invalid_notebook_cell')
            structure.update(cells=len(obj['cells']),cells_with_outputs=sum(bool(c.get('outputs')) for c in obj['cells']),executed=False)
            if structure['cells_with_outputs']:warnings.append('notebook_contains_existing_outputs_review_for_answer_leakage')
    else:
        text=data.decode('utf-8-sig')
        if kind=='html':
            parser=HTMLText(); parser.feed(text); text=''.join(parser.parts)
            warnings.append('html_discovery_only_no_browser_execution')
        for i,line in enumerate(text.splitlines(),1): add(f'line:{i}',line)
        structure={'lines':len(text.splitlines())}
    require(segments or kind=='image', 'no_readable_content')
    suffix=Path(urlsplit(url).path).suffix.lower().lstrip('.')
    actual_format=structure['format'].lower() if kind=='image' else ('zip' if kind=='repository_zip' else ('md' if kind=='markdown' else kind))
    if suffix in ('tex','py','js') and kind=='text':actual_format=suffix;structure['executed_or_compiled']=False
    if suffix=='ipynb' and kind=='json':actual_format='ipynb'
    if kind=='text' and actual_format=='text':actual_format='txt'
    # A bounded evidence index must not narrow the scan for risk indicators.
    full=data.decode('utf-8-sig') if kind=='csv' else '\n'.join(s['text'] for s in segments)
    signals=[]
    if re.search(r'\b\d{3}-\d{2}-\d{4}\b|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',full): signals.append('potential_personal_identifiers')
    if re.search(r'\b(?:variance|over budget|under budget|recommendations?|RAG rating)\b',full,re.I): signals.append('possible_precomputed_analysis')
    return add_segment_ids({'file_id':'f_'+sha256(data)[:24], 'sha256':sha256(data),'type':kind,'format':actual_format,'parse_status':'parsed',
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
