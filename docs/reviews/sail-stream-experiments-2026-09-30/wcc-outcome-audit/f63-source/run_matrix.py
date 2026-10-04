#!/usr/bin/env python3
"""Run every graph comparison cell sequentially in a fresh Docker container.

The configuration contains operator-specific paths; keep the actual file outside
this checkout. A dry run emits the complete deterministic order without calling
Docker. Nonzero cells retain their receipt, logs, inspect state, and outcome.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import random
import re
import subprocess
import sys

from traversal_source import MAX_DEGREE
import time

from runtime import algorithm_method, validate_admission_settings
from validation_outcome import effective_outcome, expected_validation_outcome, resumed_outcome


ENGINES = ('pecan', 'nutmeg-native', 'nutmeg-datafusion')
# Argentea (native partitions on Sail workers) runs bfs and sssp cells only and is never a default engine.
ALL_ENGINES = ENGINES + ('argentea',)
ALGORITHMS = ('pagerank', 'wcc', 'bfs', 'sssp')
VARIANTS = ('reference', 'optimized', 'fused', 'frontier', 'delta_star', 'push_pull')
DEFAULT_VARIANTS = ('reference', 'optimized')


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def configuration_fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def validate_config(config):
    required = ('run_id', 'docker_context', 'image', 'target_volume', 'container_python',
                'container_repo', 'container_sail_binary', 'runtime_source_sha', 'native_source_sha',
                'harness_source_sha', 'container_root', 'host_output', 'seed',
                'limits', 'defaults', 'datasets', 'suites')
    for key in required:
        if key not in config:
            raise ValueError(f'missing configuration key: {key}')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', config['run_id']):
        raise ValueError('run_id must be 1..40 lowercase letters, digits or hyphens')
    for key in ('runtime_source_sha', 'native_source_sha', 'harness_source_sha'):
        if not re.fullmatch(r'[a-f0-9]{40}', config[key]):
            raise ValueError(f'{key} must be an exact Git commit')
    for key in ('container_python', 'container_repo', 'container_sail_binary', 'container_root'):
        path = PurePosixPath(config[key])
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError(f'{key} must be an absolute container path without ..')
    if not Path(config['host_output']).is_absolute():
        raise ValueError('host_output must be an absolute host path')
    limits = config['limits']
    if limits['cpus'] <= 0 or limits['memory_gib'] <= 0 or limits['outer_timeout_seconds'] <= 0:
        raise ValueError('resource limits must be positive')
    if not re.fullmatch(r'[0-9,-]+', limits['cpuset_cpus']):
        raise ValueError('cpuset_cpus must be an explicit CPU list/range')
    container_environment(config)
    for key in ('worker_task_slots', 'sail_pool_bytes', 'native_quota'):
        if key not in config['defaults']:
            raise ValueError(f'missing configuration key: defaults.{key}')
    validate_admission_settings(**{key: config['defaults'][key] for key in
                                  ('worker_task_slots', 'sail_pool_bytes', 'native_quota')})
    for name, dataset in config['datasets'].items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
            raise ValueError(f'invalid dataset name: {name}')
        if dataset['family'] not in ('sparse', 'chain', 'edge-list', 'traversal', 'graph500', 'edge-list-traversal', 'snap-edge-list') or dataset['vertices'] <= 0:
            raise ValueError(f'invalid dataset: {name}')
        if dataset['family'] == 'traversal':
            if not 8 <= dataset['vertices'] <= 100000:
                raise ValueError('bounded traversal oracle requires 8..100000 vertices')
            if not 0 <= dataset.get('source', 0) < dataset['vertices']:
                raise ValueError('traversal source outside graph')
        if dataset['family'] == 'graph500':
            scale = dataset.get('scale', 0)
            if not isinstance(scale, int) or not 1 <= scale <= 40 or dataset['vertices'] != 2 ** scale:
                raise ValueError('Graph500 vertices must equal 2^scale, with scale in 1..40')
            edge_factor = dataset.get('edge_factor', 16)
            if not isinstance(edge_factor, int) or edge_factor <= 0:
                raise ValueError('Graph500 edge factor must be a positive integer')
            source = dataset.get('source', 0)
            if source != MAX_DEGREE and (type(source) is not int or not 0 <= source < dataset['vertices']):
                raise ValueError(f'Graph500 source outside graph (a vertex id or {MAX_DEGREE!r})')
            generator = PurePosixPath(dataset.get('generator', ''))
            if not generator.is_absolute() or '..' in generator.parts:
                raise ValueError('Graph500 generator must be an absolute container path without ..')
            validation = dataset.get('validation')
            if validation not in ('reference', 'certificate'):
                raise ValueError('Graph500 validation must explicitly be reference or certificate')
            if validation == 'reference' and (dataset['vertices'] > 100000 or dataset['vertices'] * edge_factor > 1000000):
                raise ValueError('Graph500 reference oracle is restricted to 100000 vertices and 1000000 tuples')
            if dataset.get('certificate_max_rounds', 10000) <= 0:
                raise ValueError('Graph500 certificate round cap must be positive')
            if 'expected_edge_sha256' in dataset and not re.fullmatch(r'[a-f0-9]{64}', dataset['expected_edge_sha256']):
                raise ValueError('Graph500 expected_edge_sha256 must pin the canonical edge bytes')
        if dataset['family'] in ('edge-list', 'edge-list-traversal', 'snap-edge-list'):
            path = PurePosixPath(dataset.get('edge_file', ''))
            if not path.is_absolute() or '..' in path.parts:
                raise ValueError('edge_file must be an absolute container path without ..')
            if not re.fullmatch(r'[a-f0-9]{64}', dataset.get('edge_sha256', '')):
                raise ValueError('edge_sha256 must pin the imported bytes')
        if dataset['family'] in ('edge-list-traversal', 'snap-edge-list'):
            if type(dataset['vertices']) is not int or dataset['vertices'] >= 1 << 63:
                raise ValueError('imported traversal vertices must fit int64')
            if dataset.get('weight_policy') not in ('unit', 'splitmix64-1-16'):
                raise ValueError('imported traversal requires an explicit weight policy')
            seed = dataset.get('weight_seed', 42)
            if type(seed) is not int or not 0 <= seed < 1 << 64:
                raise ValueError('weight seed must be an unsigned 64-bit integer')
            source = dataset.get('source', 0)
            if source != MAX_DEGREE and (type(source) is not int or not 0 <= source < dataset['vertices']):
                raise ValueError(f'imported traversal source outside graph (a dense vertex id or {MAX_DEGREE!r})')
            if type(dataset.get('directed', True)) is not bool:
                raise ValueError('imported traversal directed must be boolean')
            if dataset.get('validation') not in ('reference', 'certificate'):
                raise ValueError('imported traversal validation must be reference or certificate')
            if dataset['validation'] == 'reference' and dataset['vertices'] > 100000:
                raise ValueError('imported traversal reference oracle is restricted to 100000 vertices')
            if dataset.get('certificate_max_rounds', 10000) <= 0:
                raise ValueError('imported traversal certificate round cap must be positive')
            if 'expected_edge_sha256' in dataset and not re.fullmatch(r'[a-f0-9]{64}', dataset['expected_edge_sha256']):
                raise ValueError('expected_edge_sha256 must pin the canonical weighted edge bytes')
    for suite in config['suites']:
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', suite['name']):
            raise ValueError('suite name must be safe in a filename')
        if suite['mode'] not in ('local', 'process-cluster') or suite['repetitions'] <= 0:
            raise ValueError('invalid suite mode or repetition count')
        if set(suite['datasets']) - config['datasets'].keys():
            raise ValueError('suite names an unknown dataset')
        if set(suite.get('engines', ENGINES)) - set(ALL_ENGINES):
            raise ValueError('suite names an unknown engine')
        if set(suite['algorithms']) - set(ALGORITHMS):
            raise ValueError('suite names an unknown algorithm')
        for dataset_name in suite['datasets']:
            dataset = config['datasets'][dataset_name]
            family = dataset['family']
            traversal_family = family in TRAVERSAL_FAMILIES
            for algorithm in suite['algorithms']:
                if algorithm in ('bfs', 'sssp'):
                    if not traversal_family:
                        raise ValueError('algorithm and fixture reference family are incompatible')
                elif traversal_family and dataset.get('validation') != 'certificate':
                    # A traversal fixture carries no PageRank/WCC reference; ranking
                    # algorithms run on it only under the certificate policy.
                    raise ValueError('algorithm and fixture reference family are incompatible: ranking algorithms on a traversal fixture require validation=certificate')
        variants = suite.get('variants', config.get('variants', DEFAULT_VARIANTS))
        if set(variants) - set(VARIANTS):
            raise ValueError('suite names an unknown variant')
        if suite.get('stage_order', 'canonical') not in STAGE_ORDERS:
            raise ValueError('suite stage_order must be canonical or asStaged')
        for engine in suite.get('engines', ENGINES):
            for algorithm in suite['algorithms']:
                for variant in variants:
                    algorithm_method(engine, algorithm, variant)


TRAVERSAL_FAMILIES = ('traversal', 'graph500', 'edge-list-traversal', 'snap-edge-list')
# Native staging order per suite; canonical is the server default and is not sent.
STAGE_ORDERS = ('canonical', 'asStaged')


def plan_cells(config):
    validate_config(config)
    rng = random.Random(config['seed'])
    result = []
    for suite in config['suites']:
        for repeat in range(1, suite['repetitions'] + 1):
            group = []
            for dataset in suite['datasets']:
                for engine in suite.get('engines', ENGINES):
                    for algorithm in suite['algorithms']:
                        for variant in suite.get('variants', config.get('variants', DEFAULT_VARIANTS)):
                            name = f"{suite['name']}-r{repeat}-{dataset}-{engine}-{algorithm}-{variant}"
                            cell = dict(cell_id=name, suite=suite['name'], repeat=repeat,
                                dataset=dataset, engine=engine, algorithm=algorithm, variant=variant,
                                mode=suite['mode'], stage_order=suite.get('stage_order', 'canonical'),
                                max_iterations=suite.get('max_iterations', config['defaults']['max_iterations']),
                                diagnostic=bool(suite.get('diagnostic', False)))
                            expected = expected_validation_outcome(cell_command(config, cell))
                            cell['expected_outcome'] = suite.get('expected_outcomes', {}).get(variant, {}).get(engine, expected)
                            group.append(cell)
            rng.shuffle(group)
            result.extend(group)
    if len({cell['cell_id'] for cell in result}) != len(result):
        raise ValueError('cell IDs are not unique')
    for index, cell in enumerate(result, 1):
        cell['sequence'] = index
    return result


def docker_base(config):
    return ['docker', '--context', config['docker_context']]


def container_environment(config):
    """Optional `environment` map: SAIL_* settings exported into every cell container.

    Only Sail settings are admitted so a matrix cannot smuggle credentials or
    interpreter flags into the isolated trial; the map is part of the recorded
    configuration and therefore of the cell fingerprint.
    """
    environment = config.get('environment', {})
    if not isinstance(environment, dict):
        raise ValueError('environment must be a map of SAIL_* names to strings')
    options = []
    for key, value in sorted(environment.items()):
        if not (isinstance(key, str) and key.startswith('SAIL_') and isinstance(value, str)):
            raise ValueError(f'environment entry {key!r} is not a SAIL_* string setting')
        options.extend(['--env', f'{key}={value}'])
    return options


def container_options(config, name, image=None):
    limits = config['limits']
    return ['--name', name, '--init', '--cpus', str(limits['cpus']),
            '--cpuset-cpus', limits['cpuset_cpus'], '--memory', f"{limits['memory_gib']}g",
            '--memory-swap', f"{limits['memory_gib']}g", '--pids-limit', '1024',
            '--mount', f"type=volume,source={config['target_volume']},target=/targets",
            '--workdir', config['container_repo'], '--env', 'PYTHONUNBUFFERED=1',
            *container_environment(config),
            '--entrypoint', config['container_python'], image or config['image']]


def cell_command(config, cell):
    root = PurePosixPath(config['container_root'])
    defaults = config['defaults']
    dataset = config['datasets'][cell['dataset']]
    command = [str(PurePosixPath(config['container_repo']) / 'examples/extensions/benchmarks/graph_cell.py'),
               '--sail-binary', config['container_sail_binary'],
               '--runtime-source-sha', config['runtime_source_sha'],
               '--native-source-sha', config['native_source_sha'],
               '--dataset', str(root / 'datasets' / cell['dataset']),
               '--expected-dataset-family', dataset['family'],
               '--expected-vertices', str(dataset['vertices']),
               '--output', str(root / 'cells' / cell['cell_id']),
               '--engine', cell['engine'], '--algorithm', cell['algorithm'], '--variant', cell['variant'],
               '--mode', cell['mode'],
               '--repeat', str(cell['repeat']), '--max-iterations', str(cell['max_iterations'])]
    for name in ('partitions', 'threads', 'worker_task_slots', 'sail_pool_bytes',
                 'native_quota', 'tolerance', 'damping', 'timeout', 'seed'):
        command.extend(['--' + name.replace('_', '-'), str(defaults[name])])
    if cell.get('stage_order', 'canonical') != 'canonical':
        command.extend(['--stage-order', cell['stage_order']])
    if cell['algorithm'] in ('bfs', 'sssp'):
        command.extend(['--source', str(dataset.get('source', 0)), '--delta', str(defaults.get('delta', 1.0))])
        command.append('--directed' if dataset.get('directed', dataset['family'] != 'graph500') else '--no-directed')
        if dataset['family'] in ('graph500', 'edge-list-traversal', 'snap-edge-list'):
            command.extend(['--traversal-validation', dataset['validation'],
                            '--certificate-max-rounds', str(dataset.get('certificate_max_rounds', 10000))])
            if 'expected_edge_sha256' in dataset:
                flag = '--expected-graph500-sha256' if dataset['family'] == 'graph500' else '--expected-edge-sha256'
                command.extend([flag, dataset['expected_edge_sha256']])
        if dataset['family'] in ('edge-list-traversal', 'snap-edge-list'):
            command.extend(['--expected-input-sha256', dataset['edge_sha256'],
                            '--expected-weight-policy', dataset.get('weight_policy', 'unit'),
                            '--expected-weight-seed', str(dataset.get('weight_seed', 42))])
    elif dataset['family'] in TRAVERSAL_FAMILIES:
        # PageRank/WCC on a traversal fixture: no reference vector, certificate only.
        command.extend(['--ranking-validation', 'certificate'])
    return command + config.get('extra_cell_args', [])


def capture(command, timeout=60):
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        return dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        return dict(returncode=None, stdout='', stderr=repr(error))


def inspect_state(base, name):
    result = capture(base + ['inspect', name])
    if result['returncode'] != 0:
        return None
    item = json.loads(result['stdout'])[0]
    keys = ('NanoCpus', 'CpuPeriod', 'CpuQuota', 'CpusetCpus', 'Memory', 'MemorySwap', 'PidsLimit', 'Init', 'PidMode')
    return dict(id=item['Id'], image=item['Image'], state=item['State'],
                limits={key: item['HostConfig'].get(key) for key in keys})


def run_container(config, name, command, output, image, timeout, copy_paths):
    """Preserve diagnostics for failures; never leave a running cell behind."""
    output.mkdir(parents=True, exist_ok=False)
    base = docker_base(config)
    create = base + ['create'] + container_options(config, name, image) + command
    record = dict(started_utc=utc(), command=create, host_load_before=None,
                  outer_timeout=False, transport_errors=[], copied={})
    try:
        import os
        record['host_load_before'] = os.getloadavg()
    except (AttributeError, OSError):
        pass
    created = False
    try:
        result = capture(create)
        record['create'] = result
        if result['returncode'] != 0:
            record['transport_errors'].append('container creation failed')
            return record
        created = True
        with (output / 'container.log').open('w') as stream:
            try:
                completed = subprocess.run(base + ['start', '--attach', name], stdout=stream,
                    stderr=subprocess.STDOUT, timeout=timeout)
                record['attach_returncode'] = completed.returncode
            except subprocess.TimeoutExpired:
                record['outer_timeout'] = True
                record['kill'] = capture(base + ['kill', name])
    except BaseException as error:
        record['transport_errors'].append(repr(error))
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            record['operator_interrupted'] = True
    finally:
        if created:
            try:
                state = inspect_state(base, name)
                if state and state['state']['Running']:
                    record['forced_cleanup_kill'] = capture(base + ['kill', name])
                record['inspect'] = inspect_state(base, name)
                if record['inspect'] is None:
                    record['transport_errors'].append('container inspection failed')
                for label, source in copy_paths.items():
                    destination = output / label
                    destination.mkdir()
                    result = capture(base + ['cp', name + ':' + source + '/.', str(destination)], timeout=180)
                    record['copied'][label] = result
                    if result['returncode'] != 0:
                        record['transport_errors'].append(f'required artifact copy failed: {label}')
            except BaseException as error:
                record['transport_errors'].append(repr(error))
            finally:
                record['remove'] = capture(base + ['rm', '--force', name])
                if record['remove']['returncode'] != 0:
                    record['transport_errors'].append('container removal failed')
        record['finished_utc'] = utc()
        write_json(output / 'orchestration.json', record)
    return record


def classify(record, receipt, expected_sha):
    state = (record.get('inspect') or {}).get('state', {})
    events = (receipt or {}).get('cgroup_after', {}).get('memory.events') or ''
    counters = dict(line.split() for line in events.splitlines() if len(line.split()) == 2)
    # A worker can be OOM-killed while the controller survives to write its
    # receipt; Docker's final process state alone does not cover that case.
    if state.get('OOMKilled') or int(counters.get('oom_kill', '0')) > 0:
        return 'oom'
    if record.get('outer_timeout'):
        return 'outer_timeout'
    if record.get('operator_interrupted'):
        return 'interrupted'
    if record['transport_errors']:
        return 'orchestration_error'
    if record.get('receipt_read_error'):
        return 'invalid_receipt'
    if receipt is None:
        return 'missing_receipt'
    if receipt.get('harness_source_sha') != expected_sha:
        return 'source_mismatch'
    if receipt.get('outcome') == 'passed' and record.get('attach_returncode') != 0:
        return 'exit_receipt_mismatch'
    return effective_outcome(receipt)


def preflight(config, output):
    base = docker_base(config)
    image = capture(base + ['image', 'inspect', config['image'], '--format', '{{.Id}}'])
    if image['returncode'] != 0:
        raise RuntimeError(image['stderr'])
    image = image['stdout'].strip()
    script = ('import pathlib,subprocess,sys; p=pathlib.Path(sys.argv[1]); '
              'assert subprocess.check_output(["git","-C",str(p),"rev-parse","HEAD"],text=True).strip()==sys.argv[2]; '
              'assert not subprocess.check_output(["git","-C",str(p),"status","--porcelain"],text=True).strip(); '
              'assert pathlib.Path(sys.argv[3]).is_file(); print("preflight passed")')
    command = ['-I', '-c', script, config['container_repo'], config['harness_source_sha'], config['container_sail_binary']]
    name = 'sail-' + config['run_id'] + '-preflight'
    result = run_container(config, name, command, output / ('preflight-' + str(time.time_ns())), image, 120, {})
    if result.get('attach_returncode') != 0 or result['transport_errors']:
        raise RuntimeError('preflight failed; see preserved orchestration record')
    return image


def dataset_command(config, name):
    options = config['datasets'][name]
    family = options['family']
    script = {'traversal': 'traversal_fixture.py', 'graph500': 'graph500_fixture.py',
              'edge-list-traversal': 'imported_traversal_fixture.py',
              'snap-edge-list': 'imported_snap_fixture.py'}.get(family, 'graph_fixtures.py')
    dataset_path = str(PurePosixPath(config['container_root']) / 'datasets' / name)
    command = [str(PurePosixPath(config['container_repo']) / 'examples/extensions/benchmarks' / script),
               '--output', dataset_path]
    for key, value in options.items():
        if family in TRAVERSAL_FAMILIES and key == 'family':
            continue
        if family == 'graph500' and key in ('vertices', 'validation', 'certificate_max_rounds'):
            continue
        if family in ('edge-list-traversal', 'snap-edge-list') and key in ('validation', 'certificate_max_rounds'):
            continue
        if family == 'snap-edge-list' and key == 'expected_edge_sha256':
            continue
        if family in TRAVERSAL_FAMILIES and key == 'directed':
            command.append('--directed' if value else '--no-directed')
            continue
        command.extend(['--' + key.replace('_', '-'), str(value)])
    if family in ('graph500', 'edge-list-traversal') and options['validation'] == 'reference':
        command.append('--reference')
    if family not in TRAVERSAL_FAMILIES:
        for key in ('tolerance', 'damping'):
            command.extend(['--' + key, str(config['defaults'][key])])
    return command


def prepare_datasets(config, output, image):
    for name in config['datasets']:
        dataset_path = str(PurePosixPath(config['container_root']) / 'datasets' / name)
        command = dataset_command(config, name)
        result = run_container(config, 'sail-' + config['run_id'] + '-prepare-' + name, command,
            output / 'datasets' / name, image, config['limits']['outer_timeout_seconds'], {'dataset': dataset_path})
        if result.get('attach_returncode') != 0 or result['transport_errors']:
            raise RuntimeError(f'dataset preparation failed: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--skip-prepare', action='store_true')
    parser.add_argument('--resume', action='store_true', help='skip recorded cells, including failures; requires --skip-prepare')
    parser.add_argument('--select', action='append', help='run only these exact cell IDs; order is still from the full plan')
    args = parser.parse_args()
    if args.resume and not args.skip_prepare:
        parser.error('--resume requires --skip-prepare; existing datasets must be retained')
    config = json.loads(args.config.read_text())
    cells = plan_cells(config)
    if args.select:
        unknown = set(args.select) - {cell['cell_id'] for cell in cells}
        if unknown:
            parser.error(f'unknown selected cells: {sorted(unknown)}')
        cells = [cell for cell in cells if cell['cell_id'] in args.select]
    fingerprint = configuration_fingerprint(config)
    plan = dict(configuration_sha256=fingerprint, configuration=config, cells=cells,
                randomized_order='Python random.Random(seed), shuffle independently within each suite/repetition')
    if args.dry_run:
        plan['commands'] = {cell['cell_id']: cell_command(config, cell) for cell in cells}
        plan['preparation_commands'] = {name: dataset_command(config, name) for name in config['datasets']}
        print(json.dumps(plan, indent=2))
        return 0
    output = Path(config['host_output'])
    output.mkdir(parents=True, exist_ok=True)
    config_record = output / 'configuration.json'
    if config_record.exists() and json.loads(config_record.read_text()) != config:
        parser.error('output directory already belongs to a different configuration')
    write_json(config_record, config)
    write_json(output / ('plan-' + str(time.time_ns()) + '.json'), plan)
    image = preflight(config, output)
    image_record = output / 'resolved-image.json'
    if image_record.exists() and json.loads(image_record.read_text())['image_sha256'] != image:
        parser.error('Docker image changed since this matrix started')
    write_json(image_record, dict(image_sha256=image))
    if not args.skip_prepare:
        prepare_datasets(config, output, image)
    if args.prepare_only:
        return 0
    results = []
    try:
        for cell in cells:
            cell_output = output / 'cells' / cell['cell_id']
            completed = cell_output / 'summary.json'
            if args.resume and completed.exists():
                result = json.loads(completed.read_text())
                if result['configuration_sha256'] != fingerprint:
                    raise RuntimeError('resume configuration differs from recorded cell')
                receipt_path = cell_output / 'artifacts/receipt.json'
                if result.get('outcome') == 'passed' and receipt_path.exists():
                    result = resumed_outcome(result, json.loads(receipt_path.read_text()), cell['expected_outcome'])
                results.append(result)
                continue
            record = run_container(config, 'sail-' + config['run_id'] + '-' + str(cell['sequence']),
                cell_command(config, cell), cell_output, image, config['limits']['outer_timeout_seconds'],
                {'artifacts': str(PurePosixPath(config['container_root']) / 'cells' / cell['cell_id'])})
            path = cell_output / 'artifacts/receipt.json'
            try:
                receipt = json.loads(path.read_text()) if path.exists() else None
            except (OSError, json.JSONDecodeError) as error:
                receipt = None
                record['receipt_read_error'] = repr(error)
                write_json(cell_output / 'orchestration.json', record)
            outcome = classify(record, receipt, config['harness_source_sha'])
            result = dict(**cell, outcome=outcome, configuration_sha256=fingerprint,
                          expected_outcome_observed=outcome == cell['expected_outcome'],
                          receipt_path=str(path) if path.exists() else None,
                          end_to_end_seconds=receipt.get('end_to_end_seconds') if receipt else None,
                          source=receipt.get('arguments', {}).get('source') if receipt else None,
                          source_degree=receipt.get('source_degree') if receipt else None,
                          reached=(receipt.get('correctness') or {}).get('reached') if receipt else None)
            write_json(completed, result)
            results.append(result)
            write_json(output / 'matrix-results.json', dict(recorded_utc=utc(), results=results,
                outcome_counts=dict(Counter(row['outcome'] for row in results))))
            print(json.dumps(result), flush=True)
            if record['transport_errors'] or record.get('operator_interrupted'):
                raise RuntimeError('orchestration/cleanup failed; stopped before launching another cell')
    finally:
        write_json(output / 'matrix-results.json', dict(recorded_utc=utc(), results=results,
            planned_cells=len(cells), completed_cells=len(results),
            outcome_counts=dict(Counter(row['outcome'] for row in results))))
    return 0 if all(row['expected_outcome_observed'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
