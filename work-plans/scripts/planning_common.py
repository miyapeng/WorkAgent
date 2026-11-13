"""Small shared model/cache utilities for the new Stage 2–3 flow."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'work-seeds/scripts'))
from build_onet import DataError, sha256, json_bytes
from seed_evidence import save, read_jsonl, write_jsonl
from construct_seeds import llm_call


def require(condition,reason):
    if not condition:raise DataError(reason)


def schema(path):return json.loads(Path(path).read_text())


def validate(value,spec):
    errors=sorted(Draft202012Validator(spec).iter_errors(value),key=lambda e:str(list(e.path)))
    require(not errors,'schema:'+('; '.join(str(list(e.path))+': '+e.message[:200] for e in errors[:4])))


def load_llm(config,config_path,offline=False):
    llm=schema(Path(config_path).parent/config['llm_config'])['llm']
    override=config.get('llm_overrides',{})
    llm={**llm,**override,'parameters':{**llm.get('parameters',{}),**override.get('parameters',{})}}
    env=llm['api_key_env']
    if not offline and not os.environ.get(env) and config.get('credential_source')=='llmctl':
        path=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'llmctl/config.json'
        require(path.exists(),'missing_llmctl_config')
        auth=schema(path)
        require(urlsplit(auth['api']).hostname==urlsplit(llm['endpoint']).hostname,'llmctl_endpoint_mismatch')
        require(auth.get('access_key'),'missing_llmctl_access_key')
        os.environ[env]=auth['access_key']
    return llm


def model_call(llm,prompt_path,context,cache,offline=False):
    path=Path(prompt_path);prompt=path.read_text();version=path.stem
    payload={'model':llm['model'],**llm.get('parameters',{}),'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(context,ensure_ascii=False,sort_keys=True)}]}
    key=sha256(json_bytes({'endpoint':llm['endpoint'],'payload':payload,'prompt_version':version}))
    cached=Path(cache)/'llm'/(key+'.json')
    require(not offline or cached.exists(),'offline_model_cache_missing:'+key)
    try:
        value,meta=llm_call(llm,prompt,context,Path(cache),prompt_version=version)
    except DataError as exc:
        if cached.exists():
            record=schema(cached)
            exc.model_metadata={k:v for k,v in record.items() if k!='response'}
            exc.model_metadata.update(usage=record['response'].get('usage',{}),prompt_sha256=sha256(prompt.encode()))
        raise
    record=schema(cached)
    meta['usage']=record['response'].get('usage',{})
    meta['prompt_sha256']=sha256(prompt.encode())
    return value,meta


def usage(calls):
    unique={c['request_sha256']:c for c in calls}
    return {'unique_model_requests':len(unique),'prompt_tokens':sum(c.get('usage',{}).get('prompt_tokens',0) for c in unique.values()),
            'completion_tokens':sum(c.get('usage',{}).get('completion_tokens',0) for c in unique.values()),
            'billed_cost':None,'currency':None,'cost_note':'Gateway token usage retained. No confirmed billing tariff/receipt; money cost unknown. Cache replay is not a new billed call.'}
