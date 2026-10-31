from pathlib import Path
import json,hashlib,re,subprocess
R='/Users/alexy/src/sail-pipelines-proposal';G='/Users/alexy/src/sail-sdp-gate';c=json.load(open('/tmp/sail-sdp-decimal-config-candidate.json'));r=json.load(open('/tmp/sail-sdp-decimal-config-gate.json'));assert r['outcome']=='passed' and r['sail_commit']==c['commit']
for x in r['checks']:assert x['exit_code']==0 and hashlib.sha256(Path(x['log']).read_bytes()).hexdigest()==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;',Path('/tmp/sail-sdp-decimal-config-rust.log').read_text())==['117','183']
for name in ['capture','set-validation','java-trim','hierarchy']:
 r=json.load(open('/tmp/sail-sdp-decimal-config-'+name+'-control.json'));log=Path('/tmp/sail-sdp-decimal-config-'+name+'-control.log');assert r['base']==c['commit'] and r['exit_code']==101 and '0 passed; 1 failed;' in log.read_text() and hashlib.sha256(log.read_bytes()).hexdigest()==r['log_sha256']
p=json.load(open('/tmp/sail-sdp-decimal-config-public-regression/receipt.json'));assert p['sail_commit']==c['commit'] and p['outcome']=='passed' and not p['remaining_listener_pids'] and p['upstream']['tests_run']==67 and p['upstream']['failures']==p['upstream']['errors']==p['upstream']['skipped']==0
v=json.load(open('/tmp/sail-sdp-decimal-config-public/observations.json'));assert v['sail_commit']==c['commit'] and len(v['cases'])==12 and not v['remaining_listener_pids'] and v['cli_sha256']==p['cli_sha256']
s=json.load(open('/tmp/sail-sdp-decimal-config-spark/observations.json'))
assert v['default']==s['default']=='false' and v['after_unset']==s['after_unset']=='false'
for o,a in zip(s['cases'],v['cases']):assert all(a.get(k)==val for k,val in o.items()) and a['query_rows']==[[1]]
assert subprocess.check_output(['git','-C',G,'rev-parse','HEAD'],text=True).strip()==c['commit'] and not subprocess.check_output(['git','-C',G,'status','--porcelain'],text=True).strip()
assert hashlib.sha256(Path(G+'/target/debug/sail').read_bytes()).hexdigest()==p['cli_sha256']
print('PASS config300 native/fmt/strictClippy/four unchanged0/1 controls/public300+67/config12 exact reference matches')
