"""One matched cit-Patents Pecan WCC cell; fresh 16-CPU/32-GiB Linux container.

Original Parquet bytes, lazy column aliases, unchanged public API validation,
and a separately timed full physical-output comparison with the pinned oracle.
This is not a trusted-input entry point or an external-engine comparison.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
from urllib.parse import unquote, urlparse

HEAD = '3a9028057c6c6c5034492845926fc4bc18f9626f'
RUNTIME = '56194b170155301ba91077f0ba3df31fe2c78b6b'
NATIVE = 'ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
BINARY = Path('/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release')
BINARY_SHA = '5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
NATIVE_SHA = 'eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50'
VERTICES_SHA = '0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa'
EDGES_SHA = '70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f'
REFERENCE_SHA = 'b07f8665c87f94286da7beb1ac5a9d13c4932fea31d8f1a382f9ecb1d3c0c8dc'
ROWS, EDGE_ROWS, MAX_ID = 3774768, 16518947, 6009554
GIB = 2**30


class Mismatch(RuntimeError):
    pass


class NonConverged(RuntimeError):
    pass


def check(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def append(path, value):
    with path.open('a') as stream:
        stream.write(json.dumps(dict(recorded_utc=utc(), **value)) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def oracle(path, expected_sha, rows, maximum):
    import numpy as np
    check(sha(path) == expected_sha and path.stat().st_size == rows * 16, 'oracle hash/length mismatch')
    pairs = np.fromfile(path, dtype='<i8').reshape((-1, 2))
    ids, labels = pairs[:, 0], pairs[:, 1]
    check(len(ids) == rows and bool(np.all((ids > 0) & (ids <= maximum))) and bool(np.all(ids[1:] > ids[:-1])), 'invalid oracle vertex domain/order')
    expected = np.full(maximum + 1, -1, dtype=np.int64)
    expected[ids] = labels
    check(bool(np.all((labels > 0) & (labels <= ids))), 'invalid oracle representatives')
    check(bool(np.all(expected[labels] == labels)), 'oracle representative is not a canonical member')
    check(sha(path) == expected_sha, 'oracle changed during read')
    return expected


def inventory(directory):
    files = {}
    check(directory.is_dir() and not directory.is_symlink(), 'missing/unsafe result directory')
    for p in sorted(directory.rglob('*')):
        check(not p.is_symlink(), 'result symlink')
        if p.is_file():
            files[str(p.relative_to(directory))] = dict(bytes=p.stat().st_size, sha256=sha(p))
        else:
            check(p.is_dir(), 'special result file')
    return files


def verify_output(directory, expected, rows):
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    before = inventory(directory)
    files = [name for name in before if name.endswith('.parquet')]
    if not files:
        raise Mismatch('no result Parquet')
    seen = np.zeros(len(expected), dtype=np.bool_)
    count = 0
    for name in files:
        p = pq.ParquetFile(directory / name)
        schema = p.schema_arrow
        if schema.names != ['id', 'component'] or any(f.type != pa.int64() for f in schema):
            raise Mismatch('result must have exactly id:int64, component:int64')
        file_rows = 0
        for batch in p.iter_batches(batch_size=65536, use_threads=False):
            if any(a.null_count for a in batch.columns):
                raise Mismatch('null vertex/component')
            ids, labels = [a.to_numpy(zero_copy_only=False) for a in batch.columns]
            if not bool(np.all((ids > 0) & (ids < len(expected)))):
                raise Mismatch('out-of-range vertex')
            if bool(np.any(expected[ids] < 0)) or bool(np.any(seen[ids])) or len(np.unique(ids)) != len(ids):
                raise Mismatch('unknown/duplicate vertex')
            if not bool(np.all(labels == expected[ids])):
                raise Mismatch('exact minimum-ID component membership mismatch')
            seen[ids] = True
            file_rows += len(ids)
        if file_rows != p.metadata.num_rows:
            raise Mismatch('physical/footer row mismatch')
        count += file_rows
    if count != rows or int(np.count_nonzero(seen)) != rows or not bool(np.all(seen[expected >= 0])):
        raise Mismatch('incomplete vertex domain')
    check(inventory(directory) == before, 'result bytes/inventory changed during verification')
    representatives, sizes = np.unique(expected[expected >= 0], return_counts=True)
    return dict(rows=count, unique=count, membership_mismatches=0, canonicalization='exact minimum original vertex ID',
                components=len(representatives), largest_component_vertices=int(sizes.max()),
                verification='independent PyArrow full physical output versus pinned union-find membership', result_files=before)


@contextlib.contextmanager
def input_timers(module, receipt, output=None):
    """Delegate unchanged public-API work; do not remove any validation action."""
    schema, snapshot, materialize = module._check_input_schema, module._snapshot, module.StagingRun.materialize
    def timed_schema(*args, **kwargs):
        start = time.perf_counter()
        try:
            return schema(*args, **kwargs)
        finally:
            receipt['input_schema_seconds'] = time.perf_counter() - start
    def timed_snapshot(*args, **kwargs):
        if output is not None:
            parsed = urlparse(args[0].path)
            check(parsed.scheme == 'file' and Path(unquote(parsed.path)).resolve().is_relative_to((output / 'staging').resolve()), 'GraphUtils run is outside watched staging root')
            receipt['graphutils_staging_root_verified'] = True
        times, start = [], time.perf_counter()
        def timed_materialize(*a, **kw):
            t = time.perf_counter()
            try:
                return materialize(*a, **kw)
            finally:
                times.append(time.perf_counter() - t)
        module.StagingRun.materialize = timed_materialize
        try:
            return snapshot(*args, **kwargs)
        finally:
            module.StagingRun.materialize = materialize
            total = time.perf_counter() - start
            receipt.update(input_snapshot_and_validation_seconds=total, input_snapshot_materialize_seconds=times,
                           input_validation_and_count_seconds=total - sum(times))
    module._check_input_schema, module._snapshot = timed_schema, timed_snapshot
    try:
        yield
    finally:
        module._check_input_schema, module._snapshot, module.StagingRun.materialize = schema, snapshot, materialize


def deadline(*_):
    raise TimeoutError('pilot phase timeout')


def round_summary(events, ready_seconds=None):
    starts, durations = {}, []
    for e in events:
        if e['kind'] == 'iteration_start':
            starts[e['iteration']] = e['elapsed_seconds']
        elif e['kind'] == 'iteration_end' and e['iteration'] in starts:
            durations.append(dict(iteration=e['iteration'], seconds=e['elapsed_seconds']-starts.pop(e['iteration'])))
    first = next((e['elapsed_seconds'] for e in events if e['kind'] == 'iteration_start'), None)
    last = next((e['elapsed_seconds'] for e in reversed(events) if e['kind'] == 'iteration_end'), None)
    return dict(completed_round_durations=durations, incomplete_rounds=sorted(starts), pre_first_round_seconds=first,
                post_last_round_seconds=ready_seconds-last if ready_seconds is not None and last is not None else None,
                boundary='start/end differences measure contraction rounds; setup and reverse expansion/final normalization are separate')


def source_guard(repo):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], env=env, text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], env=env, text=True).strip()
    check(head == HEAD and not dirty, 'controller must be clean pinned3a')


def execute(args, r):
    source_guard(args.repo)
    sys.path.insert(0, str(args.repo / 'examples/extensions/benchmarks'))
    sys.path.insert(0, str(args.repo / 'examples/extensions/graph-algorithms/src'))
    runtime, measurement = importlib.import_module('runtime'), importlib.import_module('measurement')
    module = importlib.import_module('pyspark_pecan.algorithms')
    check(Path(module.__file__).resolve().is_relative_to(args.repo), 'Pecan imported from wrong source')
    from pyspark.sql.connect.session import SparkSession
    from pyspark.sql.connect.client.retries import DefaultPolicy
    check(sha(BINARY) == BINARY_SHA, 'runtime binary identity mismatch')
    identity = runtime.native_package_identity()
    check(NATIVE_SHA in [v for k, v in identity['files_sha256'].items() if k.endswith('.so')], 'native binary identity mismatch')
    r.update(native_package_identity=identity, packages=runtime.package_versions(), cgroup_before=measurement.cgroup_snapshot())
    cg = r['cgroup_before']
    quota, period = map(int, cg['cpu.max'].split())
    check(int(cg['memory.max']) == 32*GIB and int(cg['memory.swap.max']) == 0 and quota == 16*period, 'requires 16-CPU32GiB/no-swap cgroup')
    ticks = measurement.cpu_ticks()
    cleanup, handle, spark, events = r['cleanup_errors'], None, None, []
    sampler = measurement.Sampler(args.output / 'memory-samples.jsonl', watch={'staging': args.output / 'staging'})
    try:
        with sampler:
            startup = time.perf_counter()
            with runtime.server(BINARY, args.output, args.mode, 16, 16, 256*2**20, cleanup,
                                worker_task_slots=64, sail_pool_bytes=(24 if args.mode == 'local' else 8)*GIB, http2_keepalive_timeout=120) as (endpoint, pid):
                r['driver_pid'] = pid
                try:
                    spark = SparkSession.builder.remote(endpoint).create()
                    spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100, max_backoff=100, jitter=0)])
                    signal.alarm(120)
                    check(spark.sql('SELECT 1 AS ready').first().ready == 1, 'server not ready')
                    r['startup_seconds'] = time.perf_counter() - startup
                    vertices = spark.read.parquet(args.vertices.as_uri())
                    edges = spark.read.parquet(args.edges.as_uri()).selectExpr('source AS src', 'target AS dst')
                    sampler.mark('execute')
                    r['cgroup_execution_before'] = measurement.cgroup_snapshot()
                    signal.alarm(args.timeout)
                    start = time.perf_counter()
                    def observe(event):
                        event = dict({k: v for k, v in event.items() if k != 'run_path'}, elapsed_seconds=time.perf_counter() - start)
                        events.append(event)
                        append(args.output / 'events.jsonl', event)
                    graph = module.GraphAlgorithms(spark, observer=observe)
                    try:
                        with input_timers(module, r, args.output):
                            handle = graph.wcc(vertices, edges, method=args.method, seed=42, partitions=16, max_iterations=100)
                    except module.ConvergenceError as error:
                        raise NonConverged(str(error)) from error
                    r.update(algorithm_ready_seconds=time.perf_counter()-start, iterations=handle.iterations, converged=handle.converged)
                    check(handle.converged, 'WCC did not converge')
                    export = time.perf_counter()
                    handle.frame.select('id', 'component').write.mode('error').parquet((args.output / 'result').as_uri())
                    r.update(end_to_end_seconds=time.perf_counter()-start, export_seconds=time.perf_counter()-export,
                             cgroup_execution_after=measurement.cgroup_snapshot())
                    sampler.mark('verification')
                    signal.alarm(args.timeout)
                    verify = time.perf_counter()
                    expected = oracle(args.reference, REFERENCE_SHA, ROWS, MAX_ID)
                    r['oracle_load_seconds'] = time.perf_counter() - verify
                    r['correctness'] = verify_output(args.output / 'result', expected, ROWS)
                    r['verification_seconds'] = time.perf_counter() - verify
                    r['outcome'] = 'passed'
                finally:
                    signal.alarm(0)
                    sampler.mark('cleanup')
                    for name, action in [('result', handle.close if handle is not None else None), ('session', spark.stop if spark is not None else None)]:
                        if action is not None:
                            try:
                                signal.alarm(30)
                                action()
                            except BaseException as error:
                                cleanup.append(dict(operation=name, error=repr(error)))
                            finally:
                                signal.alarm(0)
    finally:
        r.update(events=events, memory=sampler.receipt(), cgroup_after=measurement.cgroup_snapshot(),
                 guest_steal_fraction=measurement.steal_fraction(ticks, measurement.cpu_ticks()), steal_scope='whole Linux VM over trial')
        r['rounds'] = round_summary(events, r.get('algorithm_ready_seconds'))
        if 'start' in locals() and 'end_to_end_seconds' not in r:
            r['elapsed_until_error_seconds'] = time.perf_counter() - start
    check(not cleanup and sampler.error is None, 'cleanup/sampler error')
    r['staging_files_after_shutdown'] = [str(p.relative_to(args.output)) for p in (args.output / 'staging').rglob('*.parquet')]
    check(not r['staging_files_after_shutdown'], 'retained staging files after successful shutdown')
    source_guard(args.repo)
    check(sha(BINARY) == BINARY_SHA and runtime.native_package_identity() == identity, 'runtime/native bytes changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'vertices', 'edges', 'reference', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--mode', choices=['local', 'process-cluster'], required=True)
    parser.add_argument('--method', choices=['randomized', 'randomized_fused'], required=True)
    parser.add_argument('--timeout', type=int, default=1200)
    args = parser.parse_args()
    for name in ('repo', 'vertices', 'edges', 'reference', 'output'):
        setattr(args, name, getattr(args, name).resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    r = dict(started_utc=utc(), outcome='error', arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
             cleanup_errors=[], controller=HEAD, runtime=RUNTIME, native=NATIVE, helper_sha256=sha(__file__),
             timer_boundary='lazy input handles through unchanged public WCC API and full output write; startup, hash/oracle preparation and physical verification excluded',
             validation_boundary='input_snapshot materializations remain inside public API; validation_and_count is snapshot elapsed minus its original materialize calls; includes Python/control overhead',
             diagnostic_boundary='durable observer event logging and matched task_runner debug logging are included in algorithm timing; no additional Explain RPC; actual cluster worker plans are logged, local actual-plan coverage is not established',
             resources=dict(cpus=16, memory_bytes=32*GIB, pool_per_process_bytes=(24 if args.mode == 'local' else 8)*GIB, potential_pool_total_bytes=24*GIB,
                            native_quota_per_process_bytes=256*2**20, potential_native_total_bytes=(1 if args.mode == 'local' else 3)*256*2**20,
                            pool_scope='sum of configured process pools, not a shared enforceable RSS/admission budget', partitions=16, threads_per_process=16, worker_count=0 if args.mode == 'local' else 2, worker_slots=64),
             interpretation='shared-host pilot; no dedicated timing, external-engine parity or trusted-input/B7 implementation claim')
    inputs = {str(args.vertices): VERTICES_SHA, str(args.edges): EDGES_SHA, str(args.reference): REFERENCE_SHA}
    try:
        check(args.timeout > 0 and Path('/.dockerenv').exists() and Path('/proc/stat').exists(), 'requires fresh isolated Linux container and positive timeout')
        signal.signal(signal.SIGALRM, deadline)
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt('operator interrupted')))
        sys.dont_write_bytecode = True
        for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
            os.environ[name] = '1'
        os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
        os.environ['GIT_OPTIONAL_LOCKS'] = '0'
        os.environ['SPARK_CONNECT_MODE_ENABLED'] = '1'
        os.environ['SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS'] = '900'
        os.environ['SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS'] = '86400'
        os.environ['SAIL_BENCHMARK_RUST_LOG'] = 'info,sail_execution::task_runner=debug'
        prep = time.perf_counter()
        r['input_hashes_before'] = {p: sha(p) for p in inputs}
        check(r['input_hashes_before'] == inputs, 'original input/oracle hash mismatch')
        import pyarrow as pa
        import pyarrow.parquet as pq
        pa.set_cpu_count(1)
        pa.set_io_thread_count(1)
        for path, names, rows in [(args.vertices, ['id'], ROWS), (args.edges, ['source', 'target'], EDGE_ROWS)]:
            file = pq.ParquetFile(path)
            check(file.schema_arrow.names == names and all(f.type == pa.int64() for f in file.schema_arrow) and file.metadata.num_rows == rows, 'original input schema/row mismatch')
        r['oracle_components'] = 3627
        r['input_hash_and_footer_preparation_seconds'] = time.perf_counter() - prep
        execute(args, r)
    except BaseException as error:
        r['outcome'] = 'mismatch' if isinstance(error, Mismatch) else 'nonconverged' if isinstance(error, NonConverged) else 'timeout' if isinstance(error, TimeoutError) else 'interrupted' if isinstance(error, KeyboardInterrupt) else 'error'
        r['error'] = traceback.format_exc()
    finally:
        signal.alarm(0)
        try:
            r['input_hashes_after'] = {p: sha(p) for p in inputs}
            check(r['input_hashes_after'] == inputs and sha(__file__) == r['helper_sha256'], 'input/oracle/helper changed')
        except BaseException:
            r['integrity_error'] = traceback.format_exc()
            r['outcome'] = 'error'
        if r.get('cgroup_after', {}).get('memory.events'):
            counters = dict(line.split() for line in r['cgroup_after']['memory.events'].splitlines())
            if int(counters.get('oom_kill', 0)) > 0:
                r['outcome'] = 'oom'
        r['finished_utc'] = utc()
        (args.output / 'receipt.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps(dict(outcome=r['outcome'], receipt=str(args.output / 'receipt.json'))))
    return 0 if r['outcome'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
