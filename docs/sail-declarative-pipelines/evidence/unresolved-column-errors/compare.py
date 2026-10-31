"""Compare frozen inputs and record exact ordinary error metadata and SDP outcomes."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE = Path(__file__).resolve().parent
FINAL = '7b5667c1fef901c5f6768fd5af222beeed453f15'
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def checked_run(folder, probe):
    root = HERE/folder
    receipt = json.loads((root/'receipt.json').read_text())
    assert receipt['before'] == receipt['after']
    assert receipt['before']['sail_commit'] == FINAL
    assert receipt['before']['probe_sha256'] == digest(HERE/probe)
    assert receipt['server_exit_code'] == receipt['probe_exit_code'] == 0
    assert receipt['remaining_listener_pids'] == []
    for entry in receipt['files']:
        assert digest(root/entry['path']) == entry['sha256']
    return json.loads((root/'probe/observations.json').read_text())
reference = json.loads((HERE/'spark-ordinary/observations.json').read_text())
actual = checked_run('sail-ordinary','reference.py')
assert reference['spark_version'] == reference['pyspark_version'] == actual['spark_version'] == actual['pyspark_version'] == '4.2.1'
assert reference['harness_sha256'] == actual['harness_sha256'] == digest(HERE/'reference.py')
assert len(reference['cases']) == len(actual['cases']) == 12
ordinary=[]
for expected, result in zip(reference['cases'],actual['cases']):
    keys=['name','sql','case_sensitive','outcome']
    if expected['outcome']=='error':keys+=['exception_type','condition','sql_state','parameters']
    else: keys+=['rows']
    assert {k:expected[k] for k in keys} == {k:result[k] for k in keys},(expected['name'],expected,result)
    ordinary.append({'name':result['name'],'matched':True,'condition':result.get('condition'),'parameters':result.get('parameters')})
reference = json.loads((HERE.parent/'flow-config-fusion-reference/spark/observations.json').read_text())
actual = checked_run('sail-config','config-reference.py')
assert digest(HERE/'config-reference.py') == digest(HERE.parent/'flow-config-fusion-reference/reference.py')
assert reference['spark_version'] == actual['spark_version'] == '4.2.1'
assert len(reference['cases']) == len(actual['cases']) == 13
config=[]
def conditions(case):
    text = case.get('run_error','')+'\n'+'\n'.join(e['message'] for e in case['events'])
    return sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',text)))
for expected, result in zip(reference['cases'],actual['cases']):
    keys=['name','definitions','query','consumer_conf','run_returned','result_exists','session_case_sensitive']
    assert {k:expected[k] for k in keys} == {k:result[k] for k in keys},result['name']
    assert expected.get('rows') == result.get('rows'),result['name']
    assert conditions(expected) == conditions(result),result['name']
    if conditions(expected)==['UNRESOLVED_COLUMN.WITH_SUGGESTION']:
        message='\n'.join(e['message'] for e in expected['events'])
        first=re.search(r'Error: (\[UNRESOLVED_COLUMN.WITH_SUGGESTION\].*?) SQLSTATE:',message)
        assert first is not None
        assert result['run_error'] == first.group(1), (result['name'], result['run_error'],first.group(1))
    config.append({'name':result['name'],'matched':True,'conditions':conditions(result)})
print(json.dumps({'sail_commit':FINAL,'scope':'ordinary SQL: exact condition/state/parameters plus success rows; SDP: conditions/rows plus five missing-column first-line messages; not full duplicate-flow parameter/provenance or original Scala acceptance','ordinary_matched':12,'ordinary_mismatched':0,'config_matched':13,'config_mismatched':0,'ordinary':ordinary,'config':config},indent=2,ensure_ascii=False))
