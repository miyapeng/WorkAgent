"""Real HTTP search providers with query receipts; no invented or implicit URL fallback."""
import json
import os
from urllib.parse import urlencode
from common import require,sha256,json_bytes,save,DataError
from acquire import https_request,public_url


def available(config):
    name=config['provider']
    if name=='claude_code':
        from claude_search import available as claude_available
        return claude_available(config)
    if name in ('disabled','url_manifest'):return False
    require(name in ('tavily','brave','serper'),'unsupported_search_provider')
    return bool(os.environ.get(config['api_key_env']))


def search(query,config,cache,offline=False):
    key=sha256(json_bytes({'query':query,'config':config}));path=cache/'search'/(key+'.json')
    if path.exists():
        receipt=json.loads(path.read_text());require(receipt['query']==query,'search_cache_mismatch');return receipt
    if config['provider']=='claude_code':
        from claude_search import search_query
        if not offline and not available(config):
            return {'query':query,'provider':'claude_code','status':'awaiting_search','results':[],
                    'reason':'missing_claude_cli_or_inference_key','search_api_called':False}
        receipt=search_query(query,config,cache,offline)
        save(path,receipt)
        return receipt
    if config['provider']=='url_manifest':
        return {'query':query,'provider':'url_manifest','status':'awaiting_search','results':[],
                'reason':'Manifest replay is not autonomous search. Configure a real provider.','search_api_called':False}
    if not available(config):return {'query':query,'provider':config['provider'],'status':'awaiting_search','results':[],
                                    'reason':'missing_search_api_credentials','search_api_called':False}
    require(not offline,'offline_search_cache_missing:'+key)
    token=os.environ[config['api_key_env']];name=config['provider'];limit=config.get('max_results',6)
    if name=='tavily':
        endpoint='https://api.tavily.com/search';headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
        payload=json_bytes({'query':query,'max_results':limit,'search_depth':'basic','include_answer':False,'include_raw_content':False,'include_usage':True})
    elif name=='brave':
        endpoint='https://api.search.brave.com/res/v1/web/search?'+urlencode({'q':query,'count':limit})
        headers={'X-Subscription-Token':token};payload=None
    else:
        endpoint='https://google.serper.dev/search';headers={'X-API-KEY':token,'Content-Type':'application/json'};payload=json_bytes({'q':query,'num':limit})
    raw,transport=https_request(endpoint,payload=payload,headers=headers,max_bytes=3_000_000,timeout=config.get('timeout_seconds',30),proxy_env=config.get('trusted_proxy_env'))
    value=json.loads(raw)
    if name=='tavily':rows=value['results']
    elif name=='brave':rows=value.get('web',{}).get('results',[])
    else:rows=value.get('organic',[])
    require(isinstance(rows,list),'search_results_schema')
    results=[];invalid=[]
    for row in rows[:limit]:
        try:
            url=public_url(row.get('url') or row['link'])
            results.append({'candidate_id':'c_'+sha256(url.encode())[:24],'url':url,'source_page':url,'title':str(row.get('title',''))[:500],
                            'snippet':str(row.get('content') or row.get('description') or row.get('snippet',''))[:1800]})
        except (ValueError,KeyError,TypeError):invalid.append('invalid_or_non_https_result')
    receipt={'provider':name,'query':query,'status':'searched','results':list({r['candidate_id']:r for r in results}.values()),
             'searched_at':transport['retrieved_at'],'response_sha256':transport['sha256'],'search_api_called':True,'invalid_results':invalid,
             'provider_usage':value.get('usage'),'billed_cost':None}
    save(path,receipt);return receipt
