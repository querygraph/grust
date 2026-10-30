from pathlib import Path
from datetime import datetime,timezone
import subprocess,tempfile,os,json,hashlib
root='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';base='9dc1b1157dd31d584a6c7eaf99770c778d344e6b';path='crates/sail-spark-connect/src/pipelines/streaming/lower_tests.rs';p=Path('/tmp/sail-sdp-fable-local-source-review');p.mkdir(exist_ok=False)
def git(*args,**kw):return subprocess.check_output(['git','-C',root,*args],**kw)
original=git('show',base+':'+path).decode()
extra='''
async fn codex_local_streaming_case(placeholder: bool) -> TestResult {
    let ctx = SessionContext::new();
    let scope = TaskResourceScope::new(Handle::current());
    let (_source, mut binding) = bind_clicks(100)?;
    binding.name = name(&["c", "d", "events"]);
    let graph = graph();
    let selected_flow = flow(read("events", true), &[]);
    let installed = if placeholder { placeholder_relations()? } else { relations()? };
    let lowered = lower(&ctx, Arc::new(PlanConfig::default()), &scope, &Inputs {
        graph: &graph, flow: &selected_flow, relations: &installed,
        sources: std::slice::from_ref(&binding), statics: &[], locals: &[],
    }).await?;
    assert_eq!(ids(&ctx, lowered.plan).await?, vec![0, 1, 2, 10, 11]);
    Ok(())
}
#[tokio::test]
async fn codex_lower_local_stream_ignores_analysis_placeholder() -> TestResult {
    codex_local_streaming_case(true).await
}
#[tokio::test]
async fn codex_lower_local_stream_ignores_materialised_graph_relation() -> TestResult {
    codex_local_streaming_case(false).await
}
#[tokio::test]
async fn codex_lower_snapshot_distinguishes_declared_local_versions() -> TestResult {
    let ctx = SessionContext::new();
    let (_source, binding) = bind_clicks(100)?;
    let (installed, mut local) = materialised_events()?;
    let graph = graph();
    let selected_flow = flow(join(read("clicks", true), read("events", false)), &[]);
    let mut snapshots = vec![];
    for version in ["version:1", "version:2"] {
        let scope = TaskResourceScope::new(Handle::current());
        local.identity = version.into();
        let lowered = lower(&ctx, Arc::new(PlanConfig::default()), &scope, &Inputs {
            graph: &graph, flow: &selected_flow, relations: &installed,
            sources: std::slice::from_ref(&binding), statics: &[], locals: std::slice::from_ref(&local),
        }).await?;
        snapshots.push(serde_json::to_value(lowered.snapshot)?);
    }
    assert_ne!(snapshots[0], snapshots[1], "different declared local versions have the same lowering snapshot");
    Ok(())
}
'''
content=original+extra;(p/'test-source.rs').write_text(content)
fd,index=tempfile.mkstemp(prefix='sdp-local-source-index-');os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);blob=git('hash-object','-w','--stdin',input=content.encode()).decode().strip();git('update-index','--add','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env).decode().strip();commit=git('commit-tree',tree,'-p',base,'-m','test: expose local streaming binding and snapshot gaps').decode().strip()
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/reviews/fable-local-streaming-source',commit);subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
cmd=['cargo','+1.98.1','test','-p','sail-spark-connect','--lib','--locked','codex_lower_','--','--nocapture'];r={'base':base,'commit':commit,'source_path':path,'command':cmd,'started_at':datetime.now(timezone.utc).isoformat(),'scope':'Independent lowerer counterexamples; two range-binding cases and one declared-identity snapshot case, no backend pin qualification'};(p/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
env={**os.environ,'CARGO_INCREMENTAL':'0','CARGO_PROFILE_DEV_DEBUG':'0','PYO3_PYTHON':root+'/.venv/bin/python','VIRTUAL_ENV':root+'/.venv','PYTHONPATH':root+'/.venv/lib/python3.12/site-packages'}
with (p/'test.log').open('x')as out:result=subprocess.run(cmd,cwd=gate,env=env,stdout=out,stderr=subprocess.STDOUT)
r.update(exit_code=result.returncode,finished_at=datetime.now(timezone.utc).isoformat(),log_sha256=hashlib.sha256((p/'test.log').read_bytes()).hexdigest());(p/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
assert result.returncode==101 and '0 passed; 3 failed;'in(p/'test.log').read_text(),p/'test.log'
assert 'different declared local versions have the same lowering snapshot'in(p/'test.log').read_text()
print('CONFIRMED three unchanged lowerer counterexamples '+commit,flush=True)
