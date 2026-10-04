"""Fresh detached Linux build; prepare only, launch separately after active work.

Run inside the existing pinned gate image, with the target volume at /targets
and the script/bundle bind-mounted read-only. Example arguments:
  --sha FULL_INTEGRATION_SHA --bundle /work/integration.bundle
  --bundle-ref refs/heads/work/stream-integration --image-id sha256:IMAGE_DIGEST

The default seed is /targets/graph-nuts-ffcfbd569. It is only read. Targets are
copied without hard links into a fresh sibling directory. No existing run is
resumed, removed or overwritten. This is a build/unit-test gate, not a graph
benchmark, distributed qualification or performance measurement. Its release
host profile matches rebuild-gate3.py: opt 3, LTO true, one codegen unit, stripped.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

BASE_SHA = 'ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
BASE_HOST = 'sail-linux-x86_64-ffcfbd5690e3-release'
BASE_HOST_HASH = '516cb3e5aecd89e954edff7934be439e63f2257e08c5ba45f09219261a173226'
BASE_WHEEL = 'wheels/sail_nutmeg-0.1.0-cp312-cp312-manylinux_2_34_x86_64.whl'
BASE_WHEEL_HASH = 'aac460074cbdb5a4ac301de56c7028120d6b3fbeff123c66e2a1a8ca34a47f71'
GIB = 1 << 30


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def tree_snapshot(path):
    """Detect seed-target modifications without rereading all artifact bytes."""
    value, total, count = hashlib.sha256(), 0, 0
    for directory, folders, files in os.walk(path, followlinks=False):
        folders.sort()
        for name in sorted(folders + files):
            entry = Path(directory) / name
            stat = entry.lstat()
            if entry.is_symlink():
                link = Path(os.readlink(entry))
                if link.is_absolute() or not entry.resolve().is_relative_to(path.resolve()):
                    raise RuntimeError(f'seed target has a link that cannot be safely copied: {entry}')
            row = [str(entry.relative_to(path)), stat.st_mode, stat.st_size,
                   stat.st_mtime_ns, stat.st_ctime_ns,
                   os.readlink(entry) if entry.is_symlink() else None]
            value.update(json.dumps(row).encode())
            if entry.is_file() and not entry.is_symlink():
                total += stat.st_size
            count += 1
    return dict(metadata_sha256=value.hexdigest(), logical_bytes=total, entries=count)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--bundle-ref', required=True)
    parser.add_argument('--image-id', required=True, help='Pinned launch image ID, recorded as a caller claim')
    parser.add_argument('--bundle-sha256', help='Optional expected bundle digest, verified before fetch')
    parser.add_argument('--seed', type=Path, default=Path('/targets/graph-nuts-ffcfbd569'))
    parser.add_argument('--run', type=Path, help='Fresh direct child of /targets; defaults to SHA-derived name')
    parser.add_argument('--sedona', type=Path, default=Path('/targets/linux-gates/wheels/sail_sedona_extension-0.1.0-cp312-cp312-manylinux_2_34_x86_64.whl'))
    parser.add_argument('--jobs', type=int, default=16)
    parser.add_argument('--reserve-gib', type=int, default=12)
    parser.add_argument('--setuptools-version', default='75.1.0')
    parser.add_argument('--wheel-version', default='0.45.1')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.sha):
        parser.error('--sha must be the exact full lowercase commit ID')
    if not args.bundle_ref.startswith('refs/heads/') or args.jobs < 1 or args.reserve_gib < 8:
        parser.error('require a full heads ref, positive jobs and at least 8 GiB reserve')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('this script builds in the x86_64 Linux gate container')
    seed, bundle = args.seed.resolve(strict=True), args.bundle.resolve(strict=True)
    run = (args.run or Path('/targets') / ('sail-stream-' + args.sha[:12])).absolute()
    if run.exists() or run.is_symlink() or run.parent.resolve() != Path('/targets').resolve() or run == seed:
        parser.error('--run must be a nonexistent direct child of /targets, distinct from seed')
    source, venv, wheels = run / 'source', run / 'venv', run / 'wheels'
    native_target, host_target = run / 'target-native', run / 'target-host'
    protected = {seed / BASE_HOST: BASE_HOST_HASH, seed / BASE_WHEEL: BASE_WHEEL_HASH}
    for path, expected in protected.items():
        if digest(path) != expected:
            parser.error(f'gate3 seed artifact hash differs: {path}')
    if not args.sedona.is_file():
        parser.error('the pinned Sedona wheel is absent')
    bundle_hash = digest(bundle)
    if args.bundle_sha256 and bundle_hash != args.bundle_sha256:
        parser.error('bundle digest differs from --bundle-sha256')
    snapshots = {name: tree_snapshot(seed / name) for name in ('target-native', 'target-host')}
    if any(not snapshot['entries'] for snapshot in snapshots.values()):
        parser.error('both seed target directories must be populated')
    seed_bytes = sum(snapshot['logical_bytes'] for snapshot in snapshots.values())
    initial_free = shutil.disk_usage('/targets').free
    # Reserve for new build products/linking as well as a fresh venv/source.
    if initial_free < seed_bytes + (args.reserve_gib + 2) * GIB:
        parser.error(f'need copied targets ({seed_bytes} bytes) + reserve + 2 GiB; free={initial_free}')
    run.mkdir()
    receipt = dict(started_utc=utc(), outcome='running', source_sha=args.sha,
                   seed_sha=BASE_SHA, seed=str(seed), seed_targets=snapshots,
                   bundle=dict(path=str(bundle), sha256=bundle_hash, ref=args.bundle_ref),
                   launch_image_claim=args.image_id, platform=platform.uname()._asdict(),
                   script_sha256=digest(__file__), arguments=vars(args).copy(),
                   free_bytes_before=initial_free, steps=[],
                   scope='detached exact-source build and actual native unit/integration tests; no cluster qualification')
    receipt['arguments'] = {k: str(v) if isinstance(v, Path) else v for k, v in receipt['arguments'].items()}
    base_env = dict(os.environ)
    for key in list(base_env):
        if (key.startswith(('SAIL_', 'PYO3_', 'CARGO_PROFILE_')) or key in (
            'PYTHONHOME', 'PYTHONPATH', 'DYLD_LIBRARY_PATH', 'LD_LIBRARY_PATH',
            'CARGO_TARGET_DIR', 'CARGO_BUILD_TARGET', 'CARGO_BUILD_RUSTFLAGS',
            'CARGO_ENCODED_RUSTFLAGS', 'CARGO_ENCODED_RUSTDOCFLAGS',
            'RUSTFLAGS', 'RUSTDOCFLAGS', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER')):
            base_env.pop(key, None)
    base_env.update(PATH='/root/.cargo/bin:/usr/local/cargo/bin:' + base_env.get('PATH', ''),
                    PYTHONDONTWRITEBYTECODE='1', UV_LINK_MODE='copy',
                    RUSTUP_TOOLCHAIN='1.97.1', CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS=str(args.jobs))

    def save():
        (run / 'rebuild-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def build_environment(env):
        # Do not copy registry tokens or other inherited credentials to receipts.
        keys = ('CARGO_HOME', 'CARGO_TARGET_DIR', 'CARGO_INCREMENTAL', 'CARGO_BUILD_JOBS',
                'RUSTUP_TOOLCHAIN', 'PYO3_PYTHON', 'PYTHONHOME', 'PYTHONPATH', 'LD_LIBRARY_PATH')
        return {k: v for k, v in env.items() if k in keys or k.startswith('CARGO_PROFILE_')}

    def output(command, env=None, cwd=None):
        return subprocess.check_output(list(map(str, command)), env=env or base_env, cwd=cwd, text=True).strip()

    def git(*command, path=source):
        return output(['git', '-C', path, *command])

    def guard():
        if git('rev-parse', 'HEAD') != args.sha or git('status', '--porcelain'):
            raise RuntimeError('detached source changed during the gate')
        branch = subprocess.run(['git', '-C', str(source), 'symbolic-ref', '-q', 'HEAD'],
                                env=base_env, capture_output=True)
        if branch.returncode != 1:
            raise RuntimeError('gate source is not detached')

    def step(name, command, env=None, cwd=None):
        free = shutil.disk_usage('/targets').free
        if free < args.reserve_gib * GIB:
            raise RuntimeError(f'{name}: only {free} bytes free, below reserved headroom')
        record = dict(name=name, command=list(map(str, command)), started_utc=utc(), free_bytes_before=free)
        receipt['steps'].append(record)
        save()
        with (run / (name + '.log')).open('x') as log:
            result = subprocess.run(record['command'], env=env or base_env, cwd=cwd,
                                    stdout=log, stderr=subprocess.STDOUT)
        record.update(returncode=result.returncode, finished_utc=utc(),
                      free_bytes_after=shutil.disk_usage('/targets').free)
        save()
        print(name, result.returncode, flush=True)
        if result.returncode:
            raise RuntimeError(f'{name} failed; original log retained')

    detached = False
    seed_state = None
    save()
    try:
        seed_state = dict(head=git('rev-parse', 'HEAD', path=seed / 'source'),
                          status=git('status', '--porcelain', path=seed / 'source'))
        if seed_state['head'] != BASE_SHA:
            raise RuntimeError('seed source revision does not match gate3')
        receipt['seed_source_before'] = seed_state
        receipt['sedona'] = dict(path=str(args.sedona), sha256=digest(args.sedona))
        step('clone', ['git', 'clone', '--no-hardlinks', '--no-checkout', seed / 'source', source])
        step('bundle-verify', ['git', '-C', source, 'bundle', 'verify', bundle])
        step('fetch', ['git', '-C', source, 'fetch', '--no-tags', bundle, args.bundle_ref])
        if git('rev-parse', 'FETCH_HEAD') != args.sha:
            raise RuntimeError('bundle ref does not name the requested integration SHA')
        step('detach', ['git', '-C', source, 'checkout', '--detach', args.sha])
        detached = True
        guard()
        if not (source / 'crates/sail-execution/src/diagnostics.rs').is_file():
            raise RuntimeError('requested integration lacks stream diagnostics source')
        receipt['source_log'] = git('log', '--oneline', f'{BASE_SHA}..{args.sha}')
        receipt['locks'] = {str(p.relative_to(source)): digest(p) for p in (
            source / 'Cargo.lock', source / 'examples/extensions/argentea/Cargo.lock',
            source / 'examples/extensions/nutmeg/Cargo.lock',
            source / 'examples/extensions/vendor/nutmeg-graph/Cargo.lock',
            source / 'examples/extensions/requirements.lock')}
        step('venv', ['uv', 'venv', '--python', seed / 'venv/bin/python', venv])
        python = venv / 'bin/python'
        step('dependencies', ['uv', 'pip', 'sync', '--python', python, source / 'examples/extensions/requirements.lock'])
        config = json.loads(output([python, '-I', '-c', 'import sys,sysconfig,json;print(json.dumps(dict(base=sys.base_prefix,lib=sysconfig.get_config_var("LIBDIR"),purelib=sysconfig.get_path("purelib"),version=sys.version)))']))
        receipt.update(python=config, rust=output(['rustc', '--version']), uv=output(['uv', '--version']))
        receipt['cgroup'] = {name: (Path('/sys/fs/cgroup') / name).read_text().strip()
                             for name in ('cpu.max', 'memory.max', 'memory.swap.max')}
        step('seed-native-target', ['cp', '-a', '--reflink=auto', seed / 'target-native', native_target])
        native_env = dict(base_env, CARGO_TARGET_DIR=str(native_target), CARGO_PROFILE_DEV_DEBUG='0',
                          CARGO_PROFILE_TEST_DEBUG='0', PYO3_PYTHON=str(python),
                          PYTHONHOME=config['base'], PYTHONPATH=config['purelib'], LD_LIBRARY_PATH=config['lib'])
        receipt['native_environment'] = build_environment(native_env)
        core = source / 'examples/extensions/vendor/nutmeg-graph/Cargo.toml'
        argentea = source / 'examples/extensions/argentea/Cargo.toml'
        native = source / 'examples/extensions/nutmeg/Cargo.toml'
        # Execute release tests: no --no-run and no --skip argentea::.
        for name, manifest in [('nutmeg-core', core), ('argentea-core', argentea), ('native-adapter', native)]:
            command = ['cargo', 'test', '--locked', '--release', '--manifest-path', manifest]
            if name == 'native-adapter':
                command.append('--lib')
            step(name + '-tests', command, native_env)
            log = (run / (name + '-tests.log')).read_text()
            if not re.search(r'test result: ok\. [1-9][0-9]* passed', log):
                raise RuntimeError(f'{name}: test command ran no passing tests')
            if name == 'native-adapter' and not re.search(r'^test argentea::.* \.\.\. ok$', log, re.M):
                raise RuntimeError('native adapter gate did not execute an Argentea test')
            guard()
            lint = ['cargo', 'clippy', '--locked', '--manifest-path', manifest, '--all-targets', '--', '-D', 'warnings']
            if name == 'native-adapter':
                lint += ['-A', 'clippy::large_enum_variant']
            step(name + '-clippy', lint, native_env)
        receipt['clippy_exception'] = 'native adapter only: inherited gate3 clippy::large_enum_variant flag; no other lint exceptions'
        wheels.mkdir()
        step('wheel', [python, '-m', 'maturin', 'build', '--locked', '--manifest-path', native,
                       '--release', '--interpreter', python, '--out', wheels], native_env)
        matches = list(wheels.glob('sail_nutmeg-*.whl'))
        if len(matches) != 1:
            raise RuntimeError('expected exactly one newly built native wheel')
        wheel = matches[0]
        receipt['native_wheel'] = dict(path=str(wheel), sha256=digest(wheel), bytes=wheel.stat().st_size)
        step('install-native', ['uv', 'pip', 'install', '--python', python, '--no-deps', wheel, args.sedona])
        # Pin the Pecan build tools; its pyproject lower bound is not a lock.
        step('pecan-build-tools', ['uv', 'pip', 'install', '--python', python, '--no-deps',
                                  'setuptools==' + args.setuptools_version, 'wheel==' + args.wheel_version])
        package = run / 'pecan-package'
        shutil.copytree(source / 'examples/extensions/graph-algorithms', package)
        step('install-pecan', ['uv', 'pip', 'install', '--python', python, '--no-deps', '--no-build-isolation', package])
        receipt['packages'] = output(['uv', 'pip', 'freeze', '--python', python])
        receipt['entry_points'] = json.loads(output([python, '-I', '-c', 'import importlib.metadata as m,json;print(json.dumps([dict(name=e.name,value=e.value,distribution=e.dist.name) for e in m.entry_points(group="pysail.extensions")]))']))
        step('seed-host-target', ['cp', '-a', '--reflink=auto', seed / 'target-host', host_target])
        host_env = dict(native_env, CARGO_TARGET_DIR=str(host_target), CARGO_PROFILE_RELEASE_DEBUG='0',
                        CARGO_PROFILE_RELEASE_OPT_LEVEL='3', CARGO_PROFILE_RELEASE_LTO='true',
                        CARGO_PROFILE_RELEASE_CODEGEN_UNITS='1', CARGO_PROFILE_RELEASE_STRIP='true')
        receipt['host_environment'] = build_environment(host_env)
        step('host-release-build', ['cargo', 'build', '--locked', '--release', '-p', 'sail-cli'], host_env, source)
        guard()
        artifact = run / f'sail-linux-x86_64-{args.sha[:12]}-release'
        shutil.copy2(host_target / 'release/sail', artifact)
        # A new host, not just a new wheel, must contain the diagnostic hook.
        with artifact.open('rb') as stream:
            import mmap
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as binary:
                if binary.find(b'execution_failure pid=') < 0:
                    raise RuntimeError('built host lacks the execution_failure diagnostic marker')
        receipt['host'] = dict(path=str(artifact), sha256=digest(artifact), bytes=artifact.stat().st_size,
                               version=output([artifact, '--version'], host_env))
        receipt['outcome'] = 'passed'
    except BaseException as error:
        receipt.update(outcome='failed', error=repr(error))
    finally:
        try:
            if detached:
                guard()
            for path, expected in protected.items():
                if digest(path) != expected:
                    raise RuntimeError(f'protected seed artifact changed: {path}')
            if seed_state != dict(head=git('rev-parse', 'HEAD', path=seed / 'source'),
                                  status=git('status', '--porcelain', path=seed / 'source')):
                raise RuntimeError('seed source changed')
            for name, snapshot in snapshots.items():
                if tree_snapshot(seed / name) != snapshot:
                    raise RuntimeError(f'original seed target changed: {name}')
            receipt['seed_unchanged'] = True
        except BaseException as error:
            receipt.update(outcome='failed', guard_error=repr(error), seed_unchanged=False)
        receipt.update(finished_utc=utc(), free_bytes_after=shutil.disk_usage('/targets').free)
        save()
    print(f"INTEGRATION_BUILD {receipt['outcome'].upper()} {args.sha} receipt={run / 'rebuild-receipt.json'}", flush=True)
    return 0 if receipt['outcome'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
