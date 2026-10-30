from pathlib import Path
import hashlib,json,subprocess
python='/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python';gate='/Users/alexy/src/sail-sdp-gate';label='resolver-query-session-registry';c=json.loads(Path('/tmp/sail-sdp-'+label+'-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-resolver-helper-session-bypass-receipt.json').read_text());log=Path(r['log']).read_bytes()
assert r['fixed_commit']==c['commit'] and r['exit_code']==101 and hashlib.sha256(log).hexdigest()==r['sha256']
assert b'1 passed; 4 failed;'in log and log.count(b'session extension not found: task resource scope')==4
assert subprocess.check_output(['git','-C',gate,'rev-parse','HEAD'],text=True).strip()==r['commit']
print('PASS retained unchanged bypass control; corrected expected extension name in qualifier only',flush=True)
subprocess.run(['git','-C',gate,'checkout','--detach',c['commit']],check=True)
subprocess.run([python,'/tmp/sail-sdp-package-release-stress.py',label,'','sail-plan'],check=True)
subprocess.run([python,'/tmp/sail-sdp-local-runner-public-harness/run.py','--commit',c['commit'],'--output','/tmp/sail-sdp-resolver-query-session-public'],check=True)
