from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess
root=Path('/Users/alexy/src/sail-pipelines-proposal');gate=Path('/Users/alexy/src/sail-sdp-gate')
python=str(root/'.venv/bin/python')
final=json.loads(Path('/tmp/sail-sdp-owned-store-qualified-errors-candidate.json').read_text())
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':python,'VIRTUAL_ENV':str(root/'.venv'),'PYTHONPATH':str(root/'.venv/lib/python3.12/site-packages')}
for name,filename,pattern,expected,count in [
 ('owned-store-final-bypass','owned_store.rs','checkpoint_loss_retains_completion_and_sibling_isolation','owner completed before held multipart completion',2),
 ('owned-store-condition-control','owned_store_error.rs','conditional_provider_errors_keep_their_variants_and_typed_source','provider condition variant lost:',1),
]:
 p=root/'crates/sail-execution/src'/filename;original=p.read_text()
 if filename=='owned_store.rs':
  a=original.index('    async fn put_multipart_opts(');b=original.index('    async fn get_opts(',a)
  changed=original[:a]+'''    async fn put_multipart_opts(
        &self, location: &Path, opts: PutMultipartOptions,
    ) -> object_store::Result<Box<dyn MultipartUpload>> {
        self.inner.put_multipart_opts(location, opts).await
    }

'''+original[b:]
 else:
  a=original.index('pub(super) fn store_error(')
  changed=original[:a]+'''pub(super) fn store_error(error: DataFusionError) -> object_store::Error {
    object_store::Error::Generic { store: "OwnedObjectStore", source: Box::new(error) }
}
'''
 try:
  p.write_text(changed)
  subprocess.run([python,'/tmp/sail-sdp-make-candidate.py',name,'test: retain unchanged ownership and condition counterexamples',*final['paths']],cwd=root,check=True)
 finally:p.write_text(original)
 c=json.loads(Path('/tmp/sail-sdp-'+name+'-candidate.json').read_text())
 command=['cargo','+1.98.1','test','-p','sail-execution','--lib','--locked',pattern,'--','--nocapture']
 log=Path('/tmp/sail-sdp-'+name+'.log');started=datetime.now(timezone.utc).isoformat()
 with log.open('w') as output:r=subprocess.run(command,cwd=gate,env=env,stdout=output,stderr=subprocess.STDOUT)
 Path('/tmp/sail-sdp-'+name+'-receipt.json').write_text(json.dumps({'commit':c['commit'],'fixed_commit':final['commit'],'command':command,'exit_code':r.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
 text=log.read_text();assert r.returncode==101 and text.count(expected)==count and f'0 passed; {count} failed;' in text,text[-12000:]
 subprocess.run(['git','-C',str(root),'update-ref','refs/sdp/controls/'+name,c['commit']],check=True)
 print('PASS expected negative control '+name+' '+c['commit'],flush=True)
subprocess.run(['git','-C',str(gate),'checkout','--detach',final['commit']],check=True)
assert not subprocess.check_output(['git','-C',str(gate),'status','--porcelain'])
print('Restored exact fixed candidate '+final['commit'],flush=True)
