"""Parse already retained03 server-log tails only; no new remote reads."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parent
STATUS=re.compile(r'worker_task_status worker_id=(\d+) job_id=(\d+) stage=(\d+) partition=(\d+) attempt=(\d+) status=([A-Z_]+)')
TIMESTAMP=re.compile(r'^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) ')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    paths=[ROOT/'observation-20260930T220458591359Z.json']+sorted(ROOT.glob('series-observation-*.json'))
    before={p.name:sha(p) for p in paths};rows=[];unique={};markers=[]
    for path in paths:
        record=json.loads(path.read_text());file=record.get('observation',{}).get('files',{}).get('server.log',{})
        statuses=[];iteration=[]
        for number,line in enumerate(file.get('tail_utf8','').splitlines(),1):
            timestamp=TIMESTAMP.match(line)
            if not timestamp:continue
            match=STATUS.search(line)
            if match:
                worker,job,stage,partition,attempt=map(int,match.groups()[:5]);status=match.group(6)
                event={'worker_id':worker,'job_id':job,'stage':stage,'partition':partition,'attempt':attempt,'status':status,'log_timestamp_utc':timestamp.group(1),'line_number_in_retained_tail':number,'line':line}
                statuses.append(event);unique[(worker,job,stage,partition,attempt,status)]=event
            if re.search(r'\biteration_(?:start|end)\b',line):
                event={'source':path.name,'line_number_in_retained_tail':number,'line':line};iteration.append(event);markers.append(event)
        success=[e for e in statuses if e['status']=='SUCCEEDED']
        max_success=max(success,key=lambda e:(e['job_id'],e['stage'],e['partition'],e['attempt'],e['worker_id'])) if success else None
        rows.append({'source':path.name,'source_sha256':before[path.name],'tail_start_byte_offset':file.get('offset'),'server_bytes_at_snapshot_start':file.get('bytes_at_start'),'retained_status_line_count':len(statuses),'max_observed_job_with_a_succeeded_task':max((x['job_id'] for x in success),default=None),'max_observed_task_identifier_lexicographically':max_success,'explicit_iteration_event_lines':iteration})
    success=[e for e in unique.values() if e['status']=='SUCCEEDED'];by_job={}
    for event in success:by_job[str(event['job_id'])]=by_job.get(str(event['job_id']),0)+1
    receipt={'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'CAPTURED_TASK_PROGRESS_ONLY','per_observation':rows,'unique_succeeded_task_status_records':len(success),'unique_succeeded_task_records_by_observed_job':by_job,'maximum_observed_job_with_a_succeeded_task':max((x['job_id'] for x in success),default=None),'maximum_job_id_in_retained_task_status_lines':max((x['job_id'] for x in unique.values()),default=None),'explicit_iteration_markers':markers,'source_sha256':sha(Path(__file__)),'limits':['Only existing retained32KiB server tails were parsed; initial startup excerpt and unretained scan-window bodies do not expand this task-status coverage. No new log read or workload operation occurred.', 'SUCCEEDED is an individual worker task status, not proof that the whole job, stage, controller iteration or algorithm completed. Numeric identifier maxima are observed identifiers, not counts of completed jobs or rounds.', 'No explicit iteration_start/end marker in these tails is an observation about this retained subset only; the controller may record iteration events elsewhere. No iteration count is inferred from job IDs.', 'Tail offsets are original snapshot byte offsets; listed line numbers are relative to retained decoded tail, not original full-log line numbers. Partial first lines are ignored.'], 'input_hashes':before}
    with (ROOT/'captured-progress.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    assert before=={p.name:sha(p) for p in paths}
    print(json.dumps({'output':str(ROOT/'captured-progress.json'),'sha256':sha(ROOT/'captured-progress.json'),'max_job_with_succeeded_task':receipt['maximum_observed_job_with_a_succeeded_task'],'iteration_markers':len(markers)}))

if __name__=='__main__':main()
