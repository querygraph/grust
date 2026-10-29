"""Source capture and offline validation; never starts Spark or changes fixtures."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
SPARK=Path('/Users/alexy/src/spark-sdp-4.2.1')
PIN='617618396087429b5627a86ce933bb0f5d6645cb'

def sha(data): return hashlib.sha256(data).hexdigest()
def save(name,value): (ROOT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def git(*args): return subprocess.check_output(['git','-C',str(SPARK),*args])

anchors=[
 ('orc-utils','sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcUtils.scala',[(135,178),(226,310)]),
 ('orc-file-format','sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcFileFormat.scala',[(115,175),(175,245)]),
 ('orc-type-cast-errors','sql/catalyst/src/main/scala/org/apache/spark/sql/errors/QueryExecutionErrors.scala',[(2527,2545)]),
 ('orc-atomic-vector','sql/core/src/main/java/org/apache/spark/sql/execution/datasources/orc/OrcAtomicColumnVector.java',[(85,120)]),
 ('datetime-conversion','sql/api/src/main/scala/org/apache/spark/sql/catalyst/util/SparkDateTimeUtils.scala',[(100,110),(360,390)]),
]
sources=[]
for label,path,ranges in anchors:
 raw=git('show',f'{PIN}:{path}')
 lines=raw.splitlines(keepends=True)
 entry={'path':path,'commit':PIN,'git_blob':git('rev-parse',f'{PIN}:{path}').decode().strip(),'source_sha256':sha(raw),'excerpts':[]}
 for first,last in ranges:
  assert 1<=first<=last<=len(lines),(path,first,last,len(lines))
  excerpt=b''.join(lines[first-1:last])
  target=Path('sources')/f'{label}-{first}-{last}.txt'
  (ROOT/target).parent.mkdir(exist_ok=True)
  (ROOT/target).write_bytes(excerpt)
  entry['excerpts'].append({'first_line':first,'last_line':last,'file':str(target),'sha256':sha(excerpt)})
 sources.append(entry)
save('source-audit.json',{'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'repository':str(SPARK),'commit':PIN,'sources':sources})

r=json.loads((ROOT/'results.json').read_text())
first=json.loads((ROOT/'attempt-01-unsupported-write-mode/results.json').read_text())
assert r['status']=='completed' and r['owned_gateway_exit_code']==0
assert first['status']=='failed' and first['owned_gateway_exit_code']==0 and not first['cases']
assert 'errorifexists is not supported' in first['failure']
assert len(r['cases'])==24
assert sha((ROOT/'probe.py').read_bytes())==r['script_sha256']
assert sha((ROOT/'attempt-01-unsupported-write-mode/probe.py').read_bytes())==first['script_sha256']
fixture=ROOT/'data/mixed_timestamps'/Path(r['fixture']['path']).name
assert sha(fixture.read_bytes())==r['fixture']['sha256']
expected_scalar={'ltz':1577934245123456,'ntz':1623053350654321}
expected={'ltz':[expected_scalar['ltz'],None],'ntz':[expected_scalar['ntz'],None],
 'st':[expected_scalar,None],
 'la':[[expected_scalar['ltz'],None],None], 'na':[[expected_scalar['ntz'],None],None],
 'lm':[[['null',None],['value',expected_scalar['ltz']]],None],
 'nm':[[['null',None],['value',expected_scalar['ntz']]],None]}
# Validate exact integer arithmetic independently, avoiding a floating-point oracle.
for name,dt in [('ltz',datetime(2020,1,2,3,4,5,123456)),('ntz',datetime(2021,6,7,8,9,10,654321))]:
 delta=dt-datetime(1970,1,1)
 assert expected_scalar[name]==(delta.days*86400+delta.seconds)*1000000+delta.microseconds
successes={'exact_schema','exact_schema_project_only_second_ntz','missing_ltz_appended','missing_ntz_appended'}
rows=[]
for case in r['cases']:
 name=case['name']
 assert case['stage']=='materialize_to_arrow'
 assert case['actual_vectorized_config']==str(case['vectorized']).lower()
 assert case['nested_vectorized_config']=='true'
 if name in successes:
  assert case['status']=='success'
  observed={c['name']:c['values'] for c in case['arrow']['columns']}
  wanted={'ntz':expected['ntz']} if name=='exact_schema_project_only_second_ntz' else dict(expected)
  if name=='missing_ltz_appended': wanted['absent_ltz']=[None,None]
  if name=='missing_ntz_appended': wanted['absent_ntz']=[None,None]
  assert observed==wanted,(name,observed)
  assert case['arrow']['num_rows']==2
  classification='success'
 else:
  assert case['status']=='error'
  error=case['error']
  if name in ['array_swaps','map_swaps']:
   assert error['condition'] is None
   assert 'ArithmeticException: long overflow' in error['message']
   assert 'UNSUPPORTED_FEATURE.ORC_TYPE_CAST' not in error['message']
   classification='later_timestamp_conversion_overflow'
  else:
   assert error['condition']=='FAILED_READ_FILE.NO_HINT'
   assert 'UNSUPPORTED_FEATURE.ORC_TYPE_CAST' in error['message']
   classification='dedicated_positional_orc_timestamp_compatibility_error'
 rows.append({'name':name,'vectorized':case['vectorized'],'classification':classification,'stage':case['stage'],'condition':case.get('error',{}).get('condition')})
for name in {c['name'] for c in rows}:
 pair=[c for c in rows if c['name']==name]
 assert pair[0]['classification']==pair[1]['classification']
summary={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'source_pin':PIN,'scope':'Observed Spark reference, no Sail runtime qualification or production policy decision',
 'cases_total':24,'successful_reads':8,'dedicated_compatibility_errors':12,'later_conversion_overflows':4,
 'harness_attempts':2,'first_attempt_failure':'Connect rejects errorifexists write mode before any read cases; exact artifacts preserved',
 'owned_gateway_exit_codes':[first['owned_gateway_exit_code'],r['owned_gateway_exit_code']],
 'owned_gateway_pids':[first['java']['gateway_pid'],r['java']['gateway_pid']],
 'exact_success_values_validated':True,'fixture':{'file':str(fixture.relative_to(ROOT)),'sha256':sha(fixture.read_bytes())},
 'cases':rows}
save('summary.json',summary)
files=[];excluded=[]
for p in sorted(ROOT.rglob('*')):
 if not p.is_file() or p.name=='MANIFEST.json': continue
 rel=p.relative_to(ROOT)
 if p.suffix=='.crc' or p.name=='_SUCCESS' or rel.parts[0] in ['spark-local','warehouse']:
  excluded.append({'file':str(rel),'reason':'Generated Hadoop bookkeeping or Spark runtime state; not used as evidence','sha256':sha(p.read_bytes()),'size':p.stat().st_size})
 else:
  files.append({'file':str(rel),'sha256':sha(p.read_bytes()),'size':p.stat().st_size})
save('MANIFEST.json',{'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'original_root':str(ROOT),'portable_mapping':'Every file key is relative to this manifest; original absolute paths in raw receipts are preserved',
 'files':files,'excluded':excluded,'excluded_directory_rules':['spark-local/**','warehouse/**'],'unchanged_fixture_sha256':r['fixture']['sha256']})
print('Validated 24 observed cases, 8 exact successful value sets, 2 owned JVM cleanup receipts;',len(files),'retained files')
