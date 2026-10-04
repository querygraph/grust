#!/usr/bin/env python3
"""Audit collected production min_by control, without running graph workloads."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib
import tarfile

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'wcc-fused-representatives289-cpu16-23'
REPO = Path('/Users/alexy/src/sail-large-graphs')
RUNTIME = '2894a962076d3cc404dd72ec736ebeb9239901f6'
REVIEW = 'b569e75de625885b3d919fa4196b2e0bed14c618'
sha = lambda data: hashlib.sha256(data).hexdigest()
read = lambda path: json.loads(path.read_text())
git = lambda *args: subprocess.check_output(['git', '-C', str(REPO), *args])


def main():
    collection = read(RUN / 'collection.json')
    for path, expected in collection['sha256'].items():
        assert sha((RUN / path).read_bytes()) == expected, path
    config = read(RUN / 'configuration.json')
    original_config = read(ROOT / 'configuration.json')
    assert config == original_config
    receipt = read(RUN / 'cell/diagnostics/receipt.json')
    result = read(RUN / 'result.json')
    orchestration = read(RUN / 'cell/orchestration.json')
    assert receipt['outcome'] == result['outcome'] == 'passed'
    assert receipt['configuration'] == config
    assert receipt['source_and_binary_unchanged'] and not receipt['cleanup_errors']
    assert not orchestration['transport_errors'] and not orchestration['outer_timeout']
    assert orchestration['attach_returncode'] == 0
    state = orchestration['inspect']['state']
    assert state['ExitCode'] == 0 and not state['OOMKilled'] and not state['Running']
    case_rows = []
    expression = 'last_value(#3) FILTER (WHERE #4 IS NOT NULL) ORDER BY [#4 DESC NULLS FIRST] as min_by(#3,#4)'
    for case in receipt['cases']:
        edges = case['edges']
        vertices = {v for edge in edges for v in edge}
        expected = {v:min({v} | {b for a,b in edges if a == v} | {a for a,b in edges if b == v}) for v in vertices}
        assert len(edges) == 14 and len(vertices) == 17
        assert len(case['actual']) == 17 and len(dict(case['actual'])) == 17
        assert dict(case['actual']) == dict(case['expected']) == expected
        assert case['outcome'] == 'passed'
        fields = case['schema']['fields']
        assert [field['name'] for field in fields] == ['id', 'representative']
        assert all(field['type'] == 'long' for field in fields)
        plan_path = RUN / ('cell/diagnostics/' + case['name'] + '-plan.txt')
        assert sha(plan_path.read_bytes()) == case['plan_sha256']
        plan = plan_path.read_text()
        assert plan.count(expression) == 2
        assert 'mode=Partial' in plan and 'mode=FinalPartitioned' in plan
        assert case['process_identity']['child_worker_pids'] == [61, 62]
        assert all(p['executable_sha256'] == config['binary_sha256'] for p in case['process_identity']['processes'])
        case_rows.append({'name':case['name'],'rows':17,'schema':case['schema'],'exact_oracle_pass':True,'plan_sha256':case['plan_sha256']})
    assert [case['name'] for case in receipt['cases']] == ['forward-input','reversed-input']

    lines = (RUN / 'cell/diagnostics/server.log').read_text().splitlines()
    plan_re = re.compile(r'\] job (\d+) stage (\d+) partition (\d+) attempt (\d+) execution plan$')
    status_re = re.compile(r'worker_task_status worker_id=(\d+) job_id=(\d+) stage=(\d+) partition=(\d+) attempt=(\d+) status=(\w+)')
    statuses = defaultdict(list)
    for number, line in enumerate(lines, 1):
        match = status_re.search(line)
        if match:
            worker, job, stage, partition, attempt, status = match.groups()
            statuses[tuple(map(int,(job,stage,partition,attempt)))].append((int(worker),status,number))
    assignments = []
    for index, line in enumerate(lines):
        match = plan_re.search(line)
        if not match:
            continue
        block = []
        for following in lines[index+1:]:
            if following.startswith('['):
                break
            block.append(following)
        aggregates = [(offset, row) for offset, row in enumerate(block, index+2) if expression in row]
        if not aggregates:
            continue
        assert len(aggregates) == 1
        aggregate_line, aggregate = aggregates[0]
        key = tuple(map(int, match.groups()))
        matches = statuses[key]
        success = [(worker,number) for worker,status,number in matches if status == 'SUCCEEDED']
        running = [(worker,number) for worker,status,number in matches if status == 'RUNNING']
        assert len(success) == len(running) == 1 and success[0][0] == running[0][0], key
        assert all(status in ('RUNNING','SUCCEEDED') for _,status,_ in matches), key
        mode = re.search(r'mode=(\w+)',aggregate).group(1)
        assignments.append({'job':key[0],'stage':key[1],'partition':key[2],'attempt':key[3],
                            'worker':success[0][0],'mode':mode,'plan_header_line':index+1,
                            'aggregate_line':aggregate_line,'running_line':running[0][1],
                            'succeeded_line':success[0][1]})
    counts = Counter((a['job'],a['mode'],a['worker']) for a in assignments)
    assert len(assignments) == 24
    for job in (2,3):
        for worker in (1,2):
            assert counts[job,'Partial',worker] == 4
            assert counts[job,'FinalPartitioned',worker] == 2

    bridge = []
    for path in ('Cargo.lock','crates/sail-function/src/aggregate/max_min_by.rs'):
        first, second = (git('show', ref+':'+path) for ref in (RUNTIME,REVIEW))
        assert first == second
        bridge.append({'path':path,'runtime_sha':RUNTIME,'review_sha':REVIEW,'byte_identical':True,'sha256':sha(first)})
    prior = ROOT.parent / 'min-by-probe'
    prior_source = read(prior / 'source-receipt.json')
    wrapper = git('show', RUNTIME+':crates/sail-function/src/aggregate/max_min_by.rs')
    assert sha(wrapper) == prior_source['upstream_sha256']['sail-max_min_by.rs']
    assert wrapper == (prior/'upstream/sail-max_min_by.rs').read_bytes()
    sail_lock = tomllib.loads(git('show',RUNTIME+':Cargo.lock').decode())
    probe_lock = tomllib.loads((prior/'Cargo.lock').read_text())
    dependencies = []
    for name in ('datafusion-functions-aggregate','datafusion-functions-aggregate-common','arrow-array','arrow-data'):
        sail = next(p for p in sail_lock['package'] if p['name']==name)
        probe = next(p for p in probe_lock['package'] if p['name']==name)
        fields = ('name','version','source','checksum')
        assert {k:sail[k] for k in fields} == {k:probe[k] for k in fields}
        dependencies.append({k:sail[k] for k in fields})
    registry = list((Path.home()/'.cargo/registry/src').glob('*/datafusion-functions-aggregate-55.1.0'))
    assert len(registry)==1
    archive = list((Path.home()/'.cargo/registry/cache').glob('*/datafusion-functions-aggregate-55.1.0.crate'))
    assert len(archive)==1
    df = next(p for p in dependencies if p['name']=='datafusion-functions-aggregate')
    assert sha(archive[0].read_bytes()) == df['checksum']
    first_last = (prior/'upstream/first_last.rs').read_bytes()
    assert first_last == (registry[0]/'src/first_last.rs').read_bytes()
    assert sha(first_last) == prior_source['upstream_sha256']['first_last.rs']
    with tarfile.open(archive[0], 'r:gz') as tar:
        assert tar.extractfile('datafusion-functions-aggregate-55.1.0/src/first_last.rs').read() == first_last
    build = read(ROOT.parent/'linux-builds/integration289/final/rebuild-receipt.json')
    assert build['outcome'] == 'passed' and build['source_sha'] == RUNTIME
    assert build['host']['sha256'] == config['binary_sha256']
    output = {
        'recorded_utc':datetime.now(timezone.utc).isoformat(),'outcome':'PASS_ACTUAL_CONTROL_AUDIT',
        'collected_files_verified':len(collection['sha256']), 'collection_sha256':sha((RUN/'collection.json').read_bytes()),
        'binary_sha256':config['binary_sha256'],'runtime_source_sha':RUNTIME,
        'controller_source_sha':config['harness_source_sha'],'native_source_sha':config['native_source_sha'],
        'cases':case_rows,'worker_aggregate_assignments':assignments,
        'counts':[{'job':j,'mode':m,'worker':w,'tasks':c} for (j,m,w),c in sorted(counts.items())],
        'source_bridge':bridge,'shared_dependency_identity':dependencies,
        'first_last_source_sha256':sha(first_last),
        'all_rows_and_schema_exact':True,'both_workers_succeeded_partial_and_final_aggregate_tasks':True,
        'script_sha256':sha(Path(__file__).read_bytes()),
        'limits':['Correlates explicit full job/stage/partition/attempt task keys, not merged-log adjacency or process presence alone',
                  'Does not map each returned case name to job ID directly: receipt lacks job IDs; sequential call order is supporting context only',
                  'Worker task logs establish ordered LAST_VALUE physical route; grouped Int64 specialization follows the pinned source and typed input contract',
                  'Prior standalone System-allocator measurements remain component evidence; no whole-query RSS or allocation measurement was added',
                  'No evidence that EmitTo::First ran in this control or a WCC iteration',
                  'Only one-step representatives on 17 active vertices, not full WCC convergence, certificate, scalability, speed or OOM diagnosis',
                  'Runtime build provenance relies on retained289 build receipt; audit did not rebuild or launch workloads']}
    (ROOT/'actual-control-audit.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({'outcome':output['outcome'],'aggregate_tasks':len(assignments),'counts':output['counts'],
                      'receipt_sha256':sha((ROOT/'actual-control-audit.json').read_bytes())}))


if __name__ == '__main__':
    main()
