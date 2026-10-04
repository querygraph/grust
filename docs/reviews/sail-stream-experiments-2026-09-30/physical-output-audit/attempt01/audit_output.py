#!/usr/bin/env python3
"""Supplemental physical SSSP checks; never a graph certificate or timing gate."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

PRODUCER = '3a9028057c6c6c5034492845926fc4bc18f9626f'
CLOSED_HELPER = 'c8d59db362136879bbd3a6efe8f527311849e3e0be18ddb64e6da996bdfcd318'
SHA = re.compile(r'^[0-9a-f]{64}$')
SCHEMA = {'id': pa.int64(), 'distance': pa.float64(), 'parent': pa.int64(), 'hops': pa.int64()}
MAX_VERTICES = 1 << 25
MAX_ROW_GROUP_BYTES = 256 << 20
MAX_RESULT_BYTES = 2 << 30
BATCH_ROWS = 65536


class Inconclusive(Exception):
    pass


class IntegrityError(Exception):
    pass


def need(condition, message):
    if not condition:
        raise IntegrityError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_pinned(path, digest):
    need(isinstance(digest, str) and SHA.fullmatch(digest), 'invalid supplied SHA256')
    if not path.exists():
        raise Inconclusive('missing evidence: ' + str(path))
    need(path.is_file() and not path.is_symlink(), 'evidence must be a regular nonsymlink file')
    data = path.read_bytes()
    need(hashlib.sha256(data).hexdigest() == digest, 'evidence hash mismatch: ' + str(path))
    def nonfinite(value):
        raise IntegrityError('nonfinite JSON constant: ' + value)
    result = json.loads(data, object_pairs_hook=strict_object, parse_constant=nonfinite)
    need(isinstance(result, dict), 'evidence JSON must be an object')
    return result


def timestamp(value):
    need(isinstance(value, str), 'missing closure timestamp')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(dt.tzinfo is not None and dt.year >= 2020, 'invalid closure timestamp')
    return dt


def verify_receipts(args, report):
    receipt = read_pinned(args.receipt, args.receipt_sha256)
    report['producer_outcome'] = receipt.get('outcome')
    closure = read_pinned(args.closure_audit, args.closure_sha256)
    if closure.get('integrity_status') != 'integrity_verified':
        raise Inconclusive('closed-cell integrity verification is not complete')
    need(closure.get('helper_sha256') == CLOSED_HELPER, 'unsupported closed-cell helper')
    need(closure.get('errors') == [] and closure.get('inconclusive_reasons') == [], 'contradictory closure verdict')
    records = closure.get('files')
    need(isinstance(records, dict), 'closure file inventory missing')
    need(any(name.endswith('/diagnostics/receipt.json') and isinstance(pin, dict)
             and pin.get('sha256') == args.receipt_sha256
             and pin.get('bytes') == args.receipt.stat().st_size
             for name, pin in records.items()), 'closure does not pin this producer receipt')
    observed = closure.get('recorded_outcomes')
    need(isinstance(observed, dict), 'closure outcomes missing')
    state = observed.get('docker_state')
    need(isinstance(state, dict), 'closure Docker state missing')
    if state.get('Running') is not False or state.get('Status') != 'exited':
        raise Inconclusive('producer container is not proven exited')
    timestamp(state.get('FinishedAt'))
    outcome = receipt.get('outcome')
    if not isinstance(outcome, str) or outcome in ('started', 'running', ''):
        raise Inconclusive('producer receipt is not terminal')
    need(observed.get('receipt_outcome') == outcome, 'closure outcome differs')
    start, finish = timestamp(receipt.get('started_utc')), timestamp(receipt.get('finished_utc'))
    need(finish >= start, 'producer closure precedes start')
    need(observed.get('producer_finished_utc') == receipt['finished_utc'], 'closure timestamp differs')
    options, dataset = receipt.get('arguments'), receipt.get('dataset')
    need(isinstance(options, dict) and isinstance(dataset, dict), 'producer arguments/dataset missing')
    need(receipt.get('harness_source_sha') == PRODUCER, 'unsupported producer source')
    need(options.get('output') == args.expected_cell_output, 'wrong cell output namespace')
    need(options.get('algorithm') == 'sssp' and options.get('engine') == 'pecan'
         and options.get('variant') in ('frontier', 'delta_star'), 'unsupported SSSP producer shape')
    n = args.expected_vertices
    need(type(n) is int and 0 < n <= MAX_VERTICES, 'dense domain exceeds admitted bound')
    need(type(args.expected_source) is int and 0 <= args.expected_source < n, 'invalid source')
    counts = dataset.get('counts')
    need(isinstance(counts, dict) and type(counts.get('vertices')) is int
         and counts['vertices'] == n, 'dataset vertex count differs')
    need(type(options.get('expected_vertices')) is int and options['expected_vertices'] == n,
         'producer expected vertex count differs')
    need(type(options.get('source')) is int and options['source'] == args.expected_source,
         'producer source differs')
    need(dataset.get('family') in ('graph500', 'traversal'), 'unsupported dense-domain family')
    if dataset['family'] == 'graph500':
        canonical = dataset.get('canonical')
        need(isinstance(canonical, dict) and isinstance(canonical.get('vertices'), dict),
             'Graph500 canonical vertex metadata missing')
        canonical = canonical['vertices']
        need(canonical.get('format') == 'little-endian int64 id; ascending 0..2^scale-1',
             'Graph500 dense domain declaration missing')
    else:
        need(dataset.get('purpose') == 'bounded correctness fixture; not a Graph500 input',
             'unsupported traversal generator')
    report.update(expected_vertices=n, expected_source=args.expected_source,
                  dense_domain='0 <= id < expected_vertices; generator/source contract, not input reread',
                  producer_runtime=receipt.get('runtime_source_sha'),
                  producer_correctness=receipt.get('correctness'))
    files = receipt.get('result_files')
    if not isinstance(files, list) or not files:
        raise Inconclusive('producer has no completed result file inventory')
    pins = {}
    for item in files:
        need(isinstance(item, dict), 'invalid result inventory entry')
        name = item.get('name')
        need(isinstance(name, str) and name == Path(name).name and name.endswith('.parquet')
             and name not in pins, 'unsafe or duplicate result basename')
        need(type(item.get('bytes')) is int and item['bytes'] > 0, 'invalid result length')
        need(isinstance(item.get('sha256'), str) and SHA.fullmatch(item['sha256']), 'invalid result SHA256')
        pins[name] = dict(bytes=item['bytes'], sha256=item['sha256'])
    report['expected_result_bytes'] = sum(pin['bytes'] for pin in pins.values())
    if report['expected_result_bytes'] > MAX_RESULT_BYTES:
        raise Inconclusive('result exceeds prepared 2 GiB read admission')
    report['result_inventory'] = pins
    return receipt, pins


def inventory(root):
    if not root.is_dir():
        raise Inconclusive('result directory is unavailable')
    need(not root.is_symlink(), 'result root is a symlink')
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            need(not (Path(directory) / name).is_symlink(), 'symlink within result directory')
        for name in files:
            if not name.endswith('.parquet'):
                continue
            path = Path(directory) / name
            need(path.is_file() and name not in result, 'nonregular or ambiguous result basename')
            result[name] = path
    return result


def file_identity(path):
    s = path.stat()
    return dict(bytes=s.st_size, sha256=sha256(path), device=s.st_dev, inode=s.st_ino,
                mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def footer(path):
    parquet = pq.ParquetFile(path, memory_map=False, pre_buffer=False)
    schema = parquet.schema_arrow
    need(len(schema) == len(SCHEMA) and set(schema.names) == set(SCHEMA), 'result schema columns differ')
    need(all(schema.field(name).type == kind for name, kind in SCHEMA.items()), 'result schema types differ')
    sizes = [parquet.metadata.row_group(i).total_byte_size for i in range(parquet.num_row_groups)]
    if any(size > MAX_ROW_GROUP_BYTES for size in sizes):
        raise Inconclusive('row group exceeds prepared 256 MiB decode admission')
    return parquet, dict(rows=parquet.metadata.num_rows, schema=str(schema),
                         row_groups=parquet.num_row_groups, max_row_group_bytes=max(sizes, default=0))


def scan_file(parquet, seen, n, source, counters):
    rows = 0
    def count(name, mask):
        counters[name] = counters.get(name, 0) + int(np.count_nonzero(mask))
    for batch in parquet.iter_batches(batch_size=BATCH_ROWS, columns=list(SCHEMA), use_threads=False):
        rows += batch.num_rows
        values, nulls = {}, {}
        for name in SCHEMA:
            column = batch.column(batch.schema.get_field_index(name))
            nulls[name] = column.is_null().to_numpy(zero_copy_only=False)
            values[name] = pc.fill_null(column, 0).to_numpy(zero_copy_only=False)
        ids, d, parent, hops = (values[name] for name in SCHEMA)
        valid_id = ~nulls['id'] & (ids >= 0) & (ids < n)
        unique, occurrences = np.unique(ids[valid_id], return_counts=True)
        counters['duplicate_ids'] += int(np.sum(occurrences - 1)) + int(np.count_nonzero(seen[unique]))
        counters['unique_ids'] += int(np.count_nonzero(seen[unique] == 0))
        seen[unique] = 1
        count('null_ids', nulls['id'])
        count('ids_out_of_domain', ~nulls['id'] & ~valid_id)
        reached = ~nulls['distance']
        count('unreachable_rows', ~reached)
        count('nan_distance', reached & np.isnan(d))
        count('positive_infinity_distance', reached & np.isposinf(d))
        count('negative_infinity_distance', reached & np.isneginf(d))
        count('negative_finite_distance', reached & np.isfinite(d) & (d < 0))
        count('unreachable_with_metadata', ~reached & (~nulls['parent'] | ~nulls['hops']))
        count('reached_null_parent', reached & nulls['parent'])
        count('reached_null_hops', reached & nulls['hops'])
        count('parent_out_of_domain', ~nulls['parent'] & ((parent < 0) | (parent >= n)))
        count('hops_out_of_range', ~nulls['hops'] & ((hops < 0) | (hops >= n)))
        root = valid_id & (ids == source)
        count('root_rows', root)
        count('invalid_root', root & (~reached | nulls['parent'] | nulls['hops']
                                      | (d != 0) | (parent != source) | (hops != 0)))
        count('nonroot_reached_zero_hops', reached & valid_id & ~root & ~nulls['hops'] & (hops == 0))
    return rows


def audit(args):
    started = time.monotonic()
    report = dict(started_utc=utc(), status='inconclusive', errors=[],
                  receipt_sha256=args.receipt_sha256, closure_sha256=args.closure_sha256,
                  expected_cell_output=args.expected_cell_output, result_directory=str(args.result_dir),
                  helper_sha256=sha256(Path(__file__)), python=sys.version, pyarrow=pa.__version__,
                  numpy=np.__version__, files=[], scope='Physical Parquet values and dense output domain only. '
                  'No input scan, shortest-path recomputation, parent-edge/chain proof, '
                  'certificate replacement, timing comparison or historical corruption claim.')
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    try:
        receipt, pins = verify_receipts(args, report)
        paths = inventory(args.result_dir)
        missing, extra = set(pins) - set(paths), set(paths) - set(pins)
        need(not extra, 'unrecorded result Parquet files')
        if missing:
            raise Inconclusive('missing recorded result files: ' + ', '.join(sorted(missing)))
        before = {}
        for name, path in sorted(paths.items()):
            identity = file_identity(path)
            need(all(identity[k] == v for k, v in pins[name].items()), 'result hash/length mismatch: ' + name)
            parquet, metadata = footer(path)
            parquet.close()
            before[name] = dict(identity=identity, metadata=metadata)
        n = args.expected_vertices
        seen = np.zeros(n, dtype=np.uint8)
        counters = dict(rows=0, unique_ids=0, duplicate_ids=0)
        for name, path in sorted(paths.items()):
            parquet, metadata = footer(path)
            try:
                need(metadata == before[name]['metadata'], 'Parquet footer changed before scan')
                rows = scan_file(parquet, seen, n, args.expected_source, counters)
            finally:
                parquet.close()
            need(rows == metadata['rows'], 'decoded/footer row count mismatch: ' + name)
            counters['rows'] += rows
            report['files'].append(dict(name=name, relative_path=str(path.relative_to(args.result_dir)),
                                        before=before[name], streamed_rows=rows))
        counters['missing_ids'] = n - counters['unique_ids']
        report['counts'] = counters
        need(inventory(args.result_dir) == paths, 'result inventory changed during scan')
        for item in report['files']:
            name = item['name']
            parquet, metadata = footer(paths[name])
            parquet.close()
            after = dict(identity=file_identity(paths[name]), metadata=metadata)
            item['after'] = after
            need(after == before[name], 'result changed during scan: ' + name)
        read_pinned(args.receipt, args.receipt_sha256)
        read_pinned(args.closure_audit, args.closure_sha256)
        report['identities_unchanged'] = True
        allowed = {'rows', 'unique_ids', 'unreachable_rows', 'root_rows'}
        failures = {key: value for key, value in counters.items() if key not in allowed and value}
        if counters['rows'] != n:
            failures['rows_differ_from_expected'] = counters['rows']
        if counters.get('root_rows') != 1:
            failures['root_rows_differ_from_one'] = counters.get('root_rows', 0)
        report['physical_failures'] = failures
        report['status'] = 'physical_values_fail' if failures else 'physical_values_pass'
    except Inconclusive as error:
        report['errors'].append(str(error))
    except (IntegrityError, ValueError, TypeError, KeyError, OSError, pa.ArrowException) as error:
        report.update(status='integrity_error')
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        report['finished_utc'] = utc()
        report['audit_elapsed_seconds_not_benchmark'] = time.monotonic() - started
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['process_peak_rss_bytes'] = int(rss if sys.platform == 'darwin' else rss * 1024)
        report['admission'] = dict(batch_rows=BATCH_ROWS, arrow_cpu_threads=1, arrow_io_threads=1,
                                  maximum_dense_vertices=MAX_VERTICES, seen_bytes=args.expected_vertices,
                                  maximum_result_bytes=MAX_RESULT_BYTES,
                                  maximum_row_group_uncompressed_bytes=MAX_ROW_GROUP_BYTES)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('receipt', 'closure-audit', 'result-dir', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('receipt-sha256', 'closure-sha256', 'expected-cell-output'):
        parser.add_argument('--' + name, required=True)
    for name in ('expected-vertices', 'expected-source'):
        parser.add_argument('--' + name, type=int, required=True)
    args = parser.parse_args()
    report = audit(args)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(report['status'])
    return 0 if report['status'] == 'physical_values_pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
