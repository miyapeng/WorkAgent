"""Stage 5 pilot: freeze -> isolated solver -> independent evaluation. No admission claims."""
import argparse
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from task_common import ROOT, read, digest, sha256, save, require, confined
from construct_tasks import export_agent
from claude_search import credentials, analyze_trace
from probe_sandbox import runtime, writable, preflight, VERSION


def hashes(folder):
    result={}
    for p in sorted(folder.rglob('*')):
        require(not p.is_symlink(),'probe_symlink_forbidden')
        if not p.is_dir():
            require(stat.S_ISREG(p.stat().st_mode),'probe_nonregular_file')
            require(p.stat().st_size<=100*1024**2,'probe_file_too_large')
            result[p.relative_to(folder).as_posix()]=sha256(p.read_bytes())
    return result


def verify_package(package):
    manifest=read(package/'manifest.json');require(manifest['status']=='draft','package_not_draft')
    require(manifest.get('interface')!='asset-task-v1','asset_task_requires_visual_probe_adapter_not_yet_implemented')
    for path,h in manifest['package_files'].items():
        require(sha256(confined(package,path).read_bytes())==h,'package_hash_changed:'+path)
    return digest(manifest)


def solve(package,output,config,offline=False):
    package=package.resolve();output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    prompt=(ROOT/'prompts/probe_solver.v1.txt').read_text()
    identity={'package_manifest_sha256':verify_package(package),'solver':config['solver'],
              'prompt_sha256':sha256(prompt.encode()),'sandbox_version':VERSION}
    receipt=output/'execution.json'
    if receipt.exists():
        old=read(receipt);require(old['identity']==identity,'probe_identity_changed_use_new_directory')
        require(hashes(output/'submission')==old['submission_files'],'submission_changed')
        require(sha256((output/'stdout.jsonl').read_bytes())==old['transcript_sha256'],'transcript_changed')
        if old.get('tool_trace_sha256'):
            require(sha256((output/'tool_trace.jsonl').read_bytes())==old['tool_trace_sha256'],'tool_trace_changed')
        return old
    require(not offline,'offline_probe_missing')
    root=output/'sandbox'
    require(not root.exists(),'unfinished_probe_use_new_output_directory')
    runtime(root)
    # export helper validates the current public package and excludes evaluator files.
    (root/'work').rmdir();export_agent(package,root/'work')
    for p in (root/'work').rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
    (root/'work').chmod(0o755)
    writable(root);isolation=preflight(root)
    frozen=hashes(root/'work/workspace_init');public_hash=sha256((root/'work/task.json').read_bytes())
    save(output/'isolation_preflight.json',isolation)
    solver=config['solver'];base,key=credentials(solver);require(key,'missing_inference_key')
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='workagent-probe-cli-') as temp:
        temp=__import__('pathlib').Path(temp)
        mcp={'mcpServers':{'workprobe':{'command':sys.executable,'args':[str(ROOT/'scripts/probe_sandbox.py'),str(root),str(output/'tool_trace.jsonl')]}}}
        save(temp/'mcp.json',mcp)
        cmd=[solver['binary'],'-p','--settings','{"disableAllHooks":true}','--setting-sources','','--strict-mcp-config',
             '--mcp-config',str(temp/'mcp.json'),'--tools','','--allowedTools','mcp__workprobe__python',
             '--permission-mode','dontAsk','--no-session-persistence','--model',solver['model'],
             '--output-format','stream-json','--verbose','--system-prompt',prompt]
        env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':str(temp),'LANG':'C.UTF-8',
             'ANTHROPIC_BASE_URL':base,'ANTHROPIC_AUTH_TOKEN':key,'CLAUDE_CONFIG_DIR':str(temp),
             'CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS':'1','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1',
             'ANTHROPIC_SMALL_FAST_MODEL':solver['model'],'ANTHROPIC_DEFAULT_HAIKU_MODEL':solver['model'],
             'ENABLE_TOOL_SEARCH':'false','CLAUDE_CODE_MAX_OUTPUT_TOKENS':'16000','API_TIMEOUT_MS':'180000'}
        # The API may need the host's configured transport proxy. It is never passed to execution children.
        for name in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY'):
            if name in os.environ:env[name]=os.environ[name]
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,cwd=temp,env=env,start_new_session=True)
        timed_out=False
        try:stdout,stderr=p.communicate('Execute the assignment in /work/task.json now.',timeout=solver['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
    stdout=stdout.replace(key,'[REDACTED]');stderr=stderr.replace(key,'[REDACTED]')
    (output/'stdout.jsonl').write_text(stdout);(output/'stderr.txt').write_text(stderr)
    trace=analyze_trace(stdout)
    names={c['name'] for c in trace['tool_calls']}
    init_tools=set(trace['init'].get('tools') or [])
    tool_boundary_ok=names<={'mcp__workprobe__python'} and init_tools<={'mcp__workprobe__python'} and bool(names)
    unchanged=frozen==hashes(root/'work/workspace_init') and public_hash==sha256((root/'work/task.json').read_bytes())
    require(unchanged,'read_only_inputs_changed')
    # Check outputs BEFORE copying; refuse symlinks and excessive data.
    outputs=hashes(root/'work/outputs')
    require(sum(p.stat().st_size for p in (root/'work/outputs').rglob('*') if p.is_file())<=100*1024**2,'outputs_too_large')
    submission=output/'submission';submission.mkdir()
    shutil.copytree(root/'work/outputs',submission/'outputs')
    result={'identity':identity,'task_id':read(package/'manifest.json')['task_id'],
            'elapsed_seconds':round(time.monotonic()-started,2),'returncode':p.returncode,'timed_out':timed_out,
            'input_integrity_passed':unchanged,'tool_boundary_passed':tool_boundary_ok,
            'tools_exposed':sorted(init_tools),'tools_called':sorted(names),'tool_calls':len(trace['tool_calls']),
            'tool_failures':sum(r.get('is_error',False) for r in trace['tool_results']),
            'model':trace['init'].get('model'),'cli_version':trace['init'].get('claude_code_version'),
            'usage':trace['final'].get('usage'),'cli_cost_estimate_usd':trace['final'].get('total_cost_usd'),
            'billed_cost':None,'cost_note':'CLI estimate is not confirmed gateway billing.',
            'agent_final':trace['final'],'transcript_sha256':sha256(stdout.encode()),
            'submission_files':hashes(submission),'execution_completed':bool(outputs) and tool_boundary_ok and not timed_out and p.returncode==0 and not trace['final'].get('is_error',True),
            'tool_trace_sha256':sha256((output/'tool_trace.jsonl').read_bytes()) if (output/'tool_trace.jsonl').exists() else None,
            'scope':'independent_candidate_submission_not_gold_or_training_admission'}
    save(receipt,result);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=__import__('pathlib').Path,required=True)
    parser.add_argument('--output-dir',type=__import__('pathlib').Path,required=True)
    parser.add_argument('--config',type=__import__('pathlib').Path,default=ROOT/'config/probe.json')
    parser.add_argument('--stage',choices=['solve','evaluate','all'],default='all')
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args();config=read(args.config)
    if args.stage in ('solve','all'):
        r=solve(args.package,args.output_dir,config,args.offline)
        print(__import__('json').dumps({k:r[k] for k in ('execution_completed','tool_calls','elapsed_seconds','timed_out')}),flush=True)
    if args.stage in ('evaluate','all'):
        from probe_evaluate import evaluate
        try:
            result=evaluate(args.package,args.output_dir,config,args.config,args.offline)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            save(args.output_dir/'evaluation_failure.json',{'status':'evaluation_incomplete','reason':str(exc),'training_admitted':False})
            raise
        print(__import__('json').dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
