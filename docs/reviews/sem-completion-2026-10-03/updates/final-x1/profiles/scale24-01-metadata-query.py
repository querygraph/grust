import json,os;from pathlib import Path;from datetime import datetime,timezone;from pyspark.sql.connect.session import SparkSession;from pyspark.sql.connect.client.retries import DefaultPolicy
r=Path('/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x1-scale24-01-live-metadata01');s=None;v={'observed_utc':datetime.now(timezone.utc).isoformat(),'outcome':'running','original_native_session':'96ed20ae-5330-486d-a59b-e7f0ab8195d7','job_id':38,'query_boundary':'fresh metadata session outside original algorithm; no graph inputs or writes','queries':[],'errors':[],'session_closed':False}
try:
 s=SparkSession.builder.remote('sc://192.168.4.61:50151').create();s.client.set_retry_policies([DefaultPolicy(max_retries=0)]);v['metadata_session']=s.client._session_id;assert v['metadata_session']!=v['original_native_session']
 for sql in ["SELECT stage,partitions,inputs,`group`,mode,distribution,placement,status,created_at,stopped_at FROM system.execution.stages WHERE session_id='96ed20ae-5330-486d-a59b-e7f0ab8195d7' AND job_id=38 ORDER BY stage", "SELECT stage,status,COUNT(*) AS tasks,MIN(partition) AS first_partition,MAX(partition) AS last_partition,MIN(created_at) AS earliest_created,MAX(stopped_at) AS latest_stopped FROM system.execution.tasks WHERE session_id='96ed20ae-5330-486d-a59b-e7f0ab8195d7' AND job_id=38 GROUP BY stage,status ORDER BY stage,status", "SELECT worker_id,host,port,status,created_at,stopped_at FROM system.cluster.workers WHERE session_id='96ed20ae-5330-486d-a59b-e7f0ab8195d7' ORDER BY worker_id"]:
  rows=s.sql(sql).collect();v['queries'].append({'sql':sql,'rows':[x.asDict(recursive=True) for x in rows]});(r/'observations.json').write_text(json.dumps(v,indent=2,default=str)+'\n')
 v['outcome']='completed_metadata_queries_only'
except BaseException as e:
 v['outcome']='metadata_query_error';v['errors'].append(repr(e));raise
finally:
 if s is not None:s.stop();v['session_closed']=True
 (r/'observations.json').write_text(json.dumps(v,indent=2,default=str)+'\n')