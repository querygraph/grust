from pathlib import Path
from datetime import datetime,timezone
import subprocess,tempfile,os,json,hashlib
root='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';base='ebf631edd3b41b288a2c4d899a7a82dd658582e1';path='crates/sail-spark-connect/src/pipelines/streaming/binding.rs';packet=Path('/tmp/sail-sdp-fable-binding-expression-review');packet.mkdir(exist_ok=False)
def git(*args,**kw):return subprocess.check_output(['git','-C',root,*args],**kw)
original=git('show',base+':'+path).decode();assert original.endswith('}\n')
extra='''
    #[test]
    fn codex_review_unbound_scalar_subquery_must_be_refused_before_resolution() {
        let plan = spec::QueryPlan::new(spec::QueryNode::Project {
            input: None,
            expressions: vec![spec::Expr::ScalarSubquery {
                subquery: Box::new(read("missing", false)),
            }],
        });
        let result = validate(plan, &[], &[]);
        assert!(matches!(result, Err(BindingError::UnboundCatalogRead(_))), "unbound scalar subquery passed: {result:?}");
    }
    #[test]
    fn codex_review_unbound_exists_predicate_must_be_refused_before_resolution() {
        let plan = spec::QueryPlan::new(spec::QueryNode::Filter {
            input: Box::new(read("clicks", true)),
            condition: spec::Expr::Exists {
                subquery: Box::new(read("missing", false)),
                negated: false,
            },
        });
        let result = validate(plan, &[source(&["c", "d", "clicks"])], &[]);
        assert!(matches!(result, Err(BindingError::UnboundCatalogRead(_))), "unbound predicate subquery passed: {result:?}");
    }
'''
content=original[:-2]+extra+'}\n';(packet/'test-source.rs').write_text(content)
fd,index=tempfile.mkstemp(prefix='sdp-binding-review-index-');os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);blob=git('hash-object','-w','--stdin',input=content.encode()).decode().strip();git('update-index','--add','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env).decode().strip();commit=git('commit-tree',tree,'-p',base,'-m','test: expose expression subquery holes in bounded read validation').decode().strip()
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/reviews/fable-binding-expression',commit);subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
command=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','codex_review_unbound_','--','--nocapture']
r={'base':base,'commit':commit,'source_path':path,'command':command,'started_at':datetime.now(timezone.utc).isoformat(),'scope':'Independent pre-resolution validation counterexamples; no actual provider/RPC execution claim'}
(packet/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':root+'/.venv/bin/python','VIRTUAL_ENV':root+'/.venv','PYTHONPATH':root+'/.venv/lib/python3.12/site-packages'}
with (packet/'test.log').open('x')as out:result=subprocess.run(command,cwd=gate,env=env,stdout=out,stderr=subprocess.STDOUT)
r.update(exit_code=result.returncode,finished_at=datetime.now(timezone.utc).isoformat(),log_sha256=hashlib.sha256((packet/'test.log').read_bytes()).hexdigest());(packet/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
assert result.returncode==101 and '0 passed; 2 failed;'in(packet/'test.log').read_text(),packet/'test.log'
assert 'unbound scalar subquery passed: Ok'in(packet/'test.log').read_text() and 'unbound predicate subquery passed: Ok'in(packet/'test.log').read_text()
print('CONFIRMED two unchanged-source counterexamples '+commit,flush=True)
