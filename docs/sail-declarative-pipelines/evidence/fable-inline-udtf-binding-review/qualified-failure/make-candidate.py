from pathlib import Path
import os,subprocess,tempfile,json
repo='/Users/alexy/src/sail-pipelines-proposal';gate='/Users/alexy/src/sail-sdp-gate';path='crates/sail-spark-connect/src/pipelines/streaming/binding_tests.rs'
def git(*a,**kw):return subprocess.check_output(['git','-C',repo,*a],text=True,**kw).strip()
base=git('rev-parse','HEAD');s=git('show',base+':'+path)+'\n'
fixture='''
fn inline_table_function(return_type: Option<spec::DataType>) -> spec::QueryPlan {
    spec::QueryPlan::new(spec::QueryNode::CommonInlineUserDefinedTableFunction(
        spec::CommonInlineUserDefinedTableFunction {
            function_name: "probe".into(),
            deterministic: true,
            arguments: vec![],
            function: spec::TableFunctionDefinition::PythonUdtf {
                return_type,
                eval_type: spec::PySparkUdfType::Table,
                command: vec![],
                python_version: "3.12".into(),
            },
        },
    ))
}

#[test]
fn dynamic_inline_table_function_is_refused_before_resolution() {
    let result = validate(inline_table_function(None), &[], &[]);
    assert!(matches!(result, Err(BindingError::UnsupportedRead(_))),
        "dynamic schema invokes Python analyze during resolution: {result:?}");
}

#[test]
fn static_inline_table_function_keeps_binding_classification() {
    let result = validate(inline_table_function(Some(spec::DataType::Struct { fields: spec::Fields::default() })), &[], &[]);
    assert!(result.is_ok(), "static schema does not invoke dynamic analyze: {result:?}");
}
'''
s+=fixture
fd,index=tempfile.mkstemp();os.close(fd);os.unlink(index);env={**os.environ,'GIT_INDEX_FILE':index}
try:
 git('read-tree',base,env=env);blob=git('hash-object','-w','--stdin',input=s);git('update-index','--cacheinfo','100644',blob,path,env=env);tree=git('write-tree',env=env);commit=git('commit-tree',tree,'-p',base,'-m','Test dynamic inline UDTF guard before bounded resolution')
finally:Path(index).unlink(missing_ok=True)
git('update-ref','refs/sdp/evidence/dynamic-udtf-binding-review-fields',commit)
subprocess.run(['git','-C',gate,'checkout','--detach',commit],check=True)
Path('/tmp/sail-sdp-dynamic-udtf-binding-review-fields-candidate.json').write_text(json.dumps({'base':base,'commit':commit,'paths':[path],'scope':'test-only; empty command bytes never deserialized'},indent=2)+'\n');Path('/tmp/sail-sdp-dynamic-udtf-binding-review-fields.patch').write_text(git('diff',base,commit)+'\n');print(commit)
