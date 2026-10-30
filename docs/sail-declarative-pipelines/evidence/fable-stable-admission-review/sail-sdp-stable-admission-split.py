from pathlib import Path
import os,subprocess,tempfile,json
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';old=json.loads(Path('/tmp/sail-sdp-stable-admission-review-candidate.json').read_text());base=old['base'];path=old['paths'][0]
def git(*args,**kwargs):return subprocess.check_output(['git','-C',repo,*args],text=True,**kwargs).strip()
s=git('show',old['commit']+':'+path)+'\n'
a=s.index('    #[test]\n    fn stable_clock_functions');b=s.index('    #[test]\n    fn immutable_projection',a)
s=s[:a]+'''    fn check_stable_clock(clock: Expr) -> TestResult {
        let f = Fixture::new()?;
        let Expr::ScalarFunction(function) = &clock else {
            panic!("clock fixture must remain a scalar function");
        };
        assert_eq!(function.func.signature().volatility, Volatility::Stable);
        let plan = f.scan(&["c", "d", "clicks"])?
            .project(vec![col("id"), clock.alias("clock")])?.build()?;
        let evidence = f.admit(&plan);
        assert!(evidence.admitted, "{evidence:?}");
        assert!(!evidence.replayable, "stable clock can change on replay: {evidence:?}");
        Ok(())
    }

    #[test]
    fn stable_now_is_not_content_replayable() -> TestResult {
        check_stable_clock(datafusion::functions::datetime::expr_fn::now())
    }

    #[test]
    fn stable_current_date_is_not_content_replayable() -> TestResult {
        check_stable_clock(datafusion::functions::datetime::expr_fn::current_date())
    }

'''+s[b:]
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);blob=git('hash-object','-w','--stdin',input=s);git('update-index','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env);commit=git('commit-tree',tree,'-p',base,'-m','Test stable date and time replay admission independently')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/evidence/stable-admission-split-review',commit)
subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
Path('/tmp/sail-sdp-stable-admission-split-candidate.json').write_text(json.dumps({'base':base,'commit':commit,'paths':[path],'scope':'Test-only split regression and immutable control'},indent=2)+'\n')
Path('/tmp/sail-sdp-stable-admission-split.patch').write_text(git('diff',base,commit)+'\n');print(commit)
