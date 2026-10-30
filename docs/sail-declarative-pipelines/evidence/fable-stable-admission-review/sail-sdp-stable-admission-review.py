from pathlib import Path
import os,subprocess,tempfile,json
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate'
base='d77fc47958641933e84577bfa88e3be5cfbd9471';path='crates/sail-spark-connect/src/pipelines/streaming/admission.rs'
def git(*args,**kwargs):return subprocess.check_output(['git','-C',repo,*args],text=True,**kwargs).strip()
s=git('show',base+':'+path)+'\n'
needle='    #[test]\n    fn a_volatile_expression_is_admitted_but_not_replayable()'
assert s.count(needle)==1
fixture='''    #[test]
    fn stable_clock_functions_are_not_content_replayable() -> TestResult {
        let f = Fixture::new()?;
        for clock in [
            datafusion::functions::datetime::expr_fn::now(),
            datafusion::functions::datetime::expr_fn::current_date(),
        ] {
            let Expr::ScalarFunction(function) = &clock else {
                panic!("clock fixture must remain a scalar function");
            };
            assert_eq!(function.func.signature().volatility, Volatility::Stable);
            let plan = f.scan(&["c", "d", "clicks"])?
                .project(vec![col("id"), clock.alias("clock")])?.build()?;
            let evidence = f.admit(&plan);
            assert!(evidence.admitted, "{evidence:?}");
            assert!(!evidence.replayable, "stable clock can change on replay: {evidence:?}");
        }
        Ok(())
    }

    #[test]
    fn immutable_projection_remains_content_replayable() -> TestResult {
        let f = Fixture::new()?;
        let plan = f.scan(&["c", "d", "clicks"])?
            .project(vec![(col("id") + lit(1_i64)).alias("next")])?.build()?;
        let evidence = f.admit(&plan);
        assert!(evidence.admitted, "{evidence:?}");
        assert!(evidence.replayable, "{evidence:?}");
        Ok(())
    }

'''
s=s.replace(needle,fixture+needle)
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index)
env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env)
 blob=git('hash-object','-w','--stdin',input=s)
 git('update-index','--cacheinfo','100644',blob,path,env=env)
 tree=git('write-tree',env=env)
 commit=git('commit-tree',tree,'-p',base,'-m','Test stable-clock admission replayability without production changes')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/evidence/stable-admission-review',commit)
subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
Path('/tmp/sail-sdp-stable-admission-review-candidate.json').write_text(json.dumps({'base':base,'commit':commit,'paths':[path],'scope':'Tests only; no production changes'},indent=2)+'\n')
Path('/tmp/sail-sdp-stable-admission-review.patch').write_text(git('diff',base,commit)+'\n')
print(commit)
