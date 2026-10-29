from pathlib import Path
import os,subprocess,sys,json
label=sys.argv[1];root=Path('/Users/alexy/src/orc-rust-sdp-gate');c=json.loads(Path('/tmp/orc-sdp-'+label+'-candidate.json').read_text());env={**os.environ,'CARGO_PROFILE_DEV_DEBUG':'0','CARGO_PROFILE_DEV_INCREMENTAL':'false'}
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
commands=[('fmt',['cargo','+1.98.1','fmt','--all','--','--check']),('clippy',['cargo','+1.98.1','clippy','--workspace','--all-targets','--all-features','--','-D','warnings']),('tests',['cargo','+1.98.1','test','--locked']),('no-default',['cargo','+1.98.1','test','--lib','--no-default-features','--locked'])]
for kind,command in commands:
 with Path('/tmp/orc-sdp-'+label+'-'+kind+'.log').open('w') as out:subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
 assert git('rev-parse','HEAD')==c['commit'] and not git('status','--porcelain')
 print('PASS '+label+' '+kind,flush=True)
