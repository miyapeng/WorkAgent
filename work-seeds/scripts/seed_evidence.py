"""Real-source retrieval, paragraph extraction, content-addressed caching."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from build_onet import DataError, json_bytes, sha256

RETRIEVAL_VERSION = 'paragraphs-v2-bls-duties'


def now(): return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(json_bytes(value)); tmp.replace(path)


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in records), encoding='utf-8')
    tmp.replace(path)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []


def normalized(text): return ' '.join(text.split())


STOP = set('the and for from with that this into their they them are was were have has will can may using other such work information about of to or in on a an as by at is be'.split())


def tokens(text): return {w for w in re.findall(r'[a-z]{3,}', text.lower()) if w not in STOP}


def canonical_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise DataError('Source URL must be public HTTP(S) without embedded credentials')
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, p.query, ''))


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0; self.depth = 0; self.buf = []; self.items = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'header', 'footer'): self.skip += 1
        if not self.skip and tag in ('p', 'li'):
            if self.depth == 0: self.buf = []
            self.depth += 1
        if tag == 'br' and self.depth: self.buf.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'header', 'footer'):
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in ('p', 'li') and self.depth:
            self.depth -= 1
            if self.depth == 0:
                text = normalized(''.join(self.buf))
                if 50 <= len(text) <= 1800: self.items.append(text)

    def handle_data(self, data):
        if self.depth and not self.skip: self.buf.append(data)


def request_json(url, payload, key_env=None, timeout=30):
    headers = {'Content-Type': 'application/json', 'User-Agent': 'WorkSeedsResearch/1.0'}
    if key_env:
        key = os.environ.get(key_env)
        if not key: raise DataError(f'missing_api_key_env:{key_env}')
        headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(url, data=json_bytes(payload), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # Do not persist response bodies or secrets in errors.
        raise DataError(f'http_status:{exc.code}') from None


def fetch_document(url, cache, timeout=20):
    url = canonical_url(url)
    path = cache / 'documents' / (sha256(url.encode()) + '.json')
    if path.exists():
        record = json.loads(path.read_text())
        raw = (cache / 'documents' / record['body_file']).read_bytes()
        if sha256(raw) != record['document_sha256']: raise DataError('document_cache_hash_mismatch')
    else:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (WorkSeeds occupational research)'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read(4_000_001)
                if len(raw) > 4_000_000: raise DataError('document_too_large')
                if 'html' not in response.headers.get('Content-Type', ''): raise DataError('unsupported_document_type')
                record = {'requested_url': url, 'source_url': canonical_url(response.url),
                          'document_sha256': sha256(raw), 'retrieved_at': now(),
                          'encoding': response.headers.get_content_charset() or 'utf-8',
                          'body_file': sha256(raw) + '.html'}
        except urllib.error.HTTPError as exc: raise DataError(f'source_http_status:{exc.code}') from None
        path.parent.mkdir(parents=True, exist_ok=True)
        (path.parent / record['body_file']).write_bytes(raw)
        save(path, record)
    html = raw.decode(record['encoding'])
    if urllib.parse.urlsplit(record['source_url']).hostname in ('www.bls.gov', 'blsmon1.bls.gov'):
        section = re.search(r'<article\b[^>]*aria-labelledby="what-they-do"[^>]*>(.*?)</article>', html, re.S | re.I)
        if not section: raise DataError('bls_duties_section_missing')
        html = section[1]
    parser = Paragraphs(); parser.feed(html)
    return record, sorted(set(parser.items))


def source_urls(query, pair, config, config_dir, cache):
    if config['provider'] == 'url_manifest':
        data = json.loads((config_dir / config['manifest']).read_text())
        sources = [s['url'] for s in data['sources'] if s['occupation_code'] == pair[0]
                   and ('dwa_id' not in s or s['dwa_id'] == pair[1])]
    elif config['provider'] == 'http_search':
        key = sha256(json_bytes({'query': query, 'config': config}))
        path = cache / 'search' / (key + '.json')
        if path.exists(): response = json.loads(path.read_text())
        else:
            response = request_json(config['endpoint'], {'query': query}, config.get('api_key_env'), config.get('timeout_seconds', 20))
            save(path, response)
        sources = [s['url'] for s in response['results']]
    else: raise DataError('unsupported_retrieval_provider')
    return sorted({canonical_url(u) for u in sources})[:config.get('max_sources_per_pair', 2)]


def retrieve_pair(pair, tids, catalog, config, config_dir, cache):
    occupation = catalog['occupations'][pair[0]]['occupation_title']
    dwa = catalog['dwas'][pair[1]]['dwa_name']
    task_text = ' '.join(catalog['tasks'][t]['task_text'] for t in tids)
    query = f'{occupation} | {dwa} | {task_text} | professional duties documentation'
    urls = source_urls(query, pair, config, config_dir, cache)
    if not urls: return [], {'reason': 'no_source_urls', 'query_sha256': sha256(query.encode()), 'source_errors': []}
    scored, errors = [], []
    target = tokens(dwa + ' ' + task_text)
    for url in urls:
        try:
            document, paragraphs = fetch_document(url, cache, config.get('timeout_seconds', 20))
            for excerpt in paragraphs:
                score = len(tokens(excerpt) & target)
                if score < 2: continue
                eid = 'ev_' + sha256((document['source_url'] + '\0' + excerpt).encode())[:24]
                scored.append((score, {'evidence_id': eid, 'source_url': document['source_url'],
                    'excerpt': excerpt, 'document_sha256': document['document_sha256'],
                    'retrieved_at': document['retrieved_at'], 'occupation_dwa_pairs': [list(pair)]}))
        except (OSError, ValueError, KeyError) as exc:
            errors.append({'url': url, 'reason': str(exc) if isinstance(exc, DataError) else type(exc).__name__})
    # These are retrieved lexical matches, not assertions of semantic support.
    scored.sort(key=lambda x: (-x[0], x[1]['evidence_id']))
    evidence = [v for _, v in scored[:config.get('max_passages_per_pair', 3)]]
    return evidence, {'reason': 'retrieved' if evidence else 'no_valid_passages', 'query_sha256': sha256(query.encode()), 'source_errors': errors}
