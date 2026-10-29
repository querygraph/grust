from datetime import datetime,timezone
import json,os
from pathlib import Path
for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
from pyspark.sql import SparkSession
spark=SparkSession.builder.master('local[1]').appName('catalog expression design').config('spark.ui.enabled','false').getOrCreate()
expressions=["1 / 0", "1 DIV 0", "1 % 0", "CAST(1 / 0 AS STRING)"]
result={'recorded_at':datetime.now(timezone.utc).isoformat(),'spark_version':spark.version,'spark_commit':'617618396087429b5627a86ce933bb0f5d6645cb','scope':'SQL parser plus Analyzer execute/checkAnalysis and SetCatalogCommand.getCatalogName; no command execution or catalog mutation','cases':[]}
try:
    state=spark._jsparkSession.sessionState()
    for expression in expressions:
        case={'expression':expression}
        try:
            parsed=state.sqlParser().parsePlan('SET CATALOG '+expression)
            analyzed=state.analyzer().execute(parsed)
            state.analyzer().checkAnalysis(analyzed)
            case.update(outcome='resolved',catalog=analyzed.getCatalogName(),plan=analyzed.toString())
        except Exception as error:
            case.update(outcome='rejected',exception_type=type(error).__name__,message=str(error))
            try:case['condition']=error.getCondition()
            except Exception:
                try:case['condition']=error.java_exception.getCondition()
                except Exception:pass
        result['cases'].append(case)
finally:spark.stop()
Path('/tmp/sail-sdp-catalog-division-reference.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
assert result['spark_version']=='4.2.1'
print(json.dumps([{'expression':c['expression'],'outcome':c['outcome'],'catalog':c.get('catalog'),'condition':c.get('condition')} for c in result['cases']],indent=2,ensure_ascii=False))
