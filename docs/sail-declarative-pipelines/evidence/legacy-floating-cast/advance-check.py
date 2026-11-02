from pathlib import Path
import hashlib,json,subprocess
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate'
c=json.loads(Path('/tmp/sail-sdp-legacy-floating-cast-candidate.json').read_text());r=json.loads(Path('/tmp/sail-sdp-legacy-floating-cast-gate.json').read_text())
assert r['sail_commit']==c['commit'] and r['outcome']=='passed'
for x in r['checks']:
 assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert 'test result: ok. 117 passed; 0 failed;' in Path('/tmp/sail-sdp-legacy-floating-cast-rust.log').read_text()
control=json.loads(Path('/tmp/sail-sdp-legacy-floating-cast-control.json').read_text());assert control['base']==c['commit'] and control['exit_code']==101
assert '0 passed; 3 failed;' in Path('/tmp/sail-sdp-legacy-floating-cast-control.log').read_text()
assert hashlib.sha256(Path('/tmp/sail-sdp-legacy-floating-cast-control.log').read_bytes()).hexdigest()==control['log_sha256']
pub=json.loads(Path('/tmp/sail-sdp-legacy-floating-cast-public-regression/receipt.json').read_text());assert pub['sail_commit']==c['commit'] and pub['outcome']=='passed' and not pub['remaining_listener_pids']
assert pub['upstream']['tests_run']==67 and pub['upstream']['failures']==pub['upstream']['errors']==pub['upstream']['skipped']==0
floating=json.loads(Path('/tmp/sail-sdp-legacy-floating-cast-public-02/observations.json').read_text());assert floating['sail_commit']==c['commit'] and len(floating['cases'])==136 and not floating['remaining_listener_pids']
# Require the malformed legacy and unchanged ANSI/TRY_CAST cases at the actual RPC boundary.
for x in floating['cases']:
 if x['source'] in [None,'bad','','1.5','NaN','nan','Inf','-Infinity','1e1000','1e-1000','+Infinity','1_0','null']:
  assert x['behavior_match'],x
assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==c['commit']
assert not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
assert hashlib.sha256(Path(G+'/target/debug/sail').read_bytes()).hexdigest()==pub['cli_sha256']==floating['cli_sha256']
print('PASS candidate117/fmt/strictClippy/unchanged0-of3 control/public300+67 plus required floating RPC comparisons')
