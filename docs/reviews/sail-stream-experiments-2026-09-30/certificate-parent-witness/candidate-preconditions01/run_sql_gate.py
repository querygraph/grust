"""Detached Python/certificate gate on a pinned existing local CLI; no builds."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

SUPPORT=Path(__file__).resolve().parent.parent/'resource-validation-union/sql_gate.py'
spec=importlib.util.spec_from_file_location('prior_sql_gate',SUPPORT)
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
PYTHON=support.PYTHON
BINARY=Path('/private/tmp/sail-resource-validation-union-target/host/debug/sail')
BINARY_SHA='4b976fd7a809cb059c72a2119293f490105ff0ed375feaf0ccb5f3e5dad88662'


def now():return datetime.now(timezone.utc).isoformat()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--head',required=True)
    p.add_argument('--tree',required=True)
    p.add_argument('--mode',choices=['candidate','exact'],required=True)
    p.add_argument('--unit',action='store_true')
    p.add_argument('--variant',choices=['baseline','candidate'])
    p.add_argument('--sql-tests',type=Path,nargs='+',required=True)
    p.add_argument('--expected-sql',type=int,required=True)
    a=p.parse_args();a.output.mkdir(exist_ok=False)
    private=Path(tempfile.mkdtemp(prefix='certificate-witness-fixtures-'))
    receipt=dict(started_utc=now(),head=a.head,tree=a.tree,mode=a.mode,commands=[],
        outcome='failed',private_fixtures=str(private),scope='Local builtin SQL and Python certificate code only. Existing union CLI; no rebuild, remote workload, native wheel/cluster or timing verdict.')
    before=server=pins=None
    def interrupted(signum,_frame):raise InterruptedError('gate signal '+str(signum))
    for signum in (signal.SIGTERM,signal.SIGINT):signal.signal(signum,interrupted)
    env=support.client_environment(a.repo/'examples/extensions/benchmarks',a.repo)
    if a.variant:
        env['CERTIFICATE_WITNESS_VARIANT']=a.variant
    receipt['work_variant']=a.variant
    test_pins={str(path):support.sha(path) for path in a.sql_tests}
    def run(label,command,environment=env):
        record=dict(started_utc=now(),command=command);receipt['commands'].append(record)
        try:
            with (a.output/(label+'.log')).open('x') as log:
                result=subprocess.run(command,cwd=a.repo,env=environment,stdout=log,
                    stderr=subprocess.STDOUT,timeout=900)
            record['returncode']=result.returncode
            if result.returncode:raise RuntimeError(label+' failed')
        finally:
            record['finished_utc']=now()
            record['log_sha256']=support.sha(a.output/(label+'.log'))
    def counts(label):
        suites=ET.parse(a.output/(label+'.xml')).getroot().findall('testsuite')
        return {key:sum(int(s.attrib[key]) for s in suites) for key in ('tests','failures','errors','skipped')}
    try:
        assert sys.version_info[:3]==(3,12,8), 'run gate driver with pinned CPython3.12.8'
        assert shutil.disk_usage(a.repo).free>=8<<30
        before=support.source_identity(a.repo,a.head,a.tree,a.mode)
        support.save(a.output/'source-before.json',before)
        assert support.sha(BINARY)==BINARY_SHA
        pins={str(path):support.sha(path) for path in (BINARY,PYTHON.resolve(),support.PYLIB,SUPPORT,Path(__file__))}
        receipt['runtime_and_helper_pins']=pins;receipt['test_inputs']=test_pins
        run('client-before',[str(PYTHON),'-B',str(SUPPORT),'--interpreter-probe'])
        if a.unit:
            run('unit',[str(PYTHON),'-B','-m','pytest','-q','-p','no:cacheprovider',
                str(a.repo/'examples/extensions/benchmarks'),'--junitxml='+str(a.output/'unit.xml'),
                '--basetemp='+str(private/'unit')])
            receipt['unit_counts']=counts('unit')
            assert receipt['unit_counts']==dict(tests=463,failures=0,errors=0,skipped=126)
        staging=private/'graph-utils';staging.mkdir()
        server_env,settings=support.server_environment(env)
        server_env['SAIL_EXPERIMENTAL_EXTENSIONS']='1'
        settings['SAIL_EXPERIMENTAL_EXTENSIONS']='1'
        server_env['SAIL_GRAPH_UTILS_ROOT']=staging.as_uri()
        settings['SAIL_GRAPH_UTILS_ROOT']=staging.as_uri();receipt['server_settings']=settings
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        command=[str(BINARY),'spark','server','--ip','127.0.0.1','--port',str(port)]
        receipt['server_command']=command
        with (a.output/'server.log').open('x') as log:
            server=subprocess.Popen(command,cwd=private,env=server_env,stdout=log,stderr=subprocess.STDOUT)
        receipt['server_pid']=server.pid
        deadline=time.monotonic()+30
        while True:
            assert server.poll() is None,'server exited before admission'
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:
                if time.monotonic()>deadline:raise TimeoutError('server readiness')
                time.sleep(.05)
        sql_env=dict(env,SAIL_GRAPH_TEST_REMOTE=f'sc://127.0.0.1:{port}')
        run('sql',[str(PYTHON),'-B','-m','pytest','-q','-p','no:cacheprovider',*map(str,a.sql_tests),
            '--junitxml='+str(a.output/'sql.xml'),'--basetemp='+str(private/'sql')],sql_env)
        receipt['sql_counts']=counts('sql')
        assert receipt['sql_counts']==dict(tests=a.expected_sql,failures=0,errors=0,skipped=0)
        receipt['outcome']='PASS'
    except BaseException as error:
        receipt.update(error_type=type(error).__name__,error=str(error))
    finally:
        for signum in (signal.SIGTERM,signal.SIGINT):signal.signal(signum,signal.SIG_IGN)
        if server is not None:
            try:
                if server.poll() is None:server.terminate()
                else:receipt['outcome']='failed_server'
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait(timeout=10)
                receipt['server_reaped']=True;receipt['server_returncode']=server.returncode
            except BaseException as error:receipt.update(outcome='failed_cleanup',cleanup_error=str(error))
        try:
            after=support.source_identity(a.repo,a.head,a.tree,a.mode)
            support.save(a.output/'source-after.json',after)
            assert before==after
            assert pins=={path:support.sha(path) for path in pins}
            assert test_pins=={path:support.sha(path) for path in test_pins}
            run('client-after',[str(PYTHON),'-B',str(SUPPORT),'--interpreter-probe'])
            assert (a.output/'client-before.log').read_bytes()==(a.output/'client-after.log').read_bytes()
            receipt['source_runtime_unchanged']=True
        except BaseException as error:receipt.update(outcome='failed_identity',identity_error=str(error))
        receipt['finished_utc']=now()
        receipt['logs']={p.name:support.sha(p) for p in a.output.glob('*.log')}
        support.save(a.output/'receipt.json',receipt)
    (a.output/'run_sql_gate.py').write_bytes(Path(__file__).read_bytes())
    print('CERTIFICATE_SQL_GATE',receipt['outcome'],a.head,flush=True)
    return 0 if receipt['outcome']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
