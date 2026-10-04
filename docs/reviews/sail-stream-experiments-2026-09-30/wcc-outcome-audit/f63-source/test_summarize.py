from copy import deepcopy
import csv
import json
from pathlib import Path
import sys

import pytest

import summarize
from run_matrix import cell_command, configuration_fingerprint, plan_cells
from summarize import aggregate, audited_rows, cell_row, display


def trial(outcome, seconds, pss=None):
    cell = dict(cell_id=outcome, sequence=1, repeat=1, suite='sample', dataset='sparse', mode='local',
                algorithm='pagerank', engine='pecan', variant='optimized', expected_outcome='passed')
    summary = dict(outcome=outcome, expected_outcome_observed=outcome == 'passed')
    receipt = dict(end_to_end_seconds=seconds, memory={'phase_peaks': {'execute': {'pss_bytes': pss}}})
    return cell_row(cell, summary, receipt)


def test_failures_remain_counted_but_cannot_improve_summary():
    group, = aggregate([trial('passed', 5, 10), trial('passed', 7, 20), trial('mismatch', 0.01, 1)])
    assert group['outcomes'] == {'passed': 2, 'mismatch': 1}
    assert group['metrics']['seconds'] == dict(samples=2, median=6, minimum=5, maximum=7)
    assert group['metrics']['execution_pss_bytes']['median'] == 15


def test_missing_memory_and_failed_only_groups_are_not_zero():
    group, = aggregate([trial('passed', 5)])
    assert group['metrics']['execution_pss_bytes'] is None
    group, = aggregate([trial('nonconverged', 2)])
    assert group['passed'] == 0
    assert all(metric is None for metric in group['metrics'].values())
    group, = aggregate([trial('passed', 5, 10), trial('passed', 7)])
    assert '(n=1)' in display(group['metrics']['execution_pss_bytes'])
    assert '(n=2)' in display(group['metrics']['seconds'])


def records(algorithm='pagerank'):
    config = json.loads(Path(__file__).with_name('matrix.example.json').read_text())
    config.update(harness_source_sha='a' * 40, runtime_source_sha='b' * 40, native_source_sha='c' * 40)
    cells = [cell for cell in plan_cells(config) if cell['suite'] == 'distributed' and
             cell['dataset'] == 'sparse-10000' and cell['engine'] == 'nutmeg-native' and
             cell['algorithm'] == algorithm and cell['variant'] == 'optimized']
    entries = []
    for cell in cells:
        command = cell_command(config, cell)
        arguments = {}
        for key, value in zip(command[1::2], command[2::2]):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
            arguments[key.removeprefix('--').replace('-', '_')] = value
        arguments.update(allow_dirty=False, allow_unisolated=False)
        summary = dict(cell, outcome='passed', expected_outcome_observed=True,
                       configuration_sha256=configuration_fingerprint(config))
        receipt = dict(outcome='passed', end_to_end_seconds=5, arguments=arguments,
                       **{key: config[key] for key in ('harness_source_sha', 'runtime_source_sha', 'native_source_sha')},
                       source_dirty='', memory={'error': None, 'execution_sampled': False},
                       worker_task_slots_per_worker=config['defaults']['worker_task_slots'],
                       worker_task_slots_total=2 * config['defaults']['worker_task_slots'],
                       sail_pool_per_process_bytes=config['defaults']['sail_pool_bytes'],
                       prepaid_native_quota_bytes=config['defaults']['native_quota'],
                       remaining_participating_df_budget_bytes=config['defaults']['sail_pool_bytes'] - config['defaults']['native_quota'],
                       binary_sha256='d' * 64,
                       native_package_identity={'files_sha256': {'extension.so': 'e' * 64}},
                       dataset={'family': 'sparse', 'seed': 20260927, 'counts': {'vertices': 10000},
                                'parameters': {'degree': 8, 'block_size': 1024},
                                'pagerank': {'damping': .85, 'tolerance': 1e-8},
                                'files': {name: {'sha256': 'f' * 64} for name in
                                          ('vertices.parquet', 'edges.parquet', 'reference.parquet')}})
        entries.append((cell, summary, receipt))
    return config, entries


def test_valid_records_allow_distinct_host_and_native_sources_and_missing_pss():
    config, entries = records()
    rows = audited_rows(entries, config)
    assert all(row['outcome'] == 'passed' and not row['integrity_errors'] for row in rows)
    group, = aggregate(rows)
    assert group['passed'] == 3
    assert group['metrics']['seconds']['samples'] == 3
    assert group['metrics']['execution_pss_bytes'] is None


def test_imported_dataset_requires_the_configured_input_hash():
    config, entries = records()
    config['datasets']['sparse-10000'] = dict(family='edge-list', vertices=10000,
                                           edge_file='/inputs/uniform.edges', edge_sha256='1' * 64)
    for cell, summary, receipt in entries:
        summary['configuration_sha256'] = configuration_fingerprint(config)
        receipt['dataset'].update(family='edge-list', seed=None, parameters={},
                                  input={'source_path': '/inputs/uniform.edges', 'sha256': '1' * 64})
    assert all(row['outcome'] == 'passed' for row in audited_rows(entries, config))
    entries[0][2]['dataset']['input']['sha256'] = '2' * 64
    row = audited_rows(entries, config)[0]
    assert row['outcome'] == 'integrity_error'
    assert 'dataset configuration differs: edge_sha256' in row['integrity_errors']


