"""Prepare new local configs and dry plans only; never invoke Docker or SSH."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from run_host_pair import digest, normalized, sha

REMOTE = '/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930'
CONTROLLER = '3a9028057c6c6c5034492845926fc4bc18f9626f'
HOSTS = {
    'A': dict(name='host289', source='2894a962076d3cc404dd72ec736ebeb9239901f6',
        binary='/targets/sail-stream-2894a962076d/sail-linux-x86_64-2894a962076d-release',
        sha256='40a78182a420152e8e3651f9cdb38a4196eaf8bc7aead092d10e258a17ac3497'),
    'B': dict(name='host561', source='56194b170155301ba91077f0ba3df31fe2c78b6b',
        binary='/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release',
        sha256='5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'),
}


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness-source', type=Path, required=True)
    parser.add_argument('--namespace', default='pair16k-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
    args = parser.parse_args()
    assert re.fullmatch(r'pair16k-[0-9]{14}', args.namespace)
    root = Path(__file__).resolve().parent
    experiments = root.parent
    source = args.harness_source.resolve()
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == CONTROLLER
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
    harness = source / 'examples/extensions/benchmarks'
    sys.path.insert(0, str(harness))
    import run_matrix as matrix
    baseline = experiments / 'worker-smoke-instrumented289-cpu16-23.json'
    receipt_path = experiments / 'worker-smoke-instrumented289-cpu16-23/diagnostics/receipt.json'
    template = json.loads(baseline.read_text())
    receipt = json.loads(receipt_path.read_text())
    assert receipt['outcome'] == 'passed'
    scripts = {name: sha(experiments / name) for name in ('run_focused_safe.py', 'preflight_cell.py')}
    scripts['run_host_pair.py'] = sha(root / 'run_host_pair.py')
    resources = dict(limits=template['limits'], defaults=template['defaults'],
        environment=template['environment'], extra_cell_args=template['extra_cell_args'],
        mode='process-cluster', worker_initial_count=2, worker_max_count=2,
        worker_count_source='pinned runtime.py server() environment',
        pool_scope='greedy 3 GiB configured per Sail process; container hard cap 12 GiB',
        pid_limit=1024, image=template['image'], cpuset_scope='same VM logical CPUs 16-23')
    configs, runs, plans = [], [], []
    for order, (phase, host) in enumerate([('warmup','A'), ('warmup','B'),
            ('measurement','A'), ('measurement','B'), ('measurement','B'), ('measurement','A')], 1):
        config = json.loads(json.dumps(template))
        run_id = f'{args.namespace}-{order:02d}-{host.lower()}'
        config.update(run_id=run_id, host_output=f'{REMOTE}/{args.namespace}/cells/{run_id}',
            container_sail_binary=HOSTS[host]['binary'], runtime_source_sha=HOSTS[host]['source'],
            note='Prepared paired host control on a shared Morrobay VM. Original controller/native and existing weighted16k bytes; independent heap-Dijkstra and parent checks. All outcomes retained. Fresh processes per cell; no cache flush. Timing scope is descriptive shared-host ratios only, not absolute performance. No bootstrap or dataset regeneration.')
        config['suites'][0]['name'] = run_id
        matrix.validate_config(config)
        cells = matrix.plan_cells(config)
        assert len(cells) == 1
        cell = cells[0]
        command = matrix.cell_command(config, cell)
        filename = run_id + '.json'
        write_new(root / filename, config)
        configs.append(config)
        runs.append(dict(order=order, phase=phase, host=host, configuration=filename,
            configuration_sha256=sha(root / filename),
            configuration_fingerprint=matrix.configuration_fingerprint(config),
            binary_sha256=HOSTS[host]['sha256'], cell_id=cell['cell_id'],
            cell_output=str(Path(config['container_root']) / 'cells' / cell['cell_id'])))
        plans.append(dict(order=order, phase=phase, host=host, cell=cell, command=command,
            docker_create=matrix.docker_base(config) + ['create'] + matrix.container_options(
                config, 'sail-' + run_id + '-1', config['image']) + command))
    common = {digest(normalized(config)) for config in configs}
    assert len(common) == 1
    plan = dict(schema=1, prepared_utc=datetime.now(timezone.utc).isoformat(),
        namespace=args.namespace, remote_root=REMOTE,
        scope='preparation only; execution requires a separate operator scheduling authorization',
        order='warmup A, warmup B, measured A B B A', hosts=HOSTS,
        runtime_boundary='Only host binary/source and unique output/run/suite names differ. Controller and its Pecan Python, installed original ffcf native/Python, dataset bytes, resource caps and protocol remain pinned.',
        cache_policy='No OS/filesystem cache flush; one unmeasured fresh-process warmup per host, then four fresh-process measurements. Retained staging is not reused as an input.',
        exclusions='Previous smokes excluded; warmups never used as measured samples. Failures, invalid identities, missing metrics and concurrent containers prevent ratio publication, with raw cells retained.',
        scheduling='Serial cells, idle Docker admission at each start; sampled concurrent containers invalidate ratio. No host-wide lock; no proof of dedicated hardware. All ratios labeled shared-host.',
        minimum_free_bytes=12 << 30,
        disk_scope='12 GiB free admission per cell; an observation, not a proven peak bound. No deletion or dataset generation.',
        runner_wall_timeout_seconds=2400,
        measurement_scopes=dict(timer='receipt.end_to_end_seconds: traversal execution through final Parquet write, after lazy input DataFrames are constructed; excludes server startup, independent correctness validation and cleanup (pinned traversal_cell.py:27-97)',
            memory='sampled container-process PSS/RSS phase execute; distinct from cgroup total memory counters',
            steal='full-trial, whole Linux VM /proc/stat delta; not the execution timer interval, container or assigned cpuset (pinned graph_cell.py:558-559)',
            ratios='shared-host descriptive ratios only; original smoke times excluded; no absolute performance claim'),
        deadline_scope='Per runner wall deadline 2400s, up to 240s graceful diagnostic cleanup, then own process-group/container cleanup. Unknown leftover containers stop later admission; no retry.',
        common_configuration_sha256=common.pop(), resource_fingerprint=digest(resources),
        resources=resources, scripts=scripts,
        harness_files_sha256={p.name: sha(p) for p in sorted(harness.glob('*.py'))},
        baseline_configuration_sha256=sha(baseline), baseline_receipt_sha256=sha(receipt_path),
        expected_arguments=receipt['arguments'], expected_dataset=receipt['dataset'],
        expected_native_package_identity=receipt['native_package_identity'],
        dataset_manifest_sha256='6d71d459df71e2a0de23d34c80c5faff6d40829cfa59c85c5f6cef16ae203134',
        runs=runs)
    path = root / (args.namespace + '-plan.json')
    write_new(path, plan)
    write_new(root / (args.namespace + '-dry-plans.json'), dict(
        scope='pure command construction; no Docker, graph or remote work', plans=plans,
        configuration_parity_passed=True,
        allowed_differences=['run_id', 'host_output', 'runtime_source_sha', 'container_sail_binary', 'suites[0].name'],
        common_configuration_sha256=plan['common_configuration_sha256'],
        resource_fingerprint=plan['resource_fingerprint'], plan_sha256=sha(path)))
    print(json.dumps(dict(plan=str(path), plan_sha256=sha(path), runs=len(runs),
                         resource_fingerprint=plan['resource_fingerprint']), indent=2))


if __name__ == '__main__':
    main()
