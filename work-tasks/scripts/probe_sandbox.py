"""Linux-only, fail-closed local Python tool. No repository/credential mounts.

Trusted host orchestrator requires root to chroot; generated code runs as nobody,
with no network/process creation and only outputs/scratch/tmp writable. This is
process isolation on the host kernel, not a VM or an adversarial security proof.
"""
import ctypes
import errno
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time

VERSION = 'chroot-python-v1'
BOOTSTRAP = '''import ctypes, errno, json, sys
lib = ctypes.CDLL('/usr/lib/x86_64-linux-gnu/libseccomp.so.2')
lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
ctx=lib.seccomp_init(0x7fff0000)
if not ctx: raise RuntimeError('seccomp_init_failed')
for name in ('socket','socketpair','connect','bind','listen','accept','accept4','ptrace','process_vm_readv','process_vm_writev','mount','umount2','pivot_root','chroot','unshare','setns','clone','clone3','fork','vfork','execve','execveat','open_by_handle_at','name_to_handle_at','bpf','perf_event_open','keyctl','add_key','request_key','io_uring_setup','userfaultfd','reboot','kexec_load','init_module','finit_module','delete_module'):
    number=lib.seccomp_syscall_resolve_name(name.encode())
    if number >= 0 and lib.seccomp_rule_add(ctx,0x50000|errno.EPERM,number,0)!=0: raise RuntimeError('seccomp_rule_failed')
if lib.seccomp_load(ctx)!=0: raise RuntimeError('seccomp_load_failed')
lib.seccomp_release(ctx)
code=json.load(sys.stdin)['code']
exec(compile(code,'<solver-python>','exec'),{'__name__':'__main__'})
'''


def runtime(root):
    """Copy only installed trusted interpreter, selected packages, and dependencies."""
    root=Path(root)
    if root.exists(): raise ValueError('sandbox_already_exists')
    if os.geteuid()!=0 or sys.platform!='linux': raise RuntimeError('requires_linux_chroot_privilege')
    root.mkdir(parents=True)
    binary=root/'runtime/bin/python';binary.parent.mkdir(parents=True)
    shutil.copy2(Path(sys.executable).resolve(),binary)
    stdlib=Path(sysconfig.get_path('stdlib'))
    dest=root/'runtime/lib'/stdlib.name
    shutil.copytree(stdlib,dest,ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests','idlelib','tkinter','turtledemo','ensurepip'))
    site=dest/'site-packages';site.mkdir()
    for name in ('openpyxl','et_xmlfile','pypdf'):
        spec=importlib.util.find_spec(name)
        if spec is None: raise RuntimeError('missing_runtime_package:'+name)
        src=Path(spec.origin).parent
        shutil.copytree(src,site/name,ignore=shutil.ignore_patterns('__pycache__','tests'))
    # ldd is used only on locally installed trusted Python libraries, never attachments.
    libs=[Path(sys.executable).resolve(),*stdlib.glob('lib-dynload/*.so'),Path('/usr/lib/x86_64-linux-gnu/libseccomp.so.2')]
    seen=set()
    while libs:
        source=Path(os.path.normpath(libs.pop()))
        if str(source) in seen: continue
        seen.add(str(source))
        if source.is_absolute() and not source.is_relative_to(root):
            target=(root/'runtime'/source.relative_to(sys.base_prefix)) if source.is_relative_to(sys.base_prefix) else root/str(source).lstrip('/')
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
        result=subprocess.run(['ldd',str(source)],capture_output=True,text=True,timeout=10)
        for token in result.stdout.split():
            if token.startswith('/') and Path(token).is_file() and token not in seen: libs.append(Path(token))
    (root/'runtime/bootstrap.py').write_text(BOOTSTRAP)
    for name in ('work','tmp'):(root/name).mkdir(exist_ok=True)
    for p in root.rglob('*'):
        p.chmod(0o755 if p.is_dir() or p==binary else (p.stat().st_mode & 0o755))
    return root


def writable(root):
    for name in ('work/outputs','work/scratch','tmp'):
        p=Path(root)/name;p.mkdir(exist_ok=True);p.chmod(0o700);os.chown(p,65534,65534)


def execute(root,code,timeout=90):
    root=Path(root).resolve()
    if not isinstance(code,str) or len(code)>200000: raise ValueError('invalid_code_size')
    def isolate():
        os.chroot(root);os.chdir('/work')
        os.setgroups([]);os.setgid(65534);os.setuid(65534)
        libc=ctypes.CDLL(None,use_errno=True)
        if libc.prctl(38,1,0,0,0)!=0: os._exit(120) # PR_SET_NO_NEW_PRIVS
        resource.setrlimit(resource.RLIMIT_CPU,(timeout,timeout))
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024**2,20*1024**2))
        resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    started=time.monotonic()
    with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
        p=subprocess.Popen(['/runtime/bin/python','-B','/runtime/bootstrap.py'],stdin=subprocess.PIPE,
            stdout=out,stderr=err,preexec_fn=isolate,start_new_session=True,close_fds=True,
            env={'PATH':'/runtime/bin','LANG':'C.UTF-8','PYTHONHOME':'/runtime','PYTHONHASHSEED':'0','LD_LIBRARY_PATH':'/runtime/lib'})
        timed_out=False
        try:p.communicate(json.dumps({'code':code}).encode(),timeout=timeout+5)
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(p.pid,signal.SIGKILL);p.communicate()
        out.seek(0);err.seek(0);stdout=out.read(65537);stderr=err.read(65537)
    return {'returncode':p.returncode,'timed_out':timed_out,'elapsed_seconds':round(time.monotonic()-started,3),
            'stdout':stdout[:65536].decode(errors='replace'),'stderr':stderr[:65536].decode(errors='replace'),
            'truncated':len(stdout)>65536 or len(stderr)>65536}