@pytest.mark.parametrize('target,key,value,reason', [
    ('summary', 'configuration_sha256', 'wrong', 'configuration fingerprint'),
    ('summary', 'engine', 'pecan', 'summary cell field differs: engine'),
    ('receipt', 'outcome', 'mismatch', 'disagrees with receipt outcome'),
    ('receipt', 'native_source_sha', 'a' * 40, 'source differs: native_source_sha'),
    ('receipt', 'end_to_end_seconds', float('inf'), 'finite nonnegative duration'),
    ('arguments', 'engine', 'pecan', 'receipt argument differs: engine'),
    ('arguments', 'max_iterations', 5, 'receipt argument differs: max_iterations'),
    ('arguments', 'allow_dirty', True, 'receipt argument differs: allow_dirty'),
    ('arguments', 'worker_task_slots', 1, 'receipt argument differs: worker_task_slots'),
    ('arguments', 'sail_pool_bytes', 1, 'receipt argument differs: sail_pool_bytes'),
    ('receipt', 'worker_task_slots_total', 1, 'admission receipt differs: worker_task_slots_total'),
    ('receipt', 'remaining_participating_df_budget_bytes', 1, 'admission receipt differs: remaining_participating_df_budget_bytes'),
])
def test_inconsistent_pass_is_retained_with_original_outcome(target, key, value, reason):
    config, entries = records()
    cell, summary, receipt = deepcopy(entries[0])
    {'summary': summary, 'receipt': receipt, 'arguments': receipt['arguments']}[target][key] = value
    row, = audited_rows([(cell, summary, receipt)], config)
    assert row['outcome'] == 'integrity_error'
    assert row['original_outcome'] == 'passed'
    assert any(reason in error for error in row['integrity_errors'])
    group, = aggregate([row])
    assert group['outcomes'] == {'integrity_error': 1}
    assert group['metrics']['seconds'] is None


@pytest.mark.parametrize('identity', ['binary', 'native', 'dataset'])
def test_conflicting_artifacts_reject_all_involved_trials(identity):
    config, entries = records()
    receipt = entries[1][2]
    if identity == 'binary':
        receipt['binary_sha256'] = '1' * 64
    elif identity == 'native':
        receipt['native_package_identity']['files_sha256']['extension.so'] = '2' * 64
    else:
        receipt['dataset']['files']['edges.parquet']['sha256'] = '3' * 64
    rows = audited_rows(entries, config)
    assert all(row['outcome'] == 'integrity_error' for row in rows)
    assert all(any('inconsistent' in error for error in row['integrity_errors']) for row in rows)
    assert aggregate(rows)[0]['metrics']['seconds'] is None


def test_missing_receipt_pass_is_distinct_from_never_run_and_preserved_oom():
    config, entries = records()
    cell, summary, _ = entries[0]
    row, = audited_rows([(cell, summary, None)], config)
    assert row['outcome'] == 'integrity_error' and row['original_outcome'] == 'passed'
    summary['outcome'] = 'oom'
    row, = audited_rows([(cell, summary, None)], config)
    assert row['outcome'] == row['original_outcome'] == 'oom'
    assert not row['integrity_errors']
    rows = audited_rows([(cell, None, None) for cell in plan_cells(config)], config)
    assert len(rows) == 150 and all(row['outcome'] == 'not_run' for row in rows)
    assert sum(group['planned'] for group in aggregate(rows)) == 150


def test_receipt_without_orchestration_summary_is_incomplete_not_never_run():
    config, entries = records()
    cell, _, receipt = entries[0]
    row, = audited_rows([(cell, None, receipt)], config)
    assert row['outcome'] == 'incomplete_record' and row['receipt_outcome'] == 'passed'
    assert aggregate([row])[0]['metrics']['seconds'] is None


def test_export_retains_all_planned_cells_and_integrity_reasons_in_both_formats(tmp_path, monkeypatch):
    config, entries = records()
    entries[0][2]['arguments']['engine'] = 'pecan'
    evidence, output = tmp_path / 'evidence', tmp_path / 'summary'
    evidence.mkdir()
    (evidence / 'configuration.json').write_text(json.dumps(config))
    for cell, summary, receipt in entries:
        directory = evidence / 'cells' / cell['cell_id']
        (directory / 'artifacts').mkdir(parents=True)
        (directory / 'summary.json').write_text(json.dumps(summary))
        (directory / 'artifacts/receipt.json').write_text(json.dumps(receipt))
    monkeypatch.setattr(sys, 'argv', ['summarize.py', '--evidence', str(evidence), '--output', str(output)])
    assert summarize.main() == 1
    exported = json.loads((output / 'summary.json').read_text())
    assert exported['planned_cells'] == 150
    assert exported['outcomes'] == {'passed': 2, 'integrity_error': 1, 'not_run': 147}
    error, = exported['integrity_errors']
    assert error['original_outcome'] == error['receipt_outcome'] == 'passed'
    assert error['integrity_errors'] == ['receipt argument differs: engine']
    with (output / 'cells.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 150
    row, = [row for row in rows if row['outcome'] == 'integrity_error']
    assert row['original_outcome'] == 'passed'
    assert 'receipt argument differs: engine' in row['integrity_errors']
    group, = [group for group in exported['groups'] if group['passed']]
    assert group['metrics']['seconds']['samples'] == 2
    assert 'not_run: 3' in (output / 'tables.md').read_text()
