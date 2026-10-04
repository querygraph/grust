"""Build only a fresh detached Sail host; reuse a proven identical native surface.

Run in the pinned x86_64 Linux gate image with /targets and read-only /work.
The completed prior build supplies a copied host cache and an unchanged venv.
No native tests or wheel builds are repeated: native source identity, artifacts,
and the prior passing receipt are checked and recorded explicitly.
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

GIB = 1 << 30


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def tree_snapshot(path, copying=False):
    value, total, count = hashlib.sha256(), 0, 0
    for directory, folders, files in os.walk(path, followlinks=False):
        folders.sort()
        for name in sorted(folders + files):
            entry = Path(directory) / name
            stat = entry.lstat()
            if copying and entry.is_symlink():
                link = Path(os.readlink(entry))
                if link.is_absolute() or not entry.resolve().is_relative_to(path.resolve()):
                    raise RuntimeError(f'cache link cannot be safely copied: {entry}')
            value.update(json.dumps([str(entry.relative_to(path)), stat.st_mode, stat.st_size,
                                     stat.st_mtime_ns, stat.st_ctime_ns,
                                     os.readlink(entry) if entry.is_symlink() else None]).encode())
            if entry.is_file() and not entry.is_symlink():
                total += stat.st_size
            count += 1
    return dict(metadata_sha256=value.hexdigest(), logical_bytes=total, entries=count)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--seed-sha', required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--bundle-ref', required=True)
    parser.add_argument('--bundle-sha256', required=True)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--jobs', type=int, default=16)
    parser.add_argument('--reserve-gib', type=int, default=12)
    args = parser.parse_args()
    if any(not re.fullmatch(r'[0-9a-f]{40}', sha) for sha in (args.sha, args.seed_sha)):
        parser.error('source and seed must be exact lowercase commit IDs')
    if not args.bundle_ref.startswith('refs/heads/') or args.jobs < 1 or args.reserve_gib < 8:
        parser.error('require a heads ref, positive jobs, and at least 8 GiB reserve')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('requires the x86_64 Linux gate container')
    seed, bundle = args.seed.resolve(strict=True), args.bundle.resolve(strict=True)
    run = (args.run or Path('/targets') / ('sail-compact-host-' + args.sha[:12])).absolute()
    if (seed.parent != Path('/targets') or run.exists() or run.is_symlink()
            or run.parent.resolve() != Path('/targets').resolve()):
        parser.error('seed and fresh run must be distinct direct children of /targets')
    if digest(bundle) != args.bundle_sha256:
        parser.error('bundle hash differs')
    previous_path = seed / 'rebuild-receipt.json'
    previous = json.loads(previous_path.read_text())
    if (previous.get('outcome') != 'passed' or previous.get('seed_unchanged') is not True
            or previous.get('source_sha') != args.seed_sha):
        parser.error('seed must have a passing unchanged-source receipt for --seed-sha')
    protected = {previous_path: digest(previous_path)}
    for name in ('host', 'native_wheel'):
        artifact = previous[name]
        path = Path(artifact['path']).resolve(strict=True)
        if not path.is_relative_to(seed) or digest(path) != artifact['sha256']:
            parser.error(f'seed {name} differs from its passing receipt')
        protected[path] = artifact['sha256']
    seed_target, venv = seed / 'target-host', seed / 'venv'
    source, target = run / 'source', run / 'target-host'
    seed_target_snapshot = tree_snapshot(seed_target, copying=True)
    venv_snapshot = tree_snapshot(venv)
    if not seed_target_snapshot['entries'] or not venv_snapshot['entries']:
        parser.error('seed host target and venv must be populated')
    initial_free = shutil.disk_usage('/targets').free
    required = seed_target_snapshot['logical_bytes'] + (args.reserve_gib + 2) * GIB
    if initial_free < required:
        parser.error(f'need copied host target + reserve + 2 GiB: {required}; free={initial_free}')
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('SAIL_', 'PYO3_', 'CARGO_PROFILE_')) or key in (
            'PYTHONHOME', 'PYTHONPATH', 'DYLD_LIBRARY_PATH', 'LD_LIBRARY_PATH',
            'CARGO_TARGET_DIR', 'CARGO_BUILD_TARGET', 'CARGO_BUILD_RUSTFLAGS',
            'CARGO_ENCODED_RUSTFLAGS', 'CARGO_ENCODED_RUSTDOCFLAGS',
            'RUSTFLAGS', 'RUSTDOCFLAGS', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER'):
            env.pop(key, None)
    env.update(PATH='/root/.cargo/bin:/usr/local/cargo/bin:' + env.get('PATH', ''),
               RUSTUP_TOOLCHAIN='1.97.1', PYTHONDONTWRITEBYTECODE='1',
               CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS=str(args.jobs))

    def output(command):
        return subprocess.check_output(list(map(str, command)), env=env, text=True).strip()

    def git(*command, path=source):
        return output(['git', '-C', path, *command])

    def guard_source(path, sha):
        if git('rev-parse', 'HEAD', path=path) != sha or git('status', '--porcelain', path=path):
            raise RuntimeError(f'source changed or is dirty: {path}')
        result = subprocess.run(['git', '-C', str(path), 'symbolic-ref', '-q', 'HEAD'],
                                env=env, capture_output=True)
        if result.returncode != 1:
            raise RuntimeError(f'source is not detached: {path}')

    guard_source(seed / 'source', args.seed_sha)
    python = venv / 'bin/python'
    # -B is explicit: isolated Python ignores PYTHONDONTWRITEBYTECODE.
    config = json.loads(output([python, '-I', '-B', '-c',
        'import sys,sysconfig,json;print(json.dumps(dict(base=sys.base_prefix,lib=sysconfig.get_config_var("LIBDIR"),purelib=sysconfig.get_path("purelib"),version=sys.version)))']))
    native = json.loads(output([python, '-I', '-B', '-c',
        'import importlib.metadata as m,json;d=m.distribution("sail-nutmeg");print(json.dumps(dict(distribution=d.metadata["Name"],version=d.version,libraries=[str(d.locate_file(f).resolve()) for f in d.files if str(f).endswith(".so")]),sort_keys=True))']))
    if not native['libraries']:
        parser.error('seed venv contains no installed native library')
    for value in native['libraries']:
        path = Path(value)
        if not path.is_relative_to(venv):
            parser.error('installed native library is outside seed venv')
        protected[path] = digest(path)
    protected[python.resolve()] = digest(python.resolve())
    if tree_snapshot(venv) != venv_snapshot:
        parser.error('read-only Python inspection changed the seed venv')
    run.mkdir()
    receipt = dict(started_utc=utc(), outcome='running', source_sha=args.sha,
                   native_source_sha=args.seed_sha, seed=str(seed), target=str(target),
                   seed_receipt_sha256=protected[previous_path], script_sha256=digest(__file__),
                   protected_artifacts={str(k): v for k, v in protected.items()},
                   seed_target_before=seed_target_snapshot, seed_venv_before=venv_snapshot,
                   native_wheel=previous['native_wheel'], installed_native=native,
                   reused_venv=str(venv), python=config,
                   bundle=dict(path=str(bundle), sha256=args.bundle_sha256, ref=args.bundle_ref),
                   launch_image_claim=args.image_id, platform=platform.uname()._asdict(),
                   arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                   free_bytes_before=initial_free, required_free_bytes=required, steps=[],
                   scope='host-only build; native tests and wheel reused from exact prior passing source after identity proof')

    def save():
        (run / 'rebuild-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def step(name, command, cwd=None):
        free = shutil.disk_usage('/targets').free
        if free < args.reserve_gib * GIB:
            raise RuntimeError(f'{name}: free={free}, below reserved headroom')
        record = dict(name=name, command=list(map(str, command)), started_utc=utc(), free_bytes_before=free)
        receipt['steps'].append(record)
        save()
        with (run / (name + '.log')).open('x') as log:
            result = subprocess.run(record['command'], env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        record.update(returncode=result.returncode, finished_utc=utc(), free_bytes_after=shutil.disk_usage('/targets').free)
        save()
        print(name, result.returncode, flush=True)
        if result.returncode:
            raise RuntimeError(f'{name} failed; log retained')

    detached = False
    save()
    try:
        step('clone', ['git', 'clone', '--no-hardlinks', '--no-checkout', seed / 'source', source])
        step('bundle-verify', ['git', '-C', source, 'bundle', 'verify', bundle])
        step('fetch', ['git', '-C', source, 'fetch', '--no-tags', bundle, args.bundle_ref])
        if git('rev-parse', 'FETCH_HEAD') != args.sha:
            raise RuntimeError('bundle ref differs from requested SHA')
        step('detach', ['git', '-C', source, 'checkout', '--detach', args.sha])
        detached = True
        guard_source(source, args.sha)
        identical = {}
        # The native extension's only path dependency outside examples is the
        # dependency-free resource FFI crate; include that tree in the proof.
        for name in ('examples/extensions', 'crates/sail-native-resource-ffi', 'Cargo.lock', 'Cargo.toml'):
            before = git('rev-parse', args.seed_sha + ':' + name)
            after = git('rev-parse', args.sha + ':' + name)
            if before != after:
                raise RuntimeError(f'cannot reuse native surface: {name} differs from seed')
            identical[name] = before
        receipt['native_identity'] = dict(git_objects=identical, exact_tree_and_blob_match=True)
        receipt['source_log'] = git('log', '--oneline', args.seed_sha + '..' + args.sha)
        receipt['source_tree'] = git('rev-parse', 'HEAD^{tree}')
        receipt['locks'] = {str(p.relative_to(source)): digest(p) for p in (
            source / 'Cargo.lock', source / 'examples/extensions/nutmeg/Cargo.lock',
            source / 'examples/extensions/argentea/Cargo.lock',
            source / 'examples/extensions/vendor/nutmeg-graph/Cargo.lock')}
        receipt['cgroup'] = {name: (Path('/sys/fs/cgroup') / name).read_text().strip()
                             for name in ('cpu.max', 'memory.max', 'memory.swap.max')}
        receipt['rust'] = output(['rustc', '--version'])
        env.update(CARGO_TARGET_DIR=str(target), PYO3_PYTHON=str(python),
                   PYTHONHOME=config['base'], PYTHONPATH=config['purelib'], LD_LIBRARY_PATH=config['lib'],
                   CARGO_PROFILE_RELEASE_DEBUG='0', CARGO_PROFILE_RELEASE_OPT_LEVEL='3',
                   CARGO_PROFILE_RELEASE_LTO='true', CARGO_PROFILE_RELEASE_CODEGEN_UNITS='1',
                   CARGO_PROFILE_RELEASE_STRIP='true')
        keys = ('CARGO_TARGET_DIR', 'CARGO_INCREMENTAL', 'CARGO_BUILD_JOBS', 'RUSTUP_TOOLCHAIN',
                'PYO3_PYTHON', 'PYTHONHOME', 'PYTHONPATH', 'LD_LIBRARY_PATH')
        receipt['host_environment'] = {k: v for k, v in env.items() if k in keys or k.startswith('CARGO_PROFILE_')}
        step('seed-host-target', ['cp', '-a', '--reflink=auto', seed_target, target])
        step('host-release-build', ['cargo', 'build', '--locked', '--release', '-p', 'sail-cli'], source)
        guard_source(source, args.sha)
        artifact = run / f'sail-linux-x86_64-{args.sha[:12]}-release'
        shutil.copy2(target / 'release/sail', artifact)
        with artifact.open('rb') as stream:
            import mmap
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as binary:
                if binary.find(b'execution_failure pid=') < 0:
                    raise RuntimeError('host lacks stream failure diagnostics marker')
        receipt['host'] = dict(path=str(artifact), sha256=digest(artifact), bytes=artifact.stat().st_size,
                               version=output([artifact, '--version']))
        receipt['outcome'] = 'passed'
    except BaseException as error:
        receipt.update(outcome='failed', error=repr(error))
    finally:
        try:
            if detached:
                guard_source(source, args.sha)
            guard_source(seed / 'source', args.seed_sha)
            for path, expected in protected.items():
                if digest(path) != expected:
                    raise RuntimeError(f'protected seed artifact changed: {path}')
            if tree_snapshot(seed_target, copying=True) != seed_target_snapshot:
                raise RuntimeError('seed host cache changed')
            if tree_snapshot(venv) != venv_snapshot:
                raise RuntimeError('seed venv changed')
            receipt['seed_unchanged'] = True
        except BaseException as error:
            receipt.update(outcome='failed', guard_error=repr(error), seed_unchanged=False)
        receipt.update(finished_utc=utc(), free_bytes_after=shutil.disk_usage('/targets').free)
        save()
    print(f"HOST_ONLY_BUILD {receipt['outcome'].upper()} {args.sha} receipt={run / 'rebuild-receipt.json'}", flush=True)
    return 0 if receipt['outcome'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
