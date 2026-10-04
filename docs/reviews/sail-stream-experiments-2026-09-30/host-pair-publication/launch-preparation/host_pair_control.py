"""Local control of the frozen pair. Dry by default; each remote call is explicit.

Launch stages only the new supervisor, then starts its durable child. Poll reads
selected host metadata. Collect retrieves closed host artifacts, without a VM
collector or physical-value scan. A timeout leaves remote state uncertain.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import tarfile

FROZEN = Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/host-pair-16k')
OUTPUT = FROZEN.parent/'host-pair-execution'
ROOT = '/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930'
PYTHON = '/usr/local/bin/python3'
NS = 'pair16k-20260930201356'
PLAN_SHA = 'd51e9f4d5a1d16fb18c36e93fcb3d641c017610a7319ee56a203676800dbe1ab'
RUNNER_SHA = '8220b9951c51420bd34ca5e32ba20c2304a1b863aa5f2fa1fa9467e74d60a7f1'
REMOTE_HELPER = ROOT+'/'+NS+'-launch-helper.py'

# No settings/environment changes. The existing runner owns Docker admission.
BOOTSTRAP = r'''
import base64,hashlib,json,os,subprocess,sys
from pathlib import Path
p=json.load(sys.stdin)
assert sys.version_info[:3]==(3,14,7), 'host interpreter version differs'
assert Path(sys.executable).resolve()==Path('/usr/local/bin/python3').resolve()
root=Path(p['root']); helper=Path(p['helper'])
assert root.is_dir() and not root.is_symlink()
assert helper.parent==root and helper.name==p['namespace']+'-launch-helper.py'
for path in (helper,root/p['namespace'],root/(p['namespace']+'-launch-evidence')):
 assert not path.exists() and not path.is_symlink(), 'existing namespace; no retry'
raw=base64.b64decode(p['source'],validate=True)
assert hashlib.sha256(raw).hexdigest()==p['sha256']
with helper.open('xb') as f:
 f.write(raw);f.flush();os.fsync(f.fileno())
code=subprocess.call(['/usr/local/bin/python3','-B',str(helper),'launch',
 '--script-sha256',p['sha256'],'--closure',p['closure'],
 '--closure-sha256',p['closure_sha256'],'--request-sha256',p['request_sha256']],
 stdin=subprocess.DEVNULL)
raise SystemExit(code)
'''


def need(ok, reason):
    if not ok: raise RuntimeError(reason)


def utc(): return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2); f.write('\n')


def local_inputs(args):
    need(args.supervisor.is_file() and not args.supervisor.is_symlink()
         and sha(args.supervisor)==args.supervisor_sha256, 'supervisor pin differs')
    need(sha(Path(__file__))==args.script_sha256, 'local helper pin differs')
    plan_path=FROZEN/(NS+'-plan.json')
    need(sha(plan_path)==PLAN_SHA and sha(FROZEN/'run_host_pair.py')==RUNNER_SHA,
         'frozen plan/runner differs')
    handoff=json.loads((FROZEN/'HANDOFF.json').read_text())
    need(handoff['plan_sha256']==PLAN_SHA and handoff['runner_sha256']==RUNNER_SHA
         and handoff['namespace']==NS and handoff['remote_root']==ROOT, 'handoff differs')
    plan=json.loads(plan_path.read_text())
    for row in plan['runs']:
        need(sha(FROZEN/row['configuration'])==row['configuration_sha256'], 'local config differs')
    return dict(plan_sha256=PLAN_SHA, runner_sha256=RUNNER_SHA,
                handoff_sha256=sha(FROZEN/'HANDOFF.json'), supervisor_sha256=args.supervisor_sha256,
                local_helper_sha256=args.script_sha256)


def unpack(path, output):
    """Validate every archive byte against its manifest before writing members."""
    need(not output.exists() and not output.is_symlink(), 'collection exists; no overwrite')
    with tarfile.open(path, 'r:') as archive:
        members=archive.getmembers()
        names=[m.name for m in members]
        need(len(names)==len(set(names)) and 'collection-manifest.json' in names, 'duplicate/missing manifest')
        need(all(m.isfile() and not PurePosixPath(m.name).is_absolute()
                 and '..' not in PurePosixPath(m.name).parts
                 and str(PurePosixPath(m.name))==m.name and m.size>=0 for m in members),
             'unsafe archive member')
        need(sum(m.size for m in members)<= (2<<30)+(8<<20), 'oversized collection')
        info=archive.getmember('collection-manifest.json')
        need(info.size<=8<<20, 'oversized manifest')
        manifest=json.load(archive.extractfile(info))
        need(manifest['plan_sha256']==PLAN_SHA and isinstance(manifest['files'],dict), 'wrong manifest')
        need(set(names)==set(manifest['files'])|{'collection-manifest.json'}, 'inventory differs')
        for name,pin in manifest['files'].items():
            need(name.startswith(('launch/','study/')), 'unexpected artifact root')
            member=archive.getmember(name)
            need(member.size==pin['bytes'] and
                 hashlib.file_digest(archive.extractfile(member),'sha256').hexdigest()==pin['sha256'],
                 'archive artifact differs: '+name)
        # Never extractall: only already-validated regular members into a new root.
        output.mkdir()
        for member in members:
            destination=output/member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as out, archive.extractfile(member) as source:
                while block:=source.read(1<<20): out.write(block)
        return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('launch','poll','collect'))
    p.add_argument('--execute', action='store_true', help='otherwise no SSH and no files written')
    p.add_argument('--supervisor', type=Path, required=True)
    p.add_argument('--supervisor-sha256', required=True)
    p.add_argument('--script-sha256', required=True)
    p.add_argument('--closure')
    p.add_argument('--closure-sha256')
    p.add_argument('--request-sha256')
    args=p.parse_args()
    pins=local_inputs(args)
    payload=None
    if args.action=='launch':
        need(args.closure and args.closure_sha256 and args.request_sha256, 'physical03 closure pins required')
        payload=json.dumps(dict(root=ROOT, helper=REMOTE_HELPER, namespace=NS,
            source=base64.b64encode(args.supervisor.read_bytes()).decode(), sha256=args.supervisor_sha256,
            closure=args.closure, closure_sha256=args.closure_sha256, request_sha256=args.request_sha256)).encode()
        remote=shlex.join([PYTHON,'-B','-c',BOOTSTRAP])
    else:
        remote=shlex.join([PYTHON,'-B',REMOTE_HELPER,args.action,'--script-sha256',args.supervisor_sha256])
    command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','morrobay',remote]
    if not args.execute:
        print(json.dumps(dict(outcome='PREPARED_NO_REMOTE_OPERATION', action=args.action,
            pins=pins, remote_helper=REMOTE_HELPER, host_python=PYTHON,
            full_six_physical_scans='Separate explicit task after all six records and runner closure.'),indent=2))
        return 0
    OUTPUT.mkdir(exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    prefix=OUTPUT/(stamp+'-'+args.action)
    report=dict(started_utc=utc(), action=args.action, pins=pins, outcome='incomplete',
                scope='Host launch/metadata only; original runner/receipts remain authoritative.')
    # Intent precedes SSH. A failed/timed-out launch is uncertain and never retried automatically.
    save(prefix.with_suffix('.intent.json'), dict(report, closure=args.closure,
         closure_sha256=args.closure_sha256, request_sha256=args.request_sha256))
    outpath=prefix.with_suffix('.tar' if args.action=='collect' else '.stdout')
    errpath=prefix.with_suffix('.stderr')
    try:
        with outpath.open('xb') as out, errpath.open('xb') as err:
            result=subprocess.run(command,input=payload,stdin=None if payload else subprocess.DEVNULL,
                stdout=out,stderr=err,timeout=600 if args.action=='collect' else 90)
        report['returncode']=result.returncode
        need(result.returncode==0, 'remote helper failed; inspect retained stdout/stderr')
        if args.action=='collect':
            manifest=unpack(outpath, Path(str(prefix)+'-files'))
            report['collection_files']=len(manifest['files'])
            report['full_six_records_after_runner_exit']=manifest['selected_status']['full_six_records_after_runner_exit']
        else:
            report['remote_receipt']=json.loads(outpath.read_text())
        report['outcome']='COMPLETED_HOST_METADATA_OPERATION'
        return 0
    except BaseException as error:
        report.update(error=type(error).__name__+': '+str(error),
            remote_state='Unknown on interruption/timeout. Do not retry launch or infer remote descendants stopped.')
        return 2
    finally:
        report['finished_utc']=utc()
        report['outputs']={x.name:dict(bytes=x.stat().st_size,sha256=sha(x)) for x in (outpath,errpath) if x.exists()}
        save(prefix.with_suffix('.receipt.json'),report)
        print(json.dumps(dict(receipt=str(prefix.with_suffix('.receipt.json')),outcome=report['outcome'])))


if __name__=='__main__': raise SystemExit(main())
