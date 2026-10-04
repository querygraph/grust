"""Root-owned immutable native F0 release build, with durable evidence."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import platform
import subprocess
import traceback

BASE = Path('/Volumes/Apo/graph-tests/results/sem-review-20261001')
ROOT = BASE / 'F0-native-build01'
SOURCE = BASE / 'F0-native-preparation01/csr-floor'

def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def pin(path: Path) -> dict[str, object]:
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha}

def save(data: dict[str, object]) -> None:
    tmp = ROOT / 'receipt.tmp'
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(ROOT / 'receipt.json')

def main() -> None:
    data: dict[str, object] = {'started_utc': utc(), 'outcome': 'building', 'owner_pid': os.getpid(), 'errors': []}
    locks: list[Path] = []
    try:
        assert platform.system() == 'Darwin' and platform.machine() == 'x86_64'
        for name in ('gate.lock', 'serial-queue.lock'):
            lock = BASE / name
            lock.mkdir()
            (lock / 'owner.json').write_text(json.dumps({'pid': os.getpid(), 'job': str(ROOT)}))
            locks.append(lock)
        source_files = sorted(p for p in SOURCE.rglob('*') if p.is_file())
        assert [str(p.relative_to(SOURCE)) for p in source_files] == ['Cargo.lock', 'Cargo.toml', 'src/main.rs']
        before = {str(p.relative_to(SOURCE)): pin(p) for p in source_files}
        data['source_before'] = before
        cargo = Path('/Users/alexy/.cargo/bin/cargo')
        rustc = Path('/Users/alexy/.cargo/bin/rustc')
        data['cargo_version'] = subprocess.check_output([str(cargo), '-V'], text=True).strip()
        data['rustc_verbose'] = subprocess.check_output([str(rustc), '-vV'], text=True).strip()
        env = os.environ.copy()
        for name in ('RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS'):
            env.pop(name, None)
        settings = {'CARGO_TARGET_DIR': str(ROOT / 'target'), 'CARGO_BUILD_JOBS': '8', 'CARGO_INCREMENTAL': '0',
                    'CARGO_PROFILE_RELEASE_OPT_LEVEL': '3', 'CARGO_PROFILE_RELEASE_DEBUG': '0',
                    'CARGO_PROFILE_RELEASE_STRIP': 'true', 'CARGO_PROFILE_RELEASE_CODEGEN_UNITS': '1',
                    'CARGO_PROFILE_RELEASE_LTO': 'thin'}
        env.update(settings)
        data['environment'] = settings
        argv = [str(cargo), 'build', '--locked', '--release', '--manifest-path', str(SOURCE / 'Cargo.toml')]
        data['command'] = argv
        with (ROOT / 'build.log').open('xb') as log:
            process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            data['cargo_pid'] = process.pid
            save(data)
            code = process.wait()
        data['returncode'] = code
        after = {str(p.relative_to(SOURCE)): pin(p) for p in source_files}
        data['source_after'] = after
        assert before == after and code == 0
        binary = ROOT / 'target/release/csr-floor'
        data['binary'] = pin(binary)
        data['file_type'] = subprocess.check_output(['/usr/bin/file', str(binary)], text=True).strip()
        assert 'Mach-O 64-bit executable x86_64' in str(data['file_type'])
        data['outcome'] = 'passed_optimized_native_F0_build'
    except BaseException as error:
        data['outcome'] = 'error'
        data['errors'] = [repr(error)]
        data['traceback'] = traceback.format_exc()
    finally:
        for lock in reversed(locks):
            (lock / 'owner.json').unlink()
            lock.rmdir()
        data['locks_released'] = all(not (BASE / n).exists() for n in ('gate.lock', 'serial-queue.lock'))
        data['finished_utc'] = utc()
        save(data)

if __name__ == '__main__':
    main()
