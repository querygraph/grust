from pathlib import Path
import subprocess,textwrap,json,hashlib
root=Path('/Users/alexy/src/sail-pipelines-proposal')
source='71e4a94d910c7afa978eaf1cc98beccb5df92051'
destination=root/'crates/sail-common/src/utils'
def blob(name):
 return subprocess.check_output(['git','-C',str(root),'show',f'{source}:crates/sail-common/src/utils/{name}']).decode()
original=blob('root_lowercase.rs')
production,tests=original.split('#[cfg(test)]\nmod tests {\n',1)
assert tests.endswith('}\n')
tests=textwrap.dedent(tests[:-2])
old='''    let text = std::fs::read_to_string(&path).unwrap_or_default();
    let Ok(corpus) = serde_json::from_str::<Corpus>(&text) else {
        eprintln!("could not parse {path}");
        return;
    };'''
new='''    #[expect(clippy::expect_used)]
    let text = std::fs::read_to_string(&path).expect("the supplied JVM corpus should be readable");
    #[expect(clippy::expect_used)]
    let corpus = serde_json::from_str::<Corpus>(&text)
        .expect("the supplied JVM corpus should contain valid cases");'''
assert old in tests
tests=tests.replace(old,new)
(destination/'root_lowercase.rs').write_text(production+'#[cfg(test)]\n#[path = "root_lowercase_tests.rs"]\nmod tests;\n')
(destination/'root_lowercase_tests.rs').write_text(tests)
for name in ['root_lowercase_tables.rs','root_lowercase_oracle.json']:
 (destination/name).write_text(blob(name))
p=destination/'mod.rs';s=p.read_text();assert 'root_lowercase' not in s;p.write_text(s.replace('pub mod retry;','pub mod retry;\npub mod root_lowercase;'))
packet=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/fable-c2-corrected-review/lowercase')
cases=json.loads((packet/'cases.json').read_text())
print('cases shape:',type(cases).__name__)
print('first case:',str(cases[0])[:150])
print('first JVM output:',(packet/'java.stdout').read_text().splitlines()[0][:150])
