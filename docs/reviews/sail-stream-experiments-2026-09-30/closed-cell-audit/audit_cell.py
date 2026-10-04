#!/usr/bin/env python3
"""Audit local closed-cell evidence, without executing commands or reading Parquet."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHA = re.compile(r'[0-9a-f]{64}\Z')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_info(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1 << 20):
            h.update(block)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def read_json(path):
    def reject(value):
        raise ValueError('nonfinite JSON: ' + value)
    def object_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(), parse_constant=reject, object_pairs_hook=object_pairs)


def safe_name(name):
    p = PurePosixPath(name)
    return isinstance(name, str) and bool(name) and not p.is_absolute() and '..' not in p.parts and str(p) == name


class Audit:
    def __init__(self, root):
        self.root, self.errors, self.missing, self.files = root, [], [], {}
        self.notes = []

    def check(self, predicate, message):
        if not predicate:
            self.errors.append(message)

    def load(self, path):
        try:
            self.check(not path.is_symlink(), 'symlink input: ' + str(path))
            raw = path.read_bytes()
            self.files[str(path)] = {'bytes': len(raw), 'sha256': digest(raw)}
            value = read_json(path)
            if not isinstance(value, dict):
                raise ValueError('expected JSON object')
            return value
        except FileNotFoundError:
            self.missing.append('missing input: ' + str(path))
        except (OSError, ValueError) as error:
            self.errors.append('invalid input: ' + str(path) + ': ' + str(error))
        return None

    def section(self, label, operation):
        try:
            operation()
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, StopIteration, OSError, tarfile.TarError) as error:
            self.errors.append(label + ': ' + type(error).__name__ + ': ' + str(error))


def audit_archive(a, cell, collection):
    archive = cell / 'diagnostics.tar'
    if not archive.exists():
        a.missing.append('missing input: ' + str(archive))
        return
    info = file_info(archive)
    a.files[str(archive)] = info
    a.check(not archive.is_symlink(), 'symlink archive')
    a.check(collection['returncode'] == 0 and type(collection['returncode']) is int, 'collection did not exit zero')
    a.check(collection['stderr'] == '', 'collection stderr is nonempty')
    a.check(collection['bytes'] == info['bytes'] and type(collection['bytes']) is int, 'archive size differs from collection')
    a.check(collection['sha256'] == info['sha256'], 'archive hash differs from collection')
    names = []
    with tarfile.open(archive) as tar:
        for member in tar:
            if not member.isfile() or not safe_name(member.name) or '/' in member.name:
                a.errors.append('unsafe/nonflat archive member: ' + member.name)
                continue
            if member.name in names:
                a.errors.append('duplicate archive member: ' + member.name)
                continue
            names.append(member.name)
            path = cell / 'diagnostics' / member.name
            if not path.exists():
                a.missing.append('missing extracted member: ' + member.name)
                continue
            a.check(not path.is_symlink(), 'symlink extracted member: ' + member.name)
            with tar.extractfile(member) as stream:
                h = hashlib.sha256()
                while block := stream.read(1 << 20):
                    h.update(block)
            info = file_info(path)
            a.files[str(path)] = info
            a.check(info['bytes'] == member.size and info['sha256'] == h.hexdigest(), 'archive/member mismatch: ' + member.name)
    present = {p.name for p in (cell/'diagnostics').iterdir()}
    a.check(not (present - set(names)), 'extracted inventory has members absent from archive')
    for name in {'receipt.json', 'server.log', 'server-settings.json', 'memory-samples.jsonl'} - set(names):
        a.missing.append('required diagnostic member absent: ' + name)


def audit_resources(a, config, receipt, orchestration):
    limits = config['limits']; observed = orchestration['inspect']['limits']
    memory = limits['memory_gib'] * (1 << 30)
    for key, expected in {'Memory': memory, 'MemorySwap': memory, 'NanoCpus': limits['cpus'] * 10**9,
                          'CpusetCpus': limits['cpuset_cpus'], 'PidsLimit': 1024, 'Init': True}.items():
        a.check(type(observed[key]) is type(expected) and observed[key] == expected, 'Docker resource mismatch: ' + key)
    for name in ['cgroup_before', 'cgroup_execution_before', 'cgroup_after']:
        if name not in receipt:
            a.missing.append('missing cgroup evidence: ' + name)
    for name in ['cgroup_before', 'cgroup_execution_before', 'cgroup_execution_after', 'cgroup_after']:
        if name not in receipt:
            continue
        cg = receipt[name]
        a.check(cg['memory.max'] == str(memory) and cg['memory.swap.max'] == '0', name + ': memory limits differ')
        quota, period = map(int, cg['cpu.max'].split())
        a.check(period > 0 and Fraction(quota, period) == Fraction(str(limits['cpus'])), name + ': CPU quota differs')
        a.check(cg['cpuset.cpus.effective'] == limits['cpuset_cpus'], name + ': cpuset differs')
        events = dict(line.split() for line in cg['memory.events'].splitlines())
        a.check(all(int(events[k]) >= 0 for k in ('oom', 'oom_kill')), name + ': invalid OOM counters')
    defaults = config['defaults']
    for key, expected in {'sail_pool_per_process_bytes': defaults['sail_pool_bytes'],
                          'prepaid_native_quota_bytes': defaults['native_quota'],
                          'worker_task_slots_per_worker': defaults['worker_task_slots'],
                          'worker_task_slots_total': 2 * defaults['worker_task_slots']}.items():
        a.check(receipt[key] == expected and type(receipt[key]) is int, 'runtime budget mismatch: ' + key)


def audit_identity(a, config, plan, receipt, orchestration, profile):
    for key in ['runtime_source_sha', 'harness_source_sha', 'native_source_sha']:
        a.check(receipt[key] == config[key], 'source identity mismatch: ' + key)
    a.check(receipt['binary_sha256'] == profile['binary_sha256'], 'binary hash differs from pinned artifact')
    a.check(receipt['source_dirty'] == '', 'controller source was dirty or missing clean evidence')
    a.check(canonical(receipt['native_package_identity']) == profile['native_identity_canonical_sha256'], 'native package inventory differs')
    a.check(orchestration['inspect']['image'] == config['image'], 'image differs from pinned configuration')
    a.check(len(plan['cells']) == 1, 'expected one planned cell')
    cell = plan['cells'][0]; args = receipt['arguments']; command = orchestration['command']
    a.check(len(config['suites']) == 1, 'expected one configured suite')
    suite = config['suites'][0]
    for field, plural in [('engine', 'engines'), ('algorithm', 'algorithms'), ('variant', 'variants'), ('dataset', 'datasets')]:
        a.check(suite[plural] == [cell[field]], 'configured suite differs: ' + field)
    a.check(cell['suite'] == suite['name'] and cell['mode'] == suite['mode'], 'configured suite identity differs')
    a.check(cell['repeat'] == 1 and suite['repetitions'] == 1, 'expected one repetition')
    expected_id = '-'.join([suite['name'], 'r1', cell['dataset'], cell['engine'], cell['algorithm'], cell['variant']])
    a.check(cell['cell_id'] == expected_id, 'planned cell identity differs')
    a.check(command[-len(plan['command']):] == plan['command'], 'executed cell command differs from plan')
    a.check(plan['command'][0] == config['container_repo'] + '/examples/extensions/benchmarks/graph_cell.py', 'cell entrypoint differs')
    a.check(command[command.index('--entrypoint') + 1] == config['container_python'], 'Python entrypoint differs')
    env = [command[i+1] for i, value in enumerate(command) if value == '--env']
    expected_env = ['PYTHONUNBUFFERED=1'] + [k + '=' + v for k, v in config['environment'].items()]
    a.check(sorted(env) == sorted(expected_env), 'environment differs from config')
    a.check(command[command.index('--workdir')+1] == config['container_repo'], 'controller workdir differs')
    a.check(command[command.index('--mount')+1] == 'type=volume,source=' + config['target_volume'] + ',target=/targets', 'target volume differs')
    for key in ['engine', 'algorithm', 'variant', 'mode', 'repeat', 'max_iterations', 'stage_order']:
        a.check(args[key] == cell[key] and type(args[key]) is type(cell[key]), 'planned argument differs: ' + key)
    for key, value in config['defaults'].items():
        if key != 'max_iterations':
            a.check(args[key] == value and type(args[key]) is type(value), 'default argument differs: ' + key)
    a.check(args['sail_binary'] == config['container_sail_binary'], 'runtime path differs')
    for key in ['runtime_source_sha', 'native_source_sha']:
        a.check(args[key] == config[key], 'argument source differs: ' + key)
    ds = config['datasets'][cell['dataset']]
    for key in ['source', 'directed']:
        a.check(args[key] == ds[key] and type(args[key]) is type(ds[key]), 'dataset argument differs: ' + key)
    a.check(args['traversal_validation'] == ds.get('validation', 'reference'), 'validation policy differs')
    a.check(args['certificate_max_rounds'] == ds.get('certificate_max_rounds', 10000), 'certificate budget differs')
    a.check(args['dataset'] == profile['resolved_dataset_path'], 'resolved dataset path differs from pinned identity')
    a.check(args['output'] == config['container_root'] + '/cells/' + cell['cell_id'], 'output namespace differs')
    a.check(args['record_plans'] is True and args['http2_keepalive_timeout'] == 120, 'diagnostic arguments differ')
    a.check(args['allow_dirty'] is False and args['allow_unisolated'] is False, 'source/isolation bypass enabled')
    # Bind every explicit producer argument to the actual argv, not only to another receipt.
    seen = set(); tokens = iter(plan['command'][1:])
    for token in tokens:
        a.check(token.startswith('--'), 'unexpected positional producer argument')
        name = token[2:].replace('-', '_')
        value = None
        if name == 'no_directed':
            name, value = 'directed', False
        elif name in ('directed', 'record_plans', 'allow_dirty', 'allow_unisolated'):
            value = True
        else:
            text = next(tokens)
            value = type(args[name])(text)
        a.check(name not in seen, 'duplicate producer argument: ' + name)
        seen.add(name)
        if name == 'dataset':
            a.check(value == config['container_root'] + '/datasets/' + cell['dataset'], 'planned dataset path differs')
        else:
            a.check(value == args[name] and type(value) is type(args[name]), 'argv/receipt mismatch: ' + name)


def audit_dataset(a, config, plan, receipt, profile):
    dataset = receipt['dataset']; opts = config['datasets'][plan['cells'][0]['dataset']]
    a.check(canonical(dataset) == profile['dataset_canonical_sha256'], 'embedded dataset manifest differs from pinned baseline')
    a.check(dataset['family'] == opts['family'], 'dataset family differs')
    a.check(type(dataset['counts']['vertices']) is int and dataset['counts']['vertices'] == opts['vertices'], 'vertex count differs')
    files = dataset['files']
    a.check(any(x.startswith('vertices.parquet') for x in files) and any(x.startswith('edges.parquet') for x in files), 'vertex/edge inventory missing')
    for name, record in files.items():
        a.check(safe_name(name) and SHA.fullmatch(record['sha256']) is not None and type(record['bytes']) is int and record['bytes'] >= 0, 'invalid data inventory: ' + name)
    if opts['family'] == 'graph500':
        a.check(dataset['canonical']['edges']['sha256'] == opts['expected_edge_sha256'], 'canonical edge identity differs')
    a.notes.append('Dataset checks compare the producer-embedded manifest to pinned local evidence; dataset/Parquet bytes were not read or recomputed.')


def audit(cell, profile, root=ROOT):
    cell = Path(cell); a = Audit(root)
    observed = {}; known = {}
    for item in profile['evidence_pins']:
        path = root / item['path']; data = a.load(path)
        if data is not None:
            a.check(a.files[str(path)]['sha256'] == item['sha256'], 'pinned evidence changed: ' + item['path'])
    config = a.load(root / profile['config_path'])
    local = {name: a.load(cell/name) for name in ['configuration.json', 'plan.json', 'result.json', 'cell/orchestration.json', 'collection.json', 'diagnostics/receipt.json', 'diagnostics/server-settings.json', 'host-before.json']}
    receipt, orchestration = local['diagnostics/receipt.json'], local['cell/orchestration.json']
    if config is not None and local['configuration.json'] is not None:
        a.check(config == local['configuration.json'], 'collected configuration differs from pinned configuration')
    if local['collection.json'] is not None:
        a.section('archive', lambda: audit_archive(a, cell, local['collection.json']))
    if all(x is not None for x in [config, local['plan.json'], receipt, orchestration]):
        a.section('identity', lambda: audit_identity(a, config, local['plan.json'], receipt, orchestration, profile))
        a.section('resources', lambda: audit_resources(a, config, receipt, orchestration))
        a.section('dataset', lambda: audit_dataset(a, config, local['plan.json'], receipt, profile))
    settings = local['diagnostics/server-settings.json']
    if config is not None and settings is not None:
        a.section('logger', lambda: a.check(settings['rust_log'] == config['environment']['SAIL_BENCHMARK_RUST_LOG'], 'recorded logger differs'))
    def record_orchestration():
        state = orchestration['inspect']['state']
        a.check(type(state['Running']) is bool and type(state['OOMKilled']) is bool and type(state['ExitCode']) is int, 'invalid Docker state types')
        a.check(type(orchestration['outer_timeout']) is bool and isinstance(orchestration['transport_errors'], list), 'invalid orchestration outcome types')
        observed.update(docker_state=state, outer_timeout=orchestration['outer_timeout'], attach_returncode=orchestration['attach_returncode'], transport_errors=orchestration['transport_errors'])
        if state['Running'] is not False or not orchestration.get('finished_utc'):
            a.missing.append('container not proven closed')
        else:
            datetime.fromisoformat(orchestration['finished_utc'])
    if orchestration is not None:
        a.section('orchestration closure', record_orchestration)
    if receipt is not None:
        observed.update(receipt_outcome=receipt.get('outcome'), correctness=receipt.get('correctness'), error=receipt.get('error'), cleanup_errors=receipt.get('cleanup_errors'), cgroup_after=receipt.get('cgroup_after'), producer_started_utc=receipt.get('started_utc'), producer_finished_utc=receipt.get('finished_utc'))
        if not receipt.get('finished_utc'):
            a.missing.append('receipt has no finish marker')
        else:
            a.section('receipt closure', lambda: datetime.fromisoformat(receipt['finished_utc']))
        if local['collection.json'] is not None:
            a.section('collection namespace', lambda: a.check(local['collection.json']['full_artifact_path'] == receipt['arguments']['output'], 'collection namespace differs'))
    result = local['result.json']
    if result is not None:
        observed['runner_outcome'] = result.get('outcome')
        if receipt is not None:
            a.check(result.get('receipt_outcome') == receipt.get('outcome'), 'runner copied receipt outcome differs')
        if local['plan.json'] is not None:
            a.section('result identity', lambda: a.check(result['cell'] == local['plan.json']['cells'][0], 'runner cell differs from plan'))
    host = local['host-before.json']
    if host is not None and 'redaction' in host:
        known['host_before_redaction'] = host['redaction']
        known['published_host_before_sha256'] = a.files[str(cell/'host-before.json')]['sha256']
        a.notes.append('Host snapshot is explicitly redacted; its private original hash is provenance, not an equality target. It is separate from the diagnostic archive.')
    # Recheck every read artifact after the complete audit; active/mutating inputs cannot pass.
    for path, original in a.files.items():
        p = Path(path)
        try:
            a.check(not p.is_symlink() and file_info(p) == original, 'input changed during audit: ' + path)
        except OSError:
            a.missing.append('input disappeared during audit: ' + path)
    return {'recorded_utc': datetime.now(timezone.utc).isoformat(), 'cell_directory': str(cell.resolve()), 'expectations_canonical_sha256': canonical(profile), 'integrity_status': 'integrity_error' if a.errors else ('inconclusive' if a.missing else 'integrity_verified'), 'errors': a.errors, 'inconclusive_reasons': a.missing, 'recorded_outcomes': observed, 'correctness_verification': 'not_performed', 'known_transformations': known, 'notes': a.notes, 'files': a.files, 'scope': 'Local collected-byte and recorded-identity/resource agreement only. No remote access, binary execution, source rebuild, dataset/result Parquet recomputation, independent certificate validation, causal diagnosis or performance qualification. Recorded runner and receipt outcomes remain separate.', 'helper_sha256': digest(Path(__file__).read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--cell-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    policy = HERE/'profiles.json'
    profile_before = file_info(policy)
    profiles = read_json(policy)
    if args.case not in profiles['cases']:
        parser.error('unknown pinned case: ' + args.case)
    report = audit(args.cell_dir, profiles['cases'][args.case])
    report.update(case=args.case, profiles_file={'path': str(policy), **profile_before})
    if file_info(policy) != profile_before:
        report['errors'].append('profiles changed during audit')
        report['integrity_status'] = 'integrity_error'
    encoded = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if args.output:
        if args.cell_dir.resolve() == args.output.resolve() or args.cell_dir.resolve() in args.output.resolve().parents:
            parser.error('write the audit outside the collected cell directory')
        with args.output.open('x') as stream:
            stream.write(encoded)
    else:
        print(encoded, end='')
    return {'integrity_verified': 0, 'inconclusive': 2, 'integrity_error': 1}[report['integrity_status']]


if __name__ == '__main__':
    raise SystemExit(main())
