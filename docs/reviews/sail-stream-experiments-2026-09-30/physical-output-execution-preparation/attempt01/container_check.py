#!/usr/bin/env python3
"""Read-only admission and frozen verifier invocation inside the bounded container."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), outcome='admission_error')
    rc = 2
    try:
        root = Path('/work')
        need(sha(root / 'request.json') == sys.argv[1], 'request hash differs')
        request = json.loads((root / 'request.json').read_text())
        for name, pin in request['files'].items():
            path = root / name
            need(path.stat().st_size == pin['bytes'] and sha(path) == pin['sha256'], 'bundle file differs: ' + name)
        c = json.loads((root / 'configuration.json').read_text())
        report['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        need(report['boot_id'] == request['boot_id'], 'VM boot differs')
        # These cgroup files are this checker container, not the producer or VM.
        report['cgroup'] = {name: (Path('/sys/fs/cgroup') / name).read_text().strip()
                            for name in ('memory.max', 'memory.swap.max', 'cpu.max', 'pids.max')}
        need(report['cgroup']['memory.max'] == '2147483648' and report['cgroup']['memory.swap.max'] == '0', 'memory/swap cap differs')
        quota, period = map(int, report['cgroup']['cpu.max'].split())
        need(quota == period and report['cgroup']['pids.max'] == '64', 'CPU/PID cap differs')
        import numpy
        import pyarrow
        report['python'] = sys.version
        report['versions'] = dict(python='.'.join(map(str, sys.version_info[:3])), pyarrow=pyarrow.__version__, numpy=numpy.__version__)
        need(report['versions'] == dict(python=request['expected_python_version'], pyarrow=request['expected_pyarrow'], numpy=request['expected_numpy']), 'reader version differs')
        report['runtime_files'] = {}
        for label, path, expected in (
            ('sail', c['container_sail_binary'], request['binary_sha256']),
            ('native', request['native_path'], request['native_sha256']),
            ('python', sys.executable, None), ('pyarrow_init', pyarrow.__file__, None),
            ('pyarrow_lib', pyarrow.lib.__file__, None), ('numpy_init', numpy.__file__, None),
            ('numpy_multiarray', numpy._core._multiarray_umath.__file__, None)):
            p = Path(path)
            before = p.stat()
            digest = sha(p)
            after = p.stat()
            need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                 (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), label + ' file changed')
            need(expected is None or digest == expected, label + ' hash differs')
            report['runtime_files'][label] = dict(path=path, resolved=str(p.resolve()), bytes=after.st_size, sha256=digest, expected_sha256=expected)
        receipt = json.loads((root / 'producer-receipt.json').read_text())
        for key in ('runtime_source_sha', 'native_source_sha', 'harness_source_sha'):
            need(receipt.get(key) == c[key], 'producer ' + key + ' differs')
        command = [sys.executable, '-I', '-B', '/work/audit_output.py',
            '--receipt', '/work/producer-receipt.json', '--receipt-sha256', request['files']['producer-receipt.json']['sha256'],
            '--closure-audit', '/work/closed-audit.json', '--closure-sha256', request['files']['closed-audit.json']['sha256'],
            '--expected-cell-output', request['cell_output'], '--expected-vertices', str(request['expected_vertices']),
            '--expected-source', str(request['expected_source']), '--result-dir', request['cell_output'] + '/result',
            '--output', '/evidence/physical-output.json']
        report['command'] = command
        report['outcome'] = 'admitted'
        rc = subprocess.run(command, check=False).returncode
        report['verifier_returncode'] = rc
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with Path('/evidence/reader-admission.json').open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
