from pathlib import Path
import shutil, json, hashlib, subprocess
P=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/numeric-divisor-guard')
P.mkdir(exist_ok=False)
def copy(src,dst):
 s=Path(src);d=P/dst
 if s.is_dir():shutil.copytree(s,d)
 else:d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(s,d)
for name in ['candidate.json','gate.json','fmt.log','clippy.log','rust.log','controls.py','runtime.py','compare.py','comparison.json','duplicate-control.json','duplicate-control.log','codec-control.json','codec-control.log','stage-probe.py','stage-probe.json','stage-probe.log']:
 copy('/tmp/sail-sdp-numeric-divisor-'+name,'native/'+name)
for name in ['public','schema','runtime','domain','phases','arithmetic','provenance','attempt-01']:
 copy('/tmp/sail-sdp-numeric-divisor-'+name,name)
for name in ['py','json','log']:copy('/tmp/sail-sdp-operand-stage-probe.'+name,'stage-before/probe.'+name)
copy('/tmp/sail-sdp-operand-stage-snippet.rs','stage-before/snippet.rs')
copy('/tmp/sail-sdp-numeric-divisor-collect.py','collect.py')
root='/Users/alexy/src/sail-pipelines-proposal';commit=json.loads((P/'native/candidate.json').read_text())['commit']
(P/'source.patch').write_bytes(subprocess.check_output(['git','-C',root,'diff',commit+'^',commit]))
registry=Path('/Users/alexy/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f')
paths=['datafusion-physical-expr-55.2.0/src/expressions/case.rs','datafusion-physical-expr-55.2.0/src/scalar_function.rs','datafusion-expr-55.2.0/src/udf.rs']
(P/'dependency-source.json').write_text(json.dumps({'sail_commit':commit,'cargo_lock_blob':subprocess.check_output(['git','-C',root,'rev-parse',commit+':Cargo.lock'],text=True).strip(),'files':[{'path':p,'sha256':hashlib.sha256((registry/p).read_bytes()).hexdigest()} for p in paths]},indent=2)+'\n')
print(P)
for name in ['additional-reference.py','additional-reference-v2.py','additional.py','additional-comparison.json','parent-probe.py','parent-build.json','parent-build.log','additional-spark.log','additional-spark-02.log']:
 copy('/tmp/sail-sdp-numeric-divisor-'+name,name)
for name in ['additional-spark','additional-sail','additional-spark-02','additional-sail-02','additional-parent']:
 copy('/tmp/sail-sdp-numeric-divisor-'+name,name)
