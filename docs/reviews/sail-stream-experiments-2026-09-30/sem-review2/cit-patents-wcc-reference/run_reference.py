#!/usr/bin/env python3
"""Compute a private exact WCC reference from the already pinned official pair."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time

for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_MAX_THREADS'):
    os.environ[key] = '1'
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
INPUT_RECEIPT_SHA = '56bb99e72d5b1c16bebc74e847d77d680131d58f5e03e6f10fb2f85b1123221e'
BATCH_ROWS = 65536
RSS_GUARD = 512 * 1024 * 1024


def info(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1<<20):h.update(block)
    return dict(bytes=path.stat().st_size,sha256=h.hexdigest())


def peak():
    value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    value=int(value if platform.system()=='Darwin' else value*1024)
    if value>RSS_GUARD:raise RuntimeError('observed Python RSS guard exceeded')
    return value


def stage(path, target, fields, expected_rows, low, high):
    file=pq.ParquetFile(path,memory_map=False,pre_buffer=False)
    assert file.schema_arrow.names==fields and all(f.type==pa.int64() for f in file.schema_arrow)
    assert file.metadata.num_rows==expected_rows
    assert max(file.metadata.row_group(i).total_byte_size for i in range(file.num_row_groups))<=128*1024*1024
    rows=0
    with target.open('xb') as stream:
        for batch in file.iter_batches(batch_size=BATCH_ROWS,use_threads=False):
            arrays=[]
            for column in batch.columns:
                assert column.null_count==0
                values=column.to_numpy(zero_copy_only=False)
                assert np.all((values>=low)&(values<=high))
                arrays.append(values)
            values=arrays[0] if len(arrays)==1 else np.column_stack(arrays)
            stream.write(values.astype('<i8',copy=False).tobytes(order='C'))
            rows+=batch.num_rows;peak()
    assert rows==expected_rows and target.stat().st_size==rows*len(fields)*8
    return dict(rows=rows,columns=fields,path=str(target),**info(target))


def chunks(path, columns):
    with path.open('rb') as stream:
        while block:=stream.read(BATCH_ROWS*columns*8):
            assert len(block)%(columns*8)==0
            yield np.frombuffer(block,dtype='<i8').reshape(-1,columns)


def readback(vertices, edges, output, low, high, n, m, stats):
    present=np.zeros(high+1,dtype=np.bool_)
    labels=np.zeros(high+1,dtype=np.uint32)
    counts=np.zeros(high+1,dtype=np.uint32)
    incident=np.zeros(high+1,dtype=np.bool_)
    for batch in chunks(vertices,1):
        ids=batch[:,0];assert np.all((ids>=low)&(ids<=high))
        assert np.unique(ids).size==ids.size and not np.any(present[ids]);present[ids]=True;peak()
    assert np.count_nonzero(present)==n
    previous=0;rows=0
    for batch in chunks(output,2):
        ids,components=batch[:,0],batch[:,1]
        assert np.all((ids>=low)&(ids<=high)) and np.all(present[ids])
        assert ids[0]>previous and np.all(ids[1:]>ids[:-1]);previous=int(ids[-1])
        assert np.all((components>=low)&(components<=ids))
        labels[ids]=components.astype(np.uint32,copy=False)
        np.add.at(counts,components,1);rows+=len(ids);peak()
    assert rows==n and np.count_nonzero(labels)==n and int(counts.sum(dtype=np.uint64))==n
    for batch in chunks(output,2):
        components=batch[:,1];assert np.all(labels[components]==components);peak()
    edge_rows=loops=0
    for batch in chunks(edges,2):
        sources,targets=batch[:,0],batch[:,1]
        assert np.all(present[sources]) and np.all(present[targets])
        assert np.all(labels[sources]==labels[targets])
        incident[sources]=True;incident[targets]=True
        loops+=int(np.count_nonzero(sources==targets));edge_rows+=len(batch);peak()
    largest=int(counts.max(initial=0))
    observed=dict(output_rows=rows,component_count=int(np.count_nonzero(counts)),largest_component_vertices=largest,
        largest_component_minimum_id=int(np.flatnonzero(counts==largest)[0]) if largest else 0,
        isolated_vertices_without_incident_edges=int(np.count_nonzero(present&~incident)),
        singleton_components=int(np.count_nonzero(counts==1)),self_loop_edge_rows=loops,edge_rows=edge_rows)
    assert edge_rows==m
    for key,value in observed.items():assert stats[key]==value,(key,stats[key],value)
    return dict(checks=observed,scope='Full output domain/order/representative/count checks and all-edge label consistency. Connectivity/no-false-merge construction is the tested union-find; this readback is not an independent second full-graph WCC algorithm.')


def main():
    input_receipt_path,build_path,out=map(Path,sys.argv[1:4])
    out.mkdir(parents=True,exist_ok=True)
    source_files={p.name:info(p) for p in (HERE/'wcc_reference.cpp',HERE/'test_reference.py',HERE/'run_reference.py',HERE/'build_reference.py')}
    assert info(input_receipt_path)['sha256']==INPUT_RECEIPT_SHA
    inputs=json.loads(input_receipt_path.read_text());build=json.loads(build_path.read_text())
    assert build['outcome']=='PASS_FROZEN_KERNEL_BUILD_AND_CONTROLS'
    for name in ('wcc_reference.cpp','test_reference.py'):assert source_files[name]==build['source_files'][name]
    binary=Path(build['binary']['path']);assert info(binary)=={k:build['binary'][k] for k in ('bytes','sha256')}
    control_path=build_path.parent/'controls.json';assert info(control_path)==build['controls']
    controls=json.loads(control_path.read_text());assert controls['outcome']=='PASS_PRODUCTION_KERNEL_BFS_CONTROLS'
    assert controls['binary']==info(binary)
    private=Path(build['private_directory'])/'production';private.mkdir(exist_ok=False)
    assert shutil.disk_usage(private).free>2*(1<<30)
    original=Path(inputs['private_original_directory']);assert not original.is_symlink()
    original_before={}
    for item in inputs['downloads']:
        path=original/item['name'];assert not path.is_symlink()
        original_before[item['name']]=info(path)
        assert original_before[item['name']]=={k:item[k] for k in ('bytes','sha256')}
    receipt=dict(started_utc=datetime.now(timezone.utc).isoformat(),outcome='STARTED',input_receipt=dict(path=str(input_receipt_path),**info(input_receipt_path)),build_receipt=dict(path=str(build_path),**info(build_path)),originals_before=original_before,source_files=source_files,private_directory=str(private),binary=build['binary'],python=sys.version,python_executable=sys.executable,pyarrow=pa.__version__,numpy=np.__version__,platform=platform.platform(),thread_environment={k:os.environ[k] for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_MAX_THREADS')})
    started=time.monotonic()
    try:
        pa.set_cpu_count(1);pa.set_io_thread_count(1)
        low,high=inputs['vertices']['minimum'],inputs['vertices']['maximum']
        n,m=inputs['vertices']['rows'],inputs['edges']['rows']
        assert (low,high,n,m)==(1,6009554,3774768,16518947)
        vertices,edges,output=private/'vertices.i64le',private/'edges.i64le',private/'wcc-membership.i64le'
        staged=[stage(original/'cit-Patents-v.parquet',vertices,['id'],n,low,high),stage(original/'cit-Patents-e.parquet',edges,['source','target'],m,low,high)]
        before=[info(vertices),info(edges)]
        command=[str(binary),str(vertices),str(edges),str(output),str(low),str(high),str(n),str(m),'positive-range-wcc-v1']
        result=subprocess.run(command,capture_output=True,text=True)
        with (out/'kernel.stdout').open('x') as stream:stream.write(result.stdout)
        with (out/'kernel.stderr').open('x') as stream:stream.write(result.stderr)
        receipt.update(kernel_command=command,kernel_returncode=result.returncode,staged_inputs=staged)
        result.check_returncode();stats=json.loads(result.stdout)
        assert stats['vertex_rows']==stats['output_rows']==n and stats['edge_rows']==m
        assert stats['peak_process_rss_bytes']<RSS_GUARD
        checked=readback(vertices,edges,output,low,high,n,m,stats)
        assert before==[info(vertices),info(edges)]
        assert output.stat().st_size==n*16
        assert info(binary)=={k:build['binary'][k] for k in ('bytes','sha256')}
        assert source_files=={name:info(HERE/name) for name in source_files}
        originals_after={name:info(original/name) for name in original_before};assert originals_after==original_before
        assert info(input_receipt_path)=={k:receipt['input_receipt'][k] for k in ('bytes','sha256')}
        assert peak()+stats['peak_process_rss_bytes'] < 1<<30
        receipt.update(outcome='PASS_EXACT_WCC_REFERENCE_PREPARATION',originals_after=originals_after,kernel=stats,readback=checked,reference_output=dict(path=str(output),format='Headerless ascending signed-i64 (vertex_id, minimum_component_id), little-endian, 16 bytes per declared vertex',**info(output)),python_peak_process_rss_bytes=peak(),limits=dict(observed_rss_guard_bytes=RSS_GUARD,hard_os_rss_cap=False,batch_rows=BATCH_ROWS,arrow_cpu_threads=1,arrow_io_threads=1,parquet_use_threads=False,execution='Single-thread stages run sequentially: Parquet staging, C++ union-find, Python readback. Python waits while the single-thread C++ kernel computes.'),contract='Weak connectivity: each supplied edge joins its two declared endpoints regardless of direction. Every declared vertex is emitted, including isolated vertices. No input mutation, symmetrization, edge deduplication or duplicate-edge count. Private uint32 indexing is valid only for this checked positive ID range; public oracle IDs/labels are signed i64.',scope='New exact reference input preparation for a future shared-input pilot. No Sail/GraphFrames/other engine benchmark, Stage A result, historical-byte identity, timing comparison or cluster qualification. Original Parquet and generated binary files remain private; only code, counts, hashes and receipts are public.')
    except BaseException as error:
        receipt.update(outcome='FAILED',error=repr(error));raise
    finally:
        try:
            receipt['originals_after']={name:info(original/name) for name in original_before}
            receipt['originals_unchanged']=receipt['originals_after']==original_before
            if not receipt['originals_unchanged']:
                receipt.update(outcome='FAILED',original_integrity_error='original input hash changed')
        except OSError as error:
            receipt.update(outcome='FAILED',original_integrity_error=repr(error))
        receipt.update(finished_utc=datetime.now(timezone.utc).isoformat(),preparation_elapsed_seconds=time.monotonic()-started)
        with (out/'receipt.json').open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
    assert receipt['outcome']=='PASS_EXACT_WCC_REFERENCE_PREPARATION', receipt
    print(json.dumps(dict(outcome=receipt['outcome'],component_count=stats['component_count'],largest_component_vertices=stats['largest_component_vertices'],reference_sha256=receipt['reference_output']['sha256'])))

if __name__=='__main__':main()
