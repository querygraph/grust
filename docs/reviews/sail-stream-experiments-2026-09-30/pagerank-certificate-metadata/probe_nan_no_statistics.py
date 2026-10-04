"""Exercise the real reference/certificate validators on a two-vertex fixed point."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import pyarrow as pa
import pyarrow.parquet as pq

BINARY = Path('/Users/alexy/src/sail/.venvs/default/bin/sail')
NATIVE = Path('/Users/alexy/src/sail/python/pysail/_native.abi3.so')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('repo', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(exist_ok=False)
    source = repo/'examples/extensions/benchmarks/graph_cell.py'
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    assert subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
    assert subprocess.run(['git', '-C', str(repo), 'diff', '--quiet', 'HEAD']).returncode == 0
    pins = {str(p): digest(p) for p in (source, BINARY, NATIVE, Path(__file__))}
    assert pins[str(BINARY)] == '27c01027afe78f6403d8c02c34199e30ef9103d11adb24403a6575b4bca40a09'
    assert pins[str(NATIVE)] == 'b99f1717cf49706f17eefd44d78c3751e6fd2b46a34ce3fd2cc360087b7f9685'
    sys.path[:0] = [str(source.parent), str(repo/'examples/extensions/nutmeg/python')]
    from graph_cell import validate
    from pyspark.sql.connect.session import SparkSession

    private = Path(tempfile.mkdtemp(prefix='pagerank-metadata-probe-'))
    receipt = dict(started_utc=utc(), source_commit=head, source_pins=pins,
                   private_fixtures=str(private), results=[],
                   installed_version=subprocess.check_output([str(BINARY), '--version'], text=True).strip(),
                   scope='Actual Python validator and local SQL/Parquet, installed runtime only; two-vertex fixed point. No algorithm timing, cluster or stream-cause claim.')
    dataset = private/'dataset'
    dataset.mkdir()
    pq.write_table(pa.table({'id': [0, 1]}), dataset/'vertices.parquet')
    pq.write_table(pa.table({'src': [0, 1], 'dst': [1, 0]}), dataset/'edges.parquet')
    pq.write_table(pa.table({'id': [0, 1], 'pagerank': [.5, .5]}), dataset/'reference.parquet')
    cases = [
        ('valid', [1, 1], [True, True], [.5, .5]),
        ('nan_score', [1, 1], [True, True], [float('nan'), .5]),
        ('partial_null_converged', [1, 1], [True, None], [.5, .5]),
        ('partial_null_iterations', [1, None], [True, True], [.5, .5]),
        ('negative_iterations', [-1, -1], [True, True], [.5, .5]),
        ('over_cap_iterations', [101, 101], [True, True], [.5, .5]),
        ('mixed_iterations', [1, 2], [True, True], [.5, .5]),
        ('not_converged', [1, 1], [True, False], [.5, .5]),
        ('wrong_scores', [1, 1], [True, True], [.4, .6]),
    ]
    server = session = None
    try:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        env = {k: v for k, v in os.environ.items() if not k.startswith('SAIL_') and k not in ('PYTHONPATH', 'PYTHONHOME')}
        env.update(SAIL_MODE='local', SAIL_EXECUTION__DEFAULT_PARALLELISM='2', TOKIO_WORKER_THREADS='2', RAYON_NUM_THREADS='2', RUST_LOG='warn')
        command = [str(BINARY), 'spark', 'server', '--ip', '127.0.0.1', '--port', str(port)]
        receipt['server_command'] = command
        with (output/'server.log').open('w') as log:
            server = subprocess.Popen(command, cwd=private, env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while True:
            if server.poll() is not None:
                raise RuntimeError('server exited at startup')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError('server startup timed out')
                time.sleep(.05)
        session = SparkSession.builder.remote(f'sc://127.0.0.1:{port}').create()
        for name, iterations, converged, scores in cases:
            result = private/name
            result.mkdir()
            pq.write_table(pa.table({'id': [0, 1], 'score': scores,
                           'iterations': pa.array(iterations, type=pa.int64()),
                           'converged': pa.array(converged, type=pa.bool_()),
                           'residual': [0., 0.]}), result/'part.parquet', write_statistics=False)
            for policy in ('reference', 'certificate'):
                row = dict(case=name, policy=policy, iterations=iterations, converged=converged, scores=[repr(x) for x in scores])
                from pyspark.sql.connect import functions as F
                frame = session.read.parquet(result.as_uri())
                row['direct_rows'] = repr(frame.select('id', 'score', F.isnan('score').alias('isnan')).collect())
                row['output_statistics_written'] = False
                row['parquet_rows'] = repr(pq.read_table(result/'part.parquet').to_pylist())
                try:
                    row['correctness'] = validate(session, result, dataset, 'pagerank', 2, 1e-8, .85, 100, False, False, policy=policy)
                    row['outcome'] = 'accepted'
                except (AssertionError, RuntimeError) as error:
                    row.update(outcome='rejected', error_type=type(error).__name__, error=str(error))
                receipt['results'].append(row)
        receipt['outcome'] = 'observations_complete'
    except BaseException as error:
        receipt.update(outcome='probe_error', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if session is not None:
            session.stop()
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
            receipt['server_reaped'] = True
        receipt['source_and_runtime_unchanged'] = pins == {p: digest(Path(p)) for p in pins}
        receipt['head_unchanged'] = head == subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        receipt['finished_utc'] = utc()
        (output/'receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps([dict(case=r['case'], policy=r['policy'], outcome=r['outcome']) for r in receipt['results']]))


if __name__ == '__main__':
    main()