def preflight(root):
    code="""import os, socket, pathlib, subprocess
assert os.getuid()==65534
assert not pathlib.Path('/proc').exists()
assert not pathlib.Path('/user').exists()
assert not pathlib.Path('/root').exists()
assert not any('KEY' in k or 'TOKEN' in k for k in os.environ)
for path in ['/runtime/bootstrap.py','task.json']:
    try: open(path,'a').write('BAD')
    except PermissionError: pass
    else: raise AssertionError('input_writable')
try: socket.socket()
except PermissionError: pass
else: raise AssertionError('network_available')
try: os.fork()
except PermissionError: pass
else: raise AssertionError('fork_available')
import csv, statistics, zipfile, sqlite3, openpyxl, pypdf
p=pathlib.Path('outputs/.preflight');p.write_text('ok');assert p.read_text()=='ok';p.unlink()
print('isolation_preflight_passed')"""
    result=execute(root,code)
    if result['returncode'] or result['stdout'].strip()!='isolation_preflight_passed':
        raise RuntimeError('sandbox_preflight_failed:'+json.dumps(result))
    return result


def mcp(root,log):
    """Single capability, no shell/host paths; MCP stdout is protocol only."""
    log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
    for line in sys.stdin:
        request=json.loads(line)
        if 'id' not in request:continue
        method=request['method'];params=request.get('params',{})
        try:
            if method=='initialize':
                result={'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'workprobe','version':VERSION}}
            elif method=='tools/list':
                result={'tools':[{'name':'python','description':'Execute Python in /work. Only task.json and workspace_init are task inputs. Persist files in outputs or scratch. No network or subprocesses. stdlib, openpyxl, pypdf available. State resets each call; files persist. 90 second/2 GiB per call.','inputSchema':{'type':'object','properties':{'code':{'type':'string'}},'required':['code'],'additionalProperties':False}}]}
            elif method=='tools/call':
                if params['name']!='python':raise ValueError('unknown_tool')
                code=params['arguments']['code'];record={'code':code,**execute(root,code)}
                with log.open('a') as f:f.write(json.dumps(record)+'\n')
                result={'content':[{'type':'text','text':json.dumps({k:v for k,v in record.items() if k!='code'})}],'isError':record['returncode']!=0}
            elif method=='ping':result={}
            else:raise ValueError('unsupported_method')
            response={'jsonrpc':'2.0','id':request['id'],'result':result}
        except Exception as exc:response={'jsonrpc':'2.0','id':request['id'],'error':{'code':-32603,'message':str(exc)}}
        print(json.dumps(response),flush=True)


if __name__=='__main__':
    mcp(Path(sys.argv[1]),Path(sys.argv[2]))
