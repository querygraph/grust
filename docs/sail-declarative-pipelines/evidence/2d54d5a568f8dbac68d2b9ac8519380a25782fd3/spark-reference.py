import json, os
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
spark=SparkSession.builder.master('local[1]').appName('USE golden semantics').config('spark.ui.enabled','false').getOrCreate()
result={'spark_version':spark.version,'cases':[]}
try:
    parser=spark._jsparkSession.sessionState().sqlParser()
    for sql in ['USE https://www.spa.rk/bucket/pa-th.json?=&#%','USE test-test','USE Ɩpfel','USE 表1','USE `Ɩpfel`','USE `表1`']:
        case={'sql':sql}
        try:
            plan=parser.parsePlan(sql)
            case.update(outcome='parsed',plan=plan.toString(),kind=plan.getClass().getSimpleName())
        except Exception as error:
            case.update(outcome='rejected',exception_type=type(error).__name__,message=str(error))
        result['cases'].append(case)
finally:spark.stop()
Path('/tmp/sail-sdp-use-gold-reference.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))
