"""Independently read sixty closed C2 pairs; never submit a query or engine job."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

BASE = Path('/Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-D2-native04')
sys.path.insert(0, str(BASE / 'support'))
import probe_models as m  # noqa: E402

META = BASE / 'c2-main01'
RAW = Path('/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/c2-main01')
DEST = BASE / 'review'


@dataclass(frozen=True, slots=True)
class Pair:
    run_id: str
    partitions: int
    cold_seconds: float
    warm_seconds: float
    cold_over_warm: float
    metadata_bootstrap_seconds: float
    worker_readiness_seconds: float
    pre_data_setup_wall_seconds: float
    producer_wall_seconds: float
    child_launch_actual_wait_seconds: float
    cold_jobs: int
    warm_jobs: int
    cold_stages: int
    warm_stages: int
    cold_tasks: int
    warm_tasks: int
    scan_partitions: int
    aggregate_partitions: int
    sampled_ps_rss_sum_max_bytes: int
    sampled_resident_size_sum_max_bytes: int
    sampled_footprint_sum_max_bytes: int
    driver_ps_rss_max_bytes: int
    client_ps_rss_max_bytes: int
    worker_ps_rss_max_bytes: int
    physical_observation_errors: int
    rss_samples: int
    telemetry_rows: int
    observed_operator_memory_or_spill_values: int


def pin(path: Path) -> dict[str, object]:
    return {'path': str(path), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    location = (len(ordered) - 1) * fraction
    lower = int(location)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (location - lower)


def seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def inspect() -> None:
    queue = read(META / 'owner/receipt.json')
    supervisor = read(META / 'wait.json')
    if queue['outcome'] != 'completed_scoped_native_probe_queue' or queue['errors'] or not queue['owned_locks_released']:
        raise ValueError('campaign lifecycle is not closed')
    if supervisor['status'] != 'actual_owner_wait_passed' or not supervisor['actual_wait_completed'] or not supervisor['owner_group_absent']:
        raise ValueError('supervisor actual owner wait is not closed')
    if len(queue['calls']) != 60 or len({call['run_id'] for call in queue['calls']}) != 60:
        raise ValueError('exact sixty fresh cells required')
    expected = read(Path(read(META / 'c2-p4-01.json')['fixture']) / 'reference.json')['c2']
    pairs: list[Pair] = []
    details: list[dict[str, object]] = []
    memory_pattern = re.compile(r'\b(?:peak_mem_used|mem_used|spilled_bytes|spill_count)\s*[=:]\s*\d+')
    for call in queue['calls']:
        run = call['run_id']
        directory = RAW / run
        receipt_path = directory / 'receipt.json'
        producer = m.Receipt.model_validate_json(receipt_path.read_bytes())
        oracle = read(Path(call['oracle']['path']))
        if pin(receipt_path) != call['producer'] or pin(receipt_path) != oracle['receipt']:
            raise ValueError('producer byte identity differs')
        if any(not call[key] for key in ('wait_completed', 'child_group_absent', 'oracle_wait_completed', 'oracle_group_absent')):
            raise ValueError('a producer/oracle process is not closed')
        if call['returncode'] != 0 or call['oracle_returncode'] != 0 or call['forced_cleanup']:
            raise ValueError('a waited process did not pass cleanly')
        if oracle['outcome'] != 'passed_scoped_native_probe' or oracle['errors'] or producer.errors:
            raise ValueError('producer or answer/log oracle failed')
        if producer.inputs_before != producer.inputs_after or producer.source_before != producer.source_after:
            raise ValueError('source/input closure changed')
        if producer.full_server_phase_attribution or producer.full_physical_output_qualified:
            raise ValueError('unexpected stronger producer qualification')
        if oracle['full_server_phase_attribution'] or oracle['physical_memory_accounting_qualified']:
            raise ValueError('unexpected stronger oracle qualification')
        cold, warm = producer.actions
        if [cold.name, warm.name] != ['cold-first-data-action', 'warm-same-query-same-server']:
            raise ValueError('exact same-server pair missing')
        if any(action.raw_rows != expected or action.raw_schema != [('src', 'bigint'), ('minimum', 'bigint'), ('count', 'bigint')]
               for action in producer.actions):
            raise ValueError('independent full4096-row answer/schema comparison failed')
        if producer.worker_readiness is None or producer.session_bootstrap is None or not producer.finished_utc:
            raise ValueError('bootstrap/readiness/finish missing')
        if cold.started_utc < producer.worker_readiness.finished_utc:
            raise ValueError('cold data action preceded both worker registrations')
        if any(not proof[key] for proof in oracle['actions'] for key in ('full_answer_passed', 'exchange_in_executed_plan',
                                                                      'both_workers_observed', 'partition_count_observed')):
            raise ValueError('executed worker/exchange proof missing')
        jobs = read(directory / 'system-execution.jobs.json')
        stages = read(directory / 'system-execution.stages.json')
        tasks = read(directory / 'system-execution.tasks.json')
        per_action = []
        for proof in oracle['actions']:
            ids = set(proof['job_ids'])
            selected_jobs = [row for row in jobs if row['job_id'] in ids]
            selected_stages = [row for row in stages if row['job_id'] in ids]
            selected_tasks = [row for row in tasks if row['job_id'] in ids]
            if len(ids) != 1 or len(selected_jobs) != 1 or selected_jobs[0]['status'] != 'SUCCEEDED':
                raise ValueError('workload job did not succeed')
            if len(selected_stages) != 2 or any(row['status'] != 'SUCCEEDED' for row in selected_tasks):
                raise ValueError('workload topology/tasks differ')
            if len(selected_tasks) != proof['worker_task_attempts']:
                raise ValueError('independent system task count differs from worker log count')
            per_action.append({'jobs': selected_jobs, 'stages': selected_stages, 'tasks': len(selected_tasks)})
        scan = per_action[0]['stages'][0]['partitions']
        aggregate = per_action[0]['stages'][1]['partitions']
        if scan != min(8, producer.configuration.partitions) or aggregate != producer.configuration.partitions:
            raise ValueError('actual source/aggregation stage partitions differ')
        maxima = {'ps_sum': 0, 'resident_sum': 0, 'footprint_sum': 0, 'driver': 0, 'client': 0, 'worker': 0}
        observation_errors = 0
        for sample in producer.rss_samples:
            rss_sum = resident_sum = footprint_sum = 0
            for process in sample.processes:
                rss = process.rss_kib * 1024
                role = 'driver' if process.pid == producer.server_pid else 'client' if process.pid == producer.owner_pid else 'worker'
                maxima[role] = max(maxima[role], rss)
                rss_sum += rss
                resident_sum += process.resident_size_bytes or 0
                footprint_sum += process.physical_footprint_bytes or 0
                observation_errors += process.physical_observation_error is not None
            maxima['ps_sum'] = max(maxima['ps_sum'], rss_sum)
            maxima['resident_sum'] = max(maxima['resident_sum'], resident_sum)
            maxima['footprint_sum'] = max(maxima['footprint_sum'], footprint_sum)
        metric_rows = read(directory / 'system-telemetry.metrics.json')
        logs = [directory / 'server.log', *sorted(directory.glob('worker-*.log'))]
        operator_values = sum(len(memory_pattern.findall(path.read_text())) for path in logs)
        if cold.seconds is None or warm.seconds is None:
            raise ValueError('pair clocks missing')
        pairs.append(Pair(run, producer.configuration.partitions, cold.seconds, warm.seconds, cold.seconds / warm.seconds,
                          producer.session_bootstrap.seconds, producer.worker_readiness.seconds,
                          seconds(producer.started_utc, cold.started_utc), seconds(producer.started_utc, producer.finished_utc),
                          call['launch_to_wait_seconds'], len(per_action[0]['jobs']), len(per_action[1]['jobs']),
                          len(per_action[0]['stages']), len(per_action[1]['stages']), per_action[0]['tasks'],
                          per_action[1]['tasks'], scan, aggregate, maxima['ps_sum'], maxima['resident_sum'],
                          maxima['footprint_sum'], maxima['driver'], maxima['client'], maxima['worker'],
                          observation_errors, len(producer.rss_samples), len(metric_rows), operator_values))
        details.append({'run_id': run, 'producer': pin(receipt_path), 'oracle': pin(Path(call['oracle']['path'])),
                        'actual_actions': per_action, 'metadata_query_scope': 'snapshot after workload, includes its own jobs',
                        'telemetry_names': sorted({row['name'] for row in metric_rows}), 'retained_logs': [pin(p) for p in logs],
                        'stronger_qualification': {'full_server_phase_attribution': False, 'physical_memory_accounting_qualified': False}})
    grouped = []
    numeric = ['cold_seconds', 'warm_seconds', 'cold_over_warm', 'metadata_bootstrap_seconds', 'worker_readiness_seconds',
               'pre_data_setup_wall_seconds', 'producer_wall_seconds', 'child_launch_actual_wait_seconds',
               'sampled_ps_rss_sum_max_bytes', 'sampled_resident_size_sum_max_bytes', 'sampled_footprint_sum_max_bytes']
    for partitions in (4, 16, 32):
        selected = [asdict(pair) for pair in pairs if pair.partitions == partitions]
        if len(selected) != 20:
            raise ValueError('twenty fresh pairs per P required')
        grouped.append({'partitions': partitions, 'fresh_servers': len(selected),
                        'quantiles': {name: {'p50': quantile([row[name] for row in selected], .5),
                                             'p95': quantile([row[name] for row in selected], .95)} for name in numeric},
                        'jobs_per_action': 1, 'stages_per_action': 2,
                        'worker_tasks_per_action': min(8, partitions) + partitions,
                        'sample_physical_observation_errors': sum(row['physical_observation_errors'] for row in selected),
                        'telemetry_rows': sum(row['telemetry_rows'] for row in selected),
                        'observed_operator_memory_or_spill_values': sum(row['observed_operator_memory_or_spill_values'] for row in selected)})
    result = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'status': 'independent_sixty_pair_scoped_review_passed',
              'source': '9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3', 'groups': grouped, 'pairs': [asdict(row) for row in pairs],
              'details': details, 'queue_pin': pin(META / 'owner/receipt.json'), 'supervisor_pin': pin(META / 'wait.json'),
              'quantile_definition': 'linear interpolation at (n-1)*q, matching NumPy default',
              'full_server_phase_attribution': False, 'physical_memory_accounting_qualified': False,
              'publication_scope': 'shared-host descriptive ratios; absolute clocks in private evidence CSV only'}
    (DEST / 'review.json').write_text(json.dumps(result, indent=2) + '\n')
    with (DEST / 'private-clocks.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(pairs[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in pairs)
    with (DEST / 'private-quantiles.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['partitions', 'fresh_servers', 'metric', 'p50', 'p95'])
        for group in grouped:
            for metric, values in group['quantiles'].items():
                writer.writerow([group['partitions'], group['fresh_servers'], metric, values['p50'], values['p95']])
    print(json.dumps({'status': result['status'], 'groups': grouped}, indent=2))


if __name__ == '__main__':
    inspect()
