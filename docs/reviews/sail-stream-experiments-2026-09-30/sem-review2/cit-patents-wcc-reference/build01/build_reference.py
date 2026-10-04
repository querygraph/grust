#!/usr/bin/env python3
"""Build and qualify the exact kernel in a fresh private directory."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import resource
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
COMPILER = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++'

def info(path):
    return dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    private=Path(tempfile.mkdtemp(prefix='cit-patents-wcc-reference-'))
    binary=private/'wcc-reference'
    source=HERE/'wcc_reference.cpp';controls=HERE/'test_reference.py'
    original={p.name:info(p) for p in [source,controls]}
    command=[COMPILER,'-std=c++17','-O2','-g0','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)]
    receipt=dict(started_utc=datetime.now(timezone.utc).isoformat(),outcome='STARTED',private_directory=str(private),compiler=COMPILER,compiler_version=subprocess.check_output([COMPILER,'--version'],text=True),compiler_file=info(Path(COMPILER)),platform=platform.platform(),build_command=command,source_files=original)
    try:
        result=subprocess.run(command,capture_output=True,text=True)
        with (out/'compiler.log').open('x') as stream:stream.write(result.stdout+result.stderr)
        result.check_returncode()
        compiler_peak=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        compiler_peak=int(compiler_peak if platform.system()=='Darwin' else compiler_peak*1024)
        assert compiler_peak<1<<30
        receipt['compiler_observed_peak_rss_bytes']=compiler_peak
        test=[sys.executable,'-I','-B',str(controls),str(binary),str(private/'controls')]
        tested=subprocess.run(test,capture_output=True,text=True)
        with (out/'controls.stderr').open('x') as stream:stream.write(tested.stderr)
        with (out/'controls.json').open('x') as stream:stream.write(tested.stdout)
        receipt.update(control_command=test,control_returncode=tested.returncode)
        tested.check_returncode();assert json.loads(tested.stdout)['outcome']=='PASS_PRODUCTION_KERNEL_BFS_CONTROLS'
        assert original=={p.name:info(p) for p in [source,controls]}
        receipt.update(outcome='PASS_FROZEN_KERNEL_BUILD_AND_CONTROLS',binary={'path':str(binary),**info(binary)},controls=info(out/'controls.json'))
    except BaseException as error:
        receipt.update(outcome='FAILED',error=repr(error));raise
    finally:
        receipt['finished_utc']=datetime.now(timezone.utc).isoformat()
        with (out/'build-receipt.json').open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(outcome=receipt['outcome'],private_directory=str(private),binary_sha256=receipt['binary']['sha256'])))

if __name__=='__main__':main()
