from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib, json, os, signal, subprocess, sys, time, traceback
import xml.etree.ElementTree as ET
phase=sys.argv[1]
assert phase in ('baseline','candidate')
root=Path('/Users/alexy/src/sail-sdp-gate')
implementation=Path('/Users/alexy/src/sail-pipelines-proposal')
py=str(implementation/'.venv/bin/python')
name='python/pysail/tests/spark/pipelines/test_flow_file_config.py'
out=Path('/tmp/sail-sdp-flow-config-'+phase)
out.mkdir(exist_ok=phase=='baseline')
sha=(json.loads(Path('/tmp/sail-sdp-flow-config-candidate.json').read_text())['commit'] if phase=='candidate' else '71f24a87a2f2b5b38bd012388e3ce6589c7c6d46')
r={'commit':sha,'phase':phase,'started':datetime.now(timezone.utc).isoformat(),'checks':[]}
process=None
hashfile=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def state():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==sha
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
def owners():
    p=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:50092','-sTCP:LISTEN','-Fp'],capture_output=True,text=True)
    assert p.returncode in (0,1)
    return {int(x[1:]) for x in p.stdout.splitlines() if x.startswith('p')}
def run(name,command,env,expected=0):
    with (out/(name+'.log')).open('x') as log:
        p=subprocess.run(command,cwd=root,env={**os.environ,**env},stdout=log,stderr=subprocess.STDOUT)
    r['checks'].append({'name':name,'command':command,'exit_code':p.returncode,'sha256':hashfile(out/(name+'.log'))})
    state()
    assert p.returncode==expected,(name,p.returncode)
    print('PASS '+phase+' '+name,flush=True)
try:
    state()
    if phase=='candidate':
        gate=json.loads(Path('/tmp/sail-sdp-flow-config-gate.json').read_text())
        assert gate['outcome']=='passed' and gate['sail_commit']==sha
        run('build',['cargo','+1.98.1','build','-p','sail-cli','--locked'],{'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false','PYO3_PYTHON':py,'PYTHONPATH':str(implementation/'.venv/lib/python3.12/site-packages'),'VIRTUAL_ENV':str(implementation/'.venv')})
    cli=root/'target/debug/sail'
    r['cli_sha256']=hashfile(cli)
    if phase=='baseline': assert r['cli_sha256']==json.loads((out/'build.json').read_text())['cli_sha256']
    test=(root if phase=='candidate' else implementation)/name
    r['test_file']=str(test);r['test_sha256']=hashfile(test)
    assert not owners()
    with (out/'server.log').open('x') as log:
        process=subprocess.Popen([str(cli),'spark','server','--port','50092'],cwd=root,env={**os.environ,'PYTHONPATH':str(implementation/'.venv/lib/python3.12/site-packages'),'VIRTUAL_ENV':str(implementation/'.venv')},stdout=log,stderr=subprocess.STDOUT)
        r['server_pid']=process.pid
        deadline=time.monotonic()+30
        while not owners():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.25)
        assert owners()=={process.pid}
        env={'PYTHONPATH':'python','SPARK_REMOTE':'sc://localhost:50092','PYTHONDONTWRITEBYTECODE':'1'}
        run('version',[py,'-c',"from pyspark.sql import SparkSession; s=SparkSession.builder.remote('sc://localhost:50092').create(); assert s.version=='4.2.1',s.version; print(s.version); s.stop()"],env)
        if phase=='baseline': nodes=[str(test)]
        else:
            nodes=json.loads(Path('/tmp/sail-sdp-orc-public/selected-nodes.json').read_text())+[
                'python/pysail/tests/spark/dml/test_write_table.py::test_ctas_collect_returns_empty_result_after_writing',
                'python/pysail/tests/spark/pipelines/test_nested_materialization.py',name]
        (out/'selected-nodes.json').write_text(json.dumps(nodes,indent=2)+'\n')
        run('pytest',[py,'-m','pytest','-q',*nodes,'--junitxml='+str(out/'pytest.xml')],env,expected=1 if phase=='baseline' else 0)
        suite=ET.parse(out/'pytest.xml').getroot().find('testsuite')
        r['pytest']={k:int(suite.get(k)) for k in ['tests','failures','errors','skipped']}
        if phase=='baseline':
            assert r['pytest']['tests']==4 and r['pytest']['failures']>0 and r['pytest']['errors']==r['pytest']['skipped']==0
        else:
            assert r['pytest']==dict(tests=304,failures=0,errors=0,skipped=0),r['pytest']
            run('upstream',[py,'scripts/spark-pipelines-tests/run.py','--spark-source','/Users/alexy/src/spark-sdp-4.2.1','--remote','sc://localhost:50092','--report',str(out/'upstream.json')],env)
            u=json.loads((out/'upstream.json').read_text())
            assert u['tests_run']==67 and u['failures']==u['errors']==u['skipped']==0 and u['server_spark_version']=='4.2.1'
        assert hashfile(cli)==r['cli_sha256'] and hashfile(test)==r['test_sha256'] and owners()=={process.pid}
    r['outcome']='expected baseline regression' if phase=='baseline' else 'passed'
except BaseException:
    r['outcome']='failed';r['error']=traceback.format_exc();raise
finally:
    if process:
        if process.poll() is None:process.send_signal(signal.SIGINT)
        try:process.wait(timeout=30)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
        r['server_exit']=process.returncode;r['remaining_owners']=list(owners())
    r['finished']=datetime.now(timezone.utc).isoformat()
    (out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
