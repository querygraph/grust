#!/usr/bin/env python3
"""Independent local byte/row audit of the already downloaded cit-Patents pair."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import resource
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent


def info(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return dict(bytes=path.stat().st_size, sha256=h.hexdigest())


def main():
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    original = info(ROOT / 'receipt.json')
    receipt = json.loads((ROOT / 'receipt.json').read_text())
    before = {}
    for name, expected in receipt['evidence_files'].items():
        before[name] = info(ROOT / name)
        assert before[name] == expected, name
    inventory = ROOT / receipt['source_inventory']['path']
    assert info(inventory)['sha256'] == receipt['source_inventory']['sha256']
    urls = set(json.loads(inventory.read_text())['urls'])
    private = Path(receipt['private_original_directory'])
    assert private.is_dir() and not private.is_symlink()
    files = []
    for item in receipt['downloads']:
        path = private / item['name']
        assert not path.is_symlink()
        expected = {key: item[key] for key in ('bytes', 'sha256')}
        assert info(path) == expected
        assert item['url'] in urls and item['http_status'] == 200
        files.append(pq.ParquetFile(path, memory_map=False, pre_buffer=False))
    vertices, edges = files
    assert vertices.schema_arrow.names == ['id']
    assert edges.schema_arrow.names == ['source', 'target']
    assert all(field.type == pa.int64() for f in files for field in f.schema_arrow)
    # Independent representation: direct presence bitmap for this pinned ID range,
    # instead of the producer's sorted i64 array and binary membership search.
    minimum, maximum = receipt['vertices']['minimum'], receipt['vertices']['maximum']
    assert minimum == 1 and maximum == 6009554
    present = np.zeros(maximum + 1, dtype=np.bool_)
    rows = 0
    for batch in vertices.iter_batches(batch_size=32768, use_threads=False):
        column = batch.column(0)
        assert column.null_count == 0
        ids = column.to_numpy(zero_copy_only=False)
        assert np.all((ids >= minimum) & (ids <= maximum))
        assert len(np.unique(ids)) == len(ids) and not np.any(present[ids])
        present[ids] = True
        rows += len(ids)
    assert rows == vertices.metadata.num_rows == receipt['vertices']['rows']
    assert np.count_nonzero(present) == receipt['vertices']['unique_nonnull_ids']
    edge_rows = self_loops = 0
    for batch in edges.iter_batches(batch_size=32768, use_threads=False):
        values = []
        for column in batch.columns:
            assert column.null_count == 0
            ids = column.to_numpy(zero_copy_only=False)
            assert np.all((ids >= minimum) & (ids <= maximum))
            assert np.all(present[ids])
            values.append(ids)
        edge_rows += batch.num_rows
        self_loops += int(np.count_nonzero(values[0] == values[1]))
    assert edge_rows == edges.metadata.num_rows == receipt['edges']['rows']
    assert self_loops == receipt['edges']['self_loops'] == 0
    assert receipt['duplicate_edges'] == {'measured': False, 'count': None}
    for item in receipt['downloads']:
        assert info(private / item['name']) == {k: item[k] for k in ('bytes', 'sha256')}
    assert info(ROOT / 'receipt.json') == original
    assert all(info(ROOT / name) == expected for name, expected in before.items())
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
        outcome='PASS_INDEPENDENT_LOCAL_INPUT_AUDIT', receipt=original,
        auditor=info(Path(__file__)), python=sys.version, pyarrow=pa.__version__,
        numpy=np.__version__, vertex_rows=rows, edge_rows=edge_rows,
        nulls=0, duplicate_vertex_rows=0, missing_endpoint_rows=0,
        self_loops=self_loops, presence_bitmap_bytes=present.nbytes,
        peak_process_rss_bytes=int(peak if platform.system() == 'Darwin' else peak * 1024),
        scope='Rehashed private originals and all receipt inputs; independently streamed full rows with a presence bitmap. No network, engine, remote work, benchmark, duplicate-edge count, historical-byte identity or correctness-result claim.')
    with (ROOT / 'independent-audit.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(result['outcome'])


if __name__ == '__main__':
    main()
