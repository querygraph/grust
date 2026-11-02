from pathlib import Path
import hashlib,json,subprocess
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';label='bounded-resolved-clocks';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-'+label+'-gate.json').read_text());out=Path('/tmp/sail-sdp-bounded-components-public-09d2f0cb8')
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('rev-parse','HEAD')==c['base'];assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==c['commit'];assert not subprocess.check_output(['git','-C',gate,'status','--porcelain']);assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and hashlib.sha256(Path(check['log']).read_bytes()).hexdigest()==check['sha256']
for path in c['paths']:assert git('rev-parse',c['commit']+':'+path)==git('rev-parse','56ae39abd:'+path)
assert set(git('diff','--name-only',c['base'],c['commit']).splitlines())==set(c['paths'])
log=Path('/tmp/sail-sdp-'+label+'-rust.log').read_text()
for count in [134,55,135]:assert f'test result: ok. {count} passed; 0 failed;' in log
for name in ['a_resolved_sail_current_timestamp_is_not_content_replayable','a_resolved_sail_now_is_not_content_replayable','a_resolved_sail_current_date_is_not_content_replayable','a_resolved_immutable_projection_remains_content_replayable']:assert name+' ... ok' in log
public=json.loads((out/'receipt.json').read_text());assert public['sail_commit']==c['commit'] and public['outcome']=='passed';assert public['before']==public['after'];assert public['before']['head']==c['commit'] and public['before']['detached']
assert public['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0};assert public['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'};assert public['server_exit_code']==0 and public['remaining_listener_pids']==[]
for name,digest in public['artifact_sha256'].items():assert hashlib.sha256((out/name).read_bytes()).hexdigest()==digest,name
assert hashlib.sha256(Path(public['cli_path']).read_bytes()).hexdigest()==public['cli_sha256']
assert 'Co-Authored-By: Claude Fable' in git('show','-s','--format=%B',c['commit'])
print('PASS actual resolved clocks/324 libraries/exact source/fresh300+67 CLI/version/owned server stopped; full original SDP suite unqualified')
