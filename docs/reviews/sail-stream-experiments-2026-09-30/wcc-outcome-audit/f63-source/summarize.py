#!/usr/bin/env python3
"""Export every matrix outcome and summarize only correctly completed trials."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from statistics import median

from run_matrix import configuration_fingerprint, plan_cells
from validation_outcome import effective_outcome


GROUP = ('suite', 'dataset', 'mode', 'algorithm', 'engine', 'variant')
METRICS = ('seconds', 'execution_rss_bytes', 'execution_pss_bytes',
           'cgroup_peak_through_result_bytes', 'cgroup_lifetime_peak_bytes',
           'native_pool_peak_bytes', 'native_read_peak_bytes', 'iterations',
           'true_residual', 'whole_vm_steal_fraction')


def number(value):
    return None if value is None else float(value)


def cell_row(cell, summary, receipt):
    row = {k: cell[k] for k in ('cell_id', 'sequence', 'repeat', *GROUP, 'expected_outcome')}
    outcome = summary['outcome'] if summary else ('incomplete_record' if receipt else 'not_run')
    row.update(outcome=outcome, original_outcome=outcome,
               original_expected_outcome=summary.get('expected_outcome') if summary else None,
               receipt_outcome=receipt.get('outcome') if receipt else None,
               integrity_errors=[], expected_outcome_observed=outcome == cell['expected_outcome'])
    row.update({key: None for key in METRICS})
    if not receipt:
        return row
    peaks = receipt.get('memory', {}).get('phase_peaks', {}).get('execute', {})
    correctness = receipt.get('correctness', {})
    status = receipt.get('native_status_after', receipt.get('native_status_on_error', {})) or {}
    reads = [r for r in status.get('reads', []) if r['algorithm'] == receipt.get('kernel')]
    native = reads[0] if len(reads) == 1 else {}
    diagnostics = native.get('diagnostics') or {}
    events = receipt.get('iteration_events', [])
    row.update(
        kernel=receipt.get('kernel'),
        seconds=receipt.get('end_to_end_seconds'),
        elapsed_until_error_seconds=receipt.get('elapsed_until_error_seconds'),
        execution_rss_bytes=peaks.get('rss_bytes'), execution_pss_bytes=peaks.get('pss_bytes'),
        execution_sampled=receipt.get('memory', {}).get('execution_sampled'),
        cgroup_peak_through_result_bytes=number(receipt.get('cgroup_execution_after', {}).get('memory.peak')),
        cgroup_lifetime_peak_bytes=number(receipt.get('cgroup_after', {}).get('memory.peak')),
        native_pool_peak_bytes=status.get('memory', {}).get('peak_bytes'),
        native_read_peak_bytes=native.get('peak_bytes'),
        iterations=receipt.get('algorithm_iterations', diagnostics.get('iterations', correctness.get('max_iterations'))),
        true_residual=correctness.get('true_fixed_point_residual'),
        whole_vm_steal_fraction=receipt.get('guest_steal_fraction'),
        frontier_messages=diagnostics.get('frontier_edges'),
        contraction_rounds=(len(diagnostics.get('rounds', [])) if receipt.get('kernel') in
                            ('wccRandomized', 'wccRandomizedFused') else None),
        native_source_sha=receipt.get('native_source_sha'),
        runtime_source_sha=receipt.get('runtime_source_sha'),
        harness_source_sha=receipt.get('harness_source_sha'),
        binary_sha256=receipt.get('binary_sha256'),
        verification_policy=correctness.get('policy'),
        verification_scope=correctness.get('verification_scope'),
        component_count_verified=correctness.get('component_count_verified'),
    )
    frontier = [e['active_edges'] for e in events if e['kind'] == 'iteration_end' and 'active_edges' in e]
    contraction = [e for e in events if e['kind'] == 'iteration_end' and 'edges_after' in e]
    if frontier:
        row['frontier_messages'] = sum(frontier)
    if contraction:
        row['contraction_rounds'] = len(contraction)
    return row


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def sha256_value(value):
    return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) is not None


def integrity_errors(cell, summary, receipt, config):
    """Check an apparent pass against its planned cell, not just its label."""
    errors = []
    if summary.get('configuration_sha256') != configuration_fingerprint(config):
        errors.append('configuration fingerprint differs')
    suite = next((s for s in config['suites'] if s['name'] == cell['suite']), {})
    overrides = suite.get('expected_outcomes', {}).get(cell['variant'], {})
    legacy_partial_default = (cell['expected_outcome'] == 'partially_verified' and
                              summary.get('expected_outcome') == 'passed' and
                              cell['engine'] not in overrides and receipt is not None and
                              receipt.get('outcome') == 'passed' and
                              effective_outcome(receipt) == 'partially_verified')
    for key, value in cell.items():
        if key == 'expected_outcome' and legacy_partial_default:
            continue
        if summary.get(key) != value:
            errors.append(f'summary cell field differs: {key}')
    if not receipt:
        return errors + ['passed summary has no valid receipt']
    if receipt.get('outcome') != 'passed':
        errors.append('passed summary disagrees with receipt outcome')
    for key in ('harness_source_sha', 'runtime_source_sha', 'native_source_sha'):
        if receipt.get(key) != config[key]:
            errors.append(f'source differs: {key}')
    if receipt.get('source_dirty') != '':
        errors.append('source is dirty or cleanliness is unrecorded')
    arguments = receipt.get('arguments') or {}
    expected = {key: cell[key] for key in ('engine', 'algorithm', 'variant', 'mode', 'repeat', 'max_iterations')}
    expected.update({key: config['defaults'][key] for key in
                     ('partitions', 'threads', 'worker_task_slots', 'sail_pool_bytes',
                      'native_quota', 'tolerance', 'damping', 'timeout', 'seed')})
    if cell['algorithm'] in ('bfs', 'sssp'):
        dataset_options = config['datasets'][cell['dataset']]
        expected.update(source=dataset_options.get('source', 0), directed=dataset_options.get('directed', True),
                        delta=config['defaults'].get('delta', 1.0))
    root = PurePosixPath(config['container_root'])
    expected.update(dataset=str(root / 'datasets' / cell['dataset']),
                    output=str(root / 'cells' / cell['cell_id']),
                    sail_binary=config['container_sail_binary'],
                    runtime_source_sha=config['runtime_source_sha'],
                    native_source_sha=config['native_source_sha'],
                    allow_dirty=False, allow_unisolated=False)
    for key, value in expected.items():
        if arguments.get(key) != value:
            errors.append(f'receipt argument differs: {key}')
    worker_count = 2 if cell['mode'] == 'process-cluster' else 0
    slots, pool, quota = (config['defaults'][key] for key in
                          ('worker_task_slots', 'sail_pool_bytes', 'native_quota'))
    admission = dict(worker_task_slots_per_worker=slots, worker_task_slots_total=worker_count * slots,
                     sail_pool_per_process_bytes=pool, prepaid_native_quota_bytes=quota,
                     remaining_participating_df_budget_bytes=pool - quota)
    for key, value in admission.items():
        if receipt.get(key) != value:
            errors.append(f'admission receipt differs: {key}')
    memory = receipt.get('memory') or {}
    if 'error' not in memory or memory['error'] is not None:
        errors.append('memory sampler failed or has no completion record')
    seconds = receipt.get('end_to_end_seconds')
    if not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or seconds < 0:
        errors.append('passed receipt has no finite nonnegative duration')
    if not sha256_value(receipt.get('binary_sha256')):
        errors.append('Sail binary hash is missing or malformed')
    native = (receipt.get('native_package_identity') or {}).get('files_sha256')
    if not isinstance(native, dict) or not native or not all(sha256_value(v) for v in native.values()):
        errors.append('native installed-file hashes are missing or malformed')
    manifest = receipt.get('dataset') or {}
    files = manifest.get('files') or {}
    required = ('vertices.parquet', 'edges.parquet', 'reference.parquet')
    if (set(files) != set(required) or
            any(not isinstance(files.get(name), dict) or not sha256_value(files[name].get('sha256')) for name in required)):
        errors.append('dataset hashes are missing or malformed')
    options = config['datasets'][cell['dataset']]
    observed = dict(manifest.get('parameters') or {}, family=manifest.get('family'),
                    vertices=(manifest.get('counts') or {}).get('vertices'), seed=manifest.get('seed'),
                    **{k: (manifest.get('pagerank') or {}).get(k) for k in ('damping', 'tolerance')})
    if options['family'] == 'edge-list':
        imported = manifest.get('input') or {}
        observed.update(edge_file=imported.get('source_path'), edge_sha256=imported.get('sha256'))
    algorithm_parameters = {} if options['family'] == 'traversal' else {k: config['defaults'][k] for k in ('damping', 'tolerance')}
    for key, value in dict(options, **algorithm_parameters).items():
        if observed.get(key) != value:
            errors.append(f'dataset configuration differs: {key}')
    return errors


def audited_rows(entries, config):
    """Keep every planned outcome; reject conflicting identities symmetrically."""
    rows, identities = [], defaultdict(list)
    for cell, summary, receipt in entries:
        row = cell_row(cell, summary, receipt)
        if row['outcome'] == 'passed':
            row['integrity_errors'] = integrity_errors(cell, summary, receipt, config)
            if not row['integrity_errors']:
                native = receipt['native_package_identity']['files_sha256']
                files = {name: details['sha256'] for name, details in receipt['dataset']['files'].items()}
                row['native_installed_files_identity'] = digest(native)
                row['dataset_files_identity'] = digest(files)
                identities[('Sail binary', 'all cells')].append((row, receipt['binary_sha256']))
                identities[('native installed files', 'all cells')].append((row, digest(native)))
                identities[('dataset files', cell['dataset'])].append((row, digest(files)))
                # Audit the original apparent pass before deriving its weaker
                # scope. Keep the original labels and identities as evidence.
                row['outcome'] = effective_outcome(receipt)
                row['expected_outcome_observed'] = row['outcome'] == cell['expected_outcome']
        rows.append(row)
    for (kind, scope), observations in identities.items():
        if len({identity for _, identity in observations}) > 1:
            for row, _ in observations:
                row['integrity_errors'].append(f'inconsistent {kind} identity across {scope}')
    for row in rows:
        if row['integrity_errors']:
            row['outcome'] = 'integrity_error'
            row['expected_outcome_observed'] = False
    return rows


def aggregate(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in GROUP)].append(row)
    result = []
    for key, trials in sorted(groups.items()):
        passed = [r for r in trials if r['outcome'] == 'passed']
        metrics = {}
        for name in METRICS:
            values = [r[name] for r in passed if r[name] is not None]
            metrics[name] = (dict(samples=len(values), median=median(values), minimum=min(values), maximum=max(values))
                             if values else None)
        result.append(dict(zip(GROUP, key), planned=len(trials), passed=len(passed),
                           outcomes=dict(Counter(r['outcome'] for r in trials)), metrics=metrics))
    return result


def display(metric, divisor=1):
    if metric is None:
        return 'unavailable'
    middle, low, high = (metric[k] / divisor for k in ('median', 'minimum', 'maximum'))
    return f'{middle:.3f} [{low:.3f}, {high:.3f}] (n={metric["samples"]})'


def tables(groups):
    lines = ['# All PageRank and WCC methods', '',
             'Cells show median [minimum, maximum] for passed trials only; n is the available sample count for that metric. Counts retain every outcome.', '',
             'RSS/PSS are sampled execution-phase process totals. Cgroup peak is the lifetime peak through result delivery, before verification. Memory is MiB.', '']
    previous = None
    names = {'pecan': 'Pecan', 'nutmeg-native': 'Banda', 'nutmeg-datafusion': 'Grenada'}
    for group in groups:
        section = tuple(group[k] for k in ('suite', 'dataset', 'mode', 'algorithm'))
        if section != previous:
            lines.extend(['', '## ' + ' / '.join(section), '',
                          '| Path | Variant | Outcomes | Seconds | PSS MiB | RSS MiB | Cgroup MiB |',
                          '| --- | --- | --- | ---: | ---: | ---: | ---: |'])
            previous = section
        metrics = group['metrics']
        outcomes = ', '.join(f'{name}: {count}' for name, count in sorted(group['outcomes'].items()))
        values = [names[group['engine']], group['variant'], outcomes, display(metrics['seconds']),
                  display(metrics['execution_pss_bytes'], 2**20), display(metrics['execution_rss_bytes'], 2**20),
                  display(metrics['cgroup_peak_through_result_bytes'], 2**20)]
        lines.append('| ' + ' | '.join(values) + ' |')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    config = json.loads((args.evidence / 'configuration.json').read_text())
    entries = []
    for cell in plan_cells(config):
        directory = args.evidence / 'cells' / cell['cell_id']
        path = directory / 'summary.json'
        summary = json.loads(path.read_text()) if path.exists() else None
        receipt_path = directory / 'artifacts/receipt.json'
        try:
            receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        except json.JSONDecodeError:
            receipt = None
        entries.append((cell, summary, receipt))
    rows = audited_rows(entries, config)
    groups = aggregate(rows)
    result = dict(generated_utc=datetime.now(timezone.utc).isoformat(),
                  planned_cells=len(rows), outcomes=dict(Counter(r['outcome'] for r in rows)),
                  expected_outcomes_observed=sum(r['expected_outcome_observed'] for r in rows),
                  sources={k: config[k] for k in ('harness_source_sha', 'runtime_source_sha', 'native_source_sha')},
                  integrity_errors=[{k: row[k] for k in ('cell_id', 'original_outcome', 'receipt_outcome', 'integrity_errors')}
                                    for row in rows if row['integrity_errors']],
                  groups=groups)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with (args.output / 'cells.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    (args.output / 'tables.md').write_text(tables(groups) + '\n')
    print(json.dumps({k: result[k] for k in ('planned_cells', 'outcomes', 'expected_outcomes_observed')}))
    return 1 if result['integrity_errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
