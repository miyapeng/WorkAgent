#!/usr/bin/env python3
"""Engineering-only end-to-end demo. No production input overrides or official data."""
import argparse
import getpass
import os
import sys
from task_common import *
sys.path.insert(0,str(ROOT/'tests'))
from fixture_support import create_fixture, FixtureModel
from construct_tasks import process_workspace, Model, export_agent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT/'data/synthetic_test_fixture')
    p.add_argument('--live-model',action='store_true',help='Actual configured LLM calls on fictional data; failure stays failure')
    p.add_argument('--offline',action='store_true')
    p.add_argument('--prompt-api-key',action='store_true')
    a=p.parse_args()
    code_hashes={p.name:sha256(p.read_bytes()) for p in (ROOT/'scripts').glob('*.py')}
    require(a.root.resolve()!= (ROOT/'generated').resolve() and not a.root.resolve().is_relative_to((ROOT/'generated').resolve()),'fixture_output_must_not_be_formal_generated')
    if (a.root/'inputs/SYNTHETIC_TEST_WS').exists():
        # Fixture source data is fixed; regenerate only in a fresh temporary directory and compare it.
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            _,plan,seed=create_fixture(Path(temp))
        directory=a.root/'inputs/SYNTHETIC_TEST_WS'
    else:directory,plan,seed=create_fixture(a.root/'inputs')
    if a.live_model:
        config=read(ROOT/'config/stage4.json');llm=read((ROOT/'config'/config['llm_config']).resolve())['llm']
        llm={**llm,'parameters':{**llm.get('parameters',{}),'max_tokens':config['max_tokens']},'timeout_seconds':config['timeout_seconds']}
        if a.prompt_api_key:os.environ[llm['api_key_env']]=getpass.getpass('LLMCenter access key: ')
        model=Model(config,llm,a.root/'cache',a.offline)
    else:
        require(not a.prompt_api_key,'key_not_needed_for_mock_fixture');model=FixtureModel()
    record=process_workspace(directory,plan,seed,{},a.root/'cache',a.root/'packages',model,fixture=True)
    if record.get('status')=='draft' and not (a.root/'agent_visible').exists():
        export_agent(a.root/'packages'/record['task_id'],a.root/'agent_visible')
    result={'data_provenance':'synthetic_test_fixture','model_transport':'live_api' if a.live_model else 'mock_no_network',
            'code_sha256':code_hashes,
            'included_in_real_pilot':False,'included_in_training_statistics':False,'record':record}
    save(a.root/'fixture_report.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
