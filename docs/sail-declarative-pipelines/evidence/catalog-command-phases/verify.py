from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
SOURCE='/Users/alexy/src/spark-sdp-4.2.1'
def load(path):return json.loads((HERE/path).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
m=load('SHA256.json');assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in m.items():assert digest(HERE/path)==sha,path
source=load('spark-source.json');assert source['commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
for path,sha in source['files'].items():assert hashlib.sha256(subprocess.check_output(['git','-C',SOURCE,'show',source['commit']+':'+path])).hexdigest()==sha
spark=load('spark/observations.json');sail=load('sail/probe/observations.json')
for r in [spark,sail]:
 assert r['spark_version']=='4.2.1' and r['spark_source_commit']==source['commit'] and len(r['cases'])==32
 assert r['harness_sha256']==digest(HERE/'reference.py')
 assert r['listener_after_stop']=={'exit_code':1,'stdout':''}
 assert all(c['session_namespace']==r['session_namespace'] for c in r['cases'])
 assert r['installed_client_jars']==spark['installed_client_jars'] and len(r['installed_client_jars'])>=3
receipt=load('sail/receipt.json');public=json.loads((HERE.parent/'constant-name-policy/public/receipt.json').read_text())
assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==public['sail_commit']=='f0a232af259fa2bf33c089d5439ffb45fa78061e'
assert receipt['before']['cli_sha256']==public['cli_sha256'] and receipt['before']['probe_sha256']==digest(HERE/'reference.py')
assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
for file in receipt['files']:assert digest(HERE/'sail'/file['path'])==file['sha256']
rows={c['name']:c for c in spark['cases']}
def has(name,condition):assert '['+condition+']' in rows[name].get('error',''),name
assert rows['public_bare_current_catalog']['returned']
for name in ['public_wrapped_current_catalog','directive_bare_current_catalog','directive_wrapped_current_catalog']:has(name,'NOT_A_CONSTANT_STRING.NOT_CONSTANT')
for name in ['public_bare_typeof_rand','directive_bare_typeof_rand']:has(name,'INVALID_NON_DETERMINISTIC_EXPRESSIONS')
has('public_wrapped_typeof_rand','CATALOG_NOT_FOUND');assert rows['directive_wrapped_typeof_rand']['returned']
has('public_bare_division','DIVIDE_BY_ZERO');has('directive_bare_division','NOT_A_CONSTANT_STRING.WRONG_TYPE')
has('directive_bare_generator','UNSUPPORTED_GENERATOR.OUTSIDE_SELECT')
assert rows['directive_bare_typeof_current']['returned']
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True));assert comparison==load('comparison.json')
assert (comparison['behavior_matched'],comparison['metadata_matched'])==(13,2)
print('PASS 32-case Spark/Sail baseline; three phases confirmed; 13 behavior matches/19 mismatches,2 metadata sets; source/CLI/artifact pins and teardown verified')
