from pathlib import Path
import json
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence')
ns={'__file__':str(p/'deferred-arithmetic/compare.py')}
s=(p/'deferred-arithmetic/compare.py').read_text();exec(s[:s.index("spark=load(HERE/")],ns)
result={}
for packet,label,oracle in [('deferred-arithmetic','schema','spark-schema'),('deferred-arithmetic','runtime','runtime-spark'),('deferred-arithmetic','domain','domain-spark'),('wrapped-catalog-identifier','phases','spark'),('constant-context-lowering','arithmetic','spark'),('identifier-function-provenance','provenance','spark')]:
 a=json.loads((p/packet/oracle/'observations.json').read_text());b=json.loads(Path('/tmp/sail-sdp-numeric-divisor-'+label+'/probe/observations.json').read_text())
 result[label]=ns['schemas'](ns['compare'](a,b,True),a,b)
 result[label]['total']=len(a['cases'])
Path('/tmp/sail-sdp-numeric-divisor-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
for label,v in result.items():print(label, {k:v[k] for k in ['total','behavior_matched','metadata_matched','wire_matched','schema_matched']})
