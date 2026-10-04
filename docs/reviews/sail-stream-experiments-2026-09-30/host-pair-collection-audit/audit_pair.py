#!/usr/bin/env python3
"""Read a local mirror of the frozen six-cell study; never invoke a workload."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
PLAN_NAME = 'pair16k-20260930201356-plan.json'
PLAN_SHA = 'd51e9f4d5a1d16fb18c36e93fcb3d641c017610a7319ee56a203676800dbe1ab'
HELPER_SHA = 'c8d59db362136879bbd3a6efe8f527311849e3e0be18ddb64e6da996bdfcd318'
RUNNER_SHA = '8220b9951c51420bd34ca5e32ba20c2304a1b863aa5f2fa1fa9467e74d60a7f1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def support():
    path = EXP / 'closed-cell-audit/audit_cell.py'
    if sha(path) != HELPER_SHA:
        raise ValueError('frozen integrity helper changed')
    spec = importlib.util.spec_from_file_location('pair_integrity_helper', path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def prepared(h):
    directory = EXP / 'host-pair-16k'
    path = directory / PLAN_NAME
    if sha(path) != PLAN_SHA or sha(directory / 'run_host_pair.py') != RUNNER_SHA:
        raise ValueError('frozen paired plan/runner changed')
    plan = h.read_json(path)
    configs = []
    for entry in plan['runs']:
        path = directory / entry['configuration']
        if sha(path) != entry['configuration_sha256']:
            raise ValueError('frozen configuration changed: ' + entry['configuration'])
        config = h.read_json(path)
        expected_output = plan['remote_root'] + '/' + plan['namespace'] + '/cells/' + config['run_id']
        if config['host_output'] != expected_output:
            raise ValueError('unexpected real collection namespace')
        value = json.loads(json.dumps(config))
        for key in ('run_id', 'host_output', 'runtime_source_sha', 'container_sail_binary'):
            del value[key]
        del value['suites'][0]['name']
        digest = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        if digest != plan['common_configuration_sha256']:
            raise ValueError('configuration parity differs')
        configs.append(config)
    if [(e['order'], e['phase'], e['host']) for e in plan['runs']] != [
            (1, 'warmup', 'A'), (2, 'warmup', 'B'), (3, 'measurement', 'A'),
            (4, 'measurement', 'B'), (5, 'measurement', 'B'), (6, 'measurement', 'A')]:
        raise ValueError('frozen study order differs')
    return plan, configs


def load_array(a, h, path):
    try:
        a.check(not path.is_symlink(), 'symlink input: ' + str(path))
        a.files[str(path)] = h.file_info(path)
        value = h.read_json(path)
        if not isinstance(value, list):
            raise ValueError('expected JSON array')
        return value
    except FileNotFoundError:
        a.missing.append('missing input: ' + str(path))
    except (OSError, ValueError) as error:
        a.errors.append('invalid input: ' + str(path) + ': ' + str(error))
    return None


def classified(record, receipt):
    """Pinned classifier priority; preserve producer and wrapper outcomes too."""
    state = record['inspect']['state']
    events = dict(line.split() for line in receipt['cgroup_after']['memory.events'].splitlines())
    if state['OOMKilled'] or int(events.get('oom_kill', '0')) > 0:
        return 'oom'
    for key, value in [('outer_timeout', 'outer_timeout'), ('operator_interrupted', 'interrupted')]:
        if record.get(key):
            return value
    if record['transport_errors']:
        return 'orchestration_error'
    if receipt.get('outcome') == 'passed' and record['attach_returncode'] != 0:
        return 'exit_receipt_mismatch'
    return receipt.get('outcome', 'invalid_receipt')


def number(value, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def inspect_trial(a, h, plan, entry, config, row, receipt, record, result, pre, before, inventory):
    expected_row = {key: entry[key] for key in ('order', 'phase', 'host', 'configuration')}
    a.check(h.canonical({k: row[k] for k in expected_row}) == h.canonical(expected_row), 'row order/namespace differs')
    args = dict(plan['expected_arguments'], sail_binary=config['container_sail_binary'],
                runtime_source_sha=config['runtime_source_sha'], output=entry['cell_output'])
    a.check(h.canonical(receipt['arguments']) == h.canonical(args), 'exact cell arguments differ')
    a.check(row['orchestration'] == record, 'row orchestration differs from collected original')
    outcome = classified(record, receipt)
    if row['runner_wall_timeout']:
        a.check(row['underlying_outcome'] == outcome, 'underlying timeout outcome differs')
        outcome = 'orchestrator_timeout'
    a.check(row['outcome'] == outcome, 'row classification differs')
    a.check(result['outcome'] == classified(record, receipt), 'safe runner classification differs')
    a.check(row['receipt_outcome'] == receipt['outcome'], 'row receipt outcome differs')
    for name in ('started_utc', 'finished_utc'):
        datetime.fromisoformat(row[name])
    a.check(pre['config_sha256'] == entry['configuration_sha256'], 'preflight config differs')
    observed = pre['observed']
    a.check(observed['binary_sha256'] == entry['binary_sha256'], 'preflight binary differs')
    a.check(observed['harness_head'] == config['harness_source_sha'] and observed['harness_status'] == '', 'preflight controller differs')
    a.check(observed['native_sha256'] == plan['expected_native_package_identity']['files_sha256']['_native.cpython-312-x86_64-linux-gnu.so'], 'preflight native differs')
    a.check(observed['datasets']['weighted16k']['sha256'] == plan['dataset_manifest_sha256'], 'preflight dataset differs')
    a.check(isinstance(observed['boot_id'], str) and bool(observed['boot_id']) and row['boot_id'] == observed['boot_id'], 'boot identity missing/differs')
    memory = receipt['memory']; execute = memory.get('phase_peaks', {}).get('execute', {})
    copied = dict(seconds=receipt.get('end_to_end_seconds'), execution_pss_bytes=execute.get('pss_bytes'),
                  execution_rss_bytes=execute.get('rss_bytes'), guest_steal_fraction=receipt.get('guest_steal_fraction'),
                  correctness=receipt.get('correctness'), algorithm_iterations=receipt.get('algorithm_iterations'))
    for key, value in copied.items():
        a.check(row.get(key) == value, 'copied metric differs: ' + key)
    active = 'sail-' + config['run_id'] + '-1'
    samples = [x for x in inventory if active in x['names']]
    siblings = sorted({name for x in samples for name in x['names'] if name != active})
    sampling = dict(interval_seconds=2, samples_during_cell=len(samples), observed_sibling_containers=siblings,
                    inventory_errors=sum(x['returncode'] != 0 for x in inventory), scope='sampled observation, not a host-wide lock')
    a.check(row['concurrency_sampling'] == sampling, 'concurrency summary differs from raw inventory')
    correctness = receipt.get('correctness')
    wanted = dict(rows=16384, unique=16384, parent_tree_checked=True, reference='independent BFS/heap-Dijkstra')
    correct = isinstance(correctness, dict) and all(type(correctness.get(k)) is type(v) and correctness[k] == v for k, v in wanted.items())
    if receipt['outcome'] == 'passed':
        a.check(correct, 'passed receipt lacks complete reference/parent checks')
        a.check(receipt.get('algorithm_converged') is True, 'passed receipt lacks convergence')
        if 'cgroup_execution_after' not in receipt:
            a.missing.append('passed receipt lacks execution-end cgroup snapshot')
        output_files = receipt.get('result_files')
        a.check(isinstance(output_files, list) and bool(output_files), 'passed receipt lacks result inventory')
        if isinstance(output_files, list):
            a.check(all(h.safe_name(f['name']) and h.SHA.fullmatch(f['sha256']) is not None
                        and type(f['bytes']) is int and f['bytes'] > 0 for f in output_files),
                    'invalid recorded result inventory')
    state = record['inspect']['state']
    eligible = (outcome == 'passed' and correct and receipt.get('algorithm_converged') is True
        and row['runner_returncode'] == 0 and type(row['runner_returncode']) is int
        and row['runner_wall_timeout'] is False and state['Running'] is False and state['ExitCode'] == 0
        and not receipt.get('cleanup_errors') and pre['outcome'] == 'passed'
        and observed['free_bytes'] >= plan['minimum_free_bytes']
        and before['returncode'] == 0 and before['names'] == []
        and memory.get('error') is None and memory.get('execution_sampled') is True
        and number(copied['seconds'], True) and number(copied['execution_pss_bytes'], True)
        and number(copied['guest_steal_fraction']) and copied['guest_steal_fraction'] <= 1
        and bool(samples) and not siblings and not sampling['inventory_errors'])
    a.check(type(row['comparison_eligible']) is bool, 'invalid comparison eligibility type')
    # This verifier may impose stronger closure checks; it never upgrades a runner rejection.
    return dict(recomputed_outcome=outcome, recorded_reference_complete=correct,
                candidate_ratio_eligible=bool(eligible and row['comparison_eligible']))


def audit_collection(collection):
    h = support(); plan, configs = prepared(h); outer = h.Audit(EXP)
    sequence = outer.load(collection / 'sequence.json')
    rows = []
    if sequence is not None:
        outer.check(sequence.get('plan_sha256') == PLAN_SHA, 'sequence plan hash differs')
        rows = sequence.get('rows')
        if not isinstance(rows, list):
            outer.errors.append('sequence rows must be an array'); rows = []
        outer.check(len(rows) <= 6, 'extra sequence rows')
    if len(rows) != 6:
        outer.missing.append('six completed ordered rows not available')
    reports = []
    for index, (entry, config) in enumerate(zip(plan['runs'], configs)):
        a = h.Audit(EXP)
        cell = collection / 'cells' / config['run_id']
        profile = dict(config_path='host-pair-16k/' + entry['configuration'], evidence_pins=[],
            binary_sha256=entry['binary_sha256'], native_identity_canonical_sha256=h.canonical(plan['expected_native_package_identity']),
            dataset_canonical_sha256=h.canonical(plan['expected_dataset']), resolved_dataset_path=plan['expected_arguments']['dataset'])
        integrity = h.audit(cell, profile, EXP)
        a.errors.extend(integrity['errors']); a.missing.extend(integrity['inconclusive_reasons']); a.files.update(integrity['files'])
        prefix = collection / f"{entry['order']:02d}"
        row = a.load(prefix.with_suffix('.result.json'))
        receipt = a.load(cell / 'diagnostics/receipt.json'); record = a.load(cell / 'cell/orchestration.json')
        result = a.load(cell / 'result.json'); pre = a.load(prefix.with_suffix('.preflight.json'))
        before = a.load(prefix.with_suffix('.inventory-before.json')); inventory = load_array(a, h, prefix.with_suffix('.inventory.json'))
        if row is not None and index < len(rows):
            a.check(row == rows[index], 'per-cell result differs from ordered sequence row')
        checks = {}
        if all(x is not None for x in [row, receipt, record, result, pre, before, inventory]):
            a.section('paired trial', lambda: checks.update(inspect_trial(a, h, plan, entry, config, row, receipt, record, result, pre, before, inventory)))
        report = dict(order=entry['order'], phase=entry['phase'], host=entry['host'], run_id=config['run_id'],
            integrity_status='integrity_error' if a.errors else ('inconclusive' if a.missing else 'integrity_verified'),
            errors=a.errors, inconclusive_reasons=a.missing, recorded_outcomes=integrity['recorded_outcomes'],
            sequence_row=row, correctness=checks.get('recorded_reference_complete'),
            ratio_eligible=bool(checks.get('candidate_ratio_eligible') and not a.errors and not a.missing))
        reports.append(report); outer.files.update(a.files)
    # Bind the entire local evidence set to a stable audit interval.
    for name, original in outer.files.items():
        try:
            outer.check(not Path(name).is_symlink() and h.file_info(Path(name)) == original, 'input changed during audit: ' + name)
        except OSError:
            outer.missing.append('input disappeared during audit: ' + name)
    prepared(h)
    outer.check(sha(EXP / 'closed-cell-audit/audit_cell.py') == HELPER_SHA, 'helper changed during audit')
    eligible = (not outer.errors and not outer.missing and all(r['ratio_eligible'] for r in reports)
                and len({r['sequence_row']['boot_id'] for r in reports}) == 1)
    ratios = None
    if eligible:
        a1, b1, b2, a2 = [r['sequence_row']['seconds'] for r in reports[2:]]
        ratios = dict(adjacent_A_over_B=[a1 / b1, a2 / b2], geometric_mean_A_over_B=math.sqrt(a1 / b1 * a2 / b2))
    errors = bool(outer.errors or any(r['errors'] for r in reports))
    missing = bool(outer.missing or any(r['inconclusive_reasons'] for r in reports))
    return dict(recorded_utc=datetime.now(timezone.utc).isoformat(), collection_directory=str(collection.resolve()),
        plan_sha256=PLAN_SHA, helper_sha256=HELPER_SHA, verifier_sha256=sha(Path(__file__)),
        integrity_status='integrity_error' if errors else ('inconclusive' if missing else 'integrity_verified'),
        errors=outer.errors, inconclusive_reasons=outer.missing, cells=reports, ratio_eligible=eligible,
        shared_host_ratios=ratios, evidence_files=outer.files,
        scope='Local recorded evidence only; no engine, remote access, result Parquet recomputation or independent new Dijkstra computation. Correctness means the complete recorded producer reference/parent checks under the pinned source.',
        ratio_scope='Descriptive ratios on shared host, two measurements per host; warmups excluded. Whole-VM whole-trial steal; sampled execute PSS; no quiet-host or runtime-only causal attribution. Frozen runner has no per-cell macOS closure pressure deltas.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection-dir', type=Path, required=True,
                        help='local mirror of pair16k-20260930201356, including sequence and cells/')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.collection_dir.resolve() == args.output.resolve() or args.collection_dir.resolve() in args.output.resolve().parents:
        parser.error('audit output must be outside collected evidence')
    report = audit_collection(args.collection_dir)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    return 0 if report['ratio_eligible'] else (1 if report['integrity_status'] == 'integrity_error' else 2)


if __name__ == '__main__':
    raise SystemExit(main())
