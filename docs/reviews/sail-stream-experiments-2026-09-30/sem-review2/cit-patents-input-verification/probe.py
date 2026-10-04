#!/usr/bin/env python3
"""Bounded local download and streaming validation of official cit-Patents inputs.

Writes original Parquet only under a fresh private directory; publishes receipts,
not data. This does not establish historical byte identity or benchmark results.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

HOST = 'datasets.ldbcouncil.org'
PREFIX = 'https://' + HOST + '/graphalytics-parquet/'
NAMES = ('cit-Patents-v.parquet', 'cit-Patents-e.parquet')
DOWNLOAD_CAP = 128 * 1024**2
VERTEX_ARRAY_CAP = 128 * 1024**2
ROW_GROUP_CAP = 128 * 1024**2
RSS_CAP = 1024**3
BATCH = 65536
HEADER_KEYS = ('content-length', 'content-type', 'content-encoding', 'etag',
               'last-modified', 'date', 'server', 'accept-ranges',
               'content-md5', 'digest', 'x-amz-version-id', 'x-goog-generation')


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    value['recorded_utc'] = now()
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def check_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != HOST or parsed.query
            or parsed.fragment or parsed.path not in
            ('/graphalytics-parquet/' + name for name in NAMES)):
        raise ValueError('unexpected source URL; only exact official pair admitted')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Fail before making a request to an unreviewed redirect destination.
        raise ValueError('redirect rejected: HTTP ' + str(code))


def headers(response):
    return {key: response.headers[key] for key in HEADER_KEYS
            if response.headers.get(key) is not None}


def admit_response(response, remaining):
    check_url(response.geturl())
    if response.status != 200:
        raise ValueError('expected HTTP200, got ' + str(response.status))
    kind = response.headers.get('Content-Type', '').lower()
    if 'html' in kind or kind.startswith('text/'):
        raise ValueError('unexpected HTML/text content type')
    encoding = response.headers.get('Content-Encoding', 'identity').lower()
    if encoding not in ('', 'identity'):
        raise ValueError('encoded HTTP response rejected')
    length = int(response.headers['Content-Length'])
    if length < 8 or length > remaining:
        raise ValueError('Content-Length exceeds remaining combined cap or is invalid')
    return length


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if platform.system() == 'Darwin' else value * 1024)


def check_memory():
    if peak_rss_bytes() > RSS_CAP:
        raise MemoryError('observed peak RSS exceeded 1GiB validation envelope')


def download(private, inventory):
    admitted = set(json.loads(inventory.read_text())['urls'])
    opener = urllib.request.build_opener(NoRedirect)
    result = {'outcome': 'RUNNING', 'download_cap_bytes': DOWNLOAD_CAP,
              'received_bytes': 0, 'objects': [], 'inventory_path': str(inventory),
              'inventory_sha256': digest(inventory), 'started_utc': now(),
              'private_directory': str(private)}
    try:
        for name in NAMES:
            url = PREFIX + name
            assert url in admitted
            check_url(url)
            item = {'name': name, 'url': url, 'started_utc': now(),
                    'received_bytes': 0, 'outcome': 'RUNNING'}
            result['objects'].append(item)
            request = urllib.request.Request(url, headers={
                'User-Agent': 'querygraph-input-verification/1',
                'Accept-Encoding': 'identity'})
            path = private / (name + '.partial')
            try:
                with opener.open(request, timeout=45) as response:
                    item.update(final_url=response.geturl(), status=response.status,
                                headers=headers(response))
                    length = admit_response(response, DOWNLOAD_CAP-result['received_bytes'])
                    with path.open('xb') as f:
                        while item['received_bytes'] < length:
                            # Never request bytes beyond declared length or aggregate cap.
                            remaining = min(length-item['received_bytes'],
                                            DOWNLOAD_CAP-result['received_bytes'])
                            if remaining <= 0:
                                raise ValueError('aggregate download cap exhausted')
                            chunk = response.read(min(65536, remaining))
                            if not chunk:
                                raise ValueError('body shorter than Content-Length')
                            f.write(chunk)
                            item['received_bytes'] += len(chunk)
                            result['received_bytes'] += len(chunk)
                        f.flush()
                    assert item['received_bytes'] == length
                with path.open('rb') as f:
                    first = f.read(4)
                    f.seek(-4, 2)
                    last = f.read(4)
                if first != b'PAR1' or last != b'PAR1':
                    raise ValueError('Parquet magic missing; original body retained privately')
                final = private / name
                path.rename(final)
                item.update(outcome='DOWNLOADED', bytes=final.stat().st_size,
                            sha256=digest(final), private_path=str(final))
            except Exception as error:
                if isinstance(error, urllib.error.HTTPError):
                    item.update(status=error.code, headers=headers(error),
                                final_url=error.geturl())
                item.update(outcome='FAILED', error_type=type(error).__name__,
                            error=str(error), partial_path=str(path) if path.exists() else None)
                if path.exists():
                    item.update(partial_bytes=path.stat().st_size, partial_sha256=digest(path))
                raise
            finally:
                item['finished_utc'] = now()
        result['outcome'] = 'DOWNLOADED_OFFICIAL_PAIR'
        return result
    except Exception as error:
        result.update(outcome='DOWNLOAD_FAILED', error_type=type(error).__name__, error=str(error))
        return result
    finally:
        result['finished_utc'] = now()


def validate(private, downloaded):
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    result = {'outcome': 'RUNNING', 'started_utc': now(),
              'runtime': {'python': sys.executable, 'python_version': platform.python_version(),
                          'pyarrow_version': pa.__version__, 'numpy_version': np.__version__,
                          'platform': platform.platform(), 'cpu_count_setting': pa.cpu_count(),
                          'io_thread_count_setting': pa.io_thread_count(),
                          'thread_environment': {key: os.environ.get(key) for key in
                              ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}},
              'bounds': {'batch_rows': BATCH, 'parquet_use_threads': False,
                         'pre_buffer': False, 'vertex_array_cap_bytes': VERTEX_ARRAY_CAP,
                         'row_group_uncompressed_cap_bytes': ROW_GROUP_CAP,
                         'observed_peak_rss_guard_bytes': RSS_CAP,
                         'rss_guard_is_hard_os_limit': False}, 'footers': [],
              'duplicate_edges': {'measured': False, 'count': None},
              'scope': 'Validation only; original files unchanged. No benchmark execution, historical byte-parity claim, graph symmetrization or deduplication.'}
    try:
        files = []
        for item in downloaded['objects']:
            path = private/item['name']
            assert digest(path) == item['sha256']
            file = pq.ParquetFile(path, memory_map=False, pre_buffer=False)
            metadata = file.metadata
            sizes = [metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups)]
            if max(sizes, default=0) > ROW_GROUP_CAP:
                raise MemoryError('footer row-group admission exceeds bounded decoding plan')
            result['footers'].append({'name':item['name'], 'sha256':item['sha256'],
                'rows':metadata.num_rows,'row_groups':metadata.num_row_groups,
                'maximum_row_group_uncompressed_bytes':max(sizes,default=0),
                'total_row_group_uncompressed_bytes':sum(sizes),
                'created_by':metadata.created_by,'parquet_format_version':metadata.format_version,
                'schema_arrow':str(file.schema_arrow),
                'schema_fields':[{'name':f.name,'type':str(f.type),'nullable':f.nullable}
                                 for f in file.schema_arrow]})
            files.append(file)
        vertices, edges = files
        if vertices.schema_arrow.field('id').type != pa.int64():
            raise TypeError('vertex id is not signed Int64')
        for name in ('source','target'):
            if edges.schema_arrow.field(name).type != pa.int64():
                raise TypeError('edge endpoint is not signed Int64')
        n = vertices.metadata.num_rows
        if n*8 > VERTEX_ARRAY_CAP:
            raise MemoryError('vertex cardinality exceeds admitted sorted-map size')
        ids = np.empty(n,dtype=np.int64)
        count = nulls = 0
        for batch in vertices.iter_batches(batch_size=BATCH,columns=['id'],use_threads=False):
            arr = batch.column(0)
            nulls += arr.null_count
            valid = arr.drop_null().to_numpy(zero_copy_only=False)
            ids[count:count+len(valid)] = valid
            count += len(valid)
            check_memory()
        assert count+nulls == n
        ids = ids[:count]
        ids.sort(kind='quicksort')  # Validation index only; original Parquet is never modified.
        duplicates = 0
        for start in range(1,count,BATCH):
            end = min(start+BATCH,count)
            duplicates += int(np.count_nonzero(ids[start:end] == ids[start-1:end-1]))
        result['vertices'] = {'rows':n,'nonnull_rows':count,'nulls':nulls,
            'duplicate_rows_after_first':duplicates,'unique_nonnull_ids':count-duplicates,
            'minimum':int(ids[0]) if count else None,'maximum':int(ids[-1]) if count else None,
            'validation_index_bytes':int(ids.nbytes)}
        weight = 'weight' in edges.schema_arrow.names
        if weight and not (pa.types.is_floating(edges.schema_arrow.field('weight').type)
                           or pa.types.is_integer(edges.schema_arrow.field('weight').type)):
            raise TypeError('unexpected nonnumeric weight column')
        stats = {'rows':0,'source_nulls':0,'target_nulls':0,
                 'missing_source_endpoint_rows':0,'missing_target_endpoint_rows':0,'self_loops':0}
        weights = {'present':weight,'nulls':0,'nonfinite':0,'negative':0,'zero':0,
                   'minimum_finite':None,'maximum_finite':None}
        for batch in edges.iter_batches(batch_size=BATCH,
                columns=['source','target']+(['weight'] if weight else []),use_threads=False):
            stats['rows'] += batch.num_rows
            arrays = {}
            for i,name in enumerate(('source','target')):
                arr=batch.column(i);stats[name+'_nulls']+=arr.null_count
                valid=arr.drop_null().to_numpy(zero_copy_only=False)
                positions=np.searchsorted(ids,valid)
                bounded=positions<len(ids)
                found=np.zeros(len(valid),dtype=bool)
                found[bounded]=ids[positions[bounded]]==valid[bounded]
                stats['missing_'+name+'_endpoint_rows']+=int(np.count_nonzero(~found))
                arrays[name]=arr
            # Arrow comparison preserves validity; NULL does not count as a self-loop.
            import pyarrow.compute as pc
            eq=pc.equal(arrays['source'],arrays['target'])
            stats['self_loops']+=int(pc.sum(eq).as_py() or 0)
            if weight:
                arr=batch.column(2);weights['nulls']+=arr.null_count
                values=arr.drop_null().to_numpy(zero_copy_only=False)
                finite=np.isfinite(values);weights['nonfinite']+=int(np.count_nonzero(~finite))
                values=values[finite]
                weights['negative']+=int(np.count_nonzero(values<0))
                weights['zero']+=int(np.count_nonzero(values==0))
                if len(values):
                    low,high=values.min().item(),values.max().item()
                    weights['minimum_finite']=low if weights['minimum_finite'] is None else min(low,weights['minimum_finite'])
                    weights['maximum_finite']=high if weights['maximum_finite'] is None else max(high,weights['maximum_finite'])
            check_memory()
        assert stats['rows']==edges.metadata.num_rows
        result.update(edges=stats,weights=weights)
        required = [nulls==0,duplicates==0,stats['source_nulls']==0,stats['target_nulls']==0,
                    stats['missing_source_endpoint_rows']==0,stats['missing_target_endpoint_rows']==0,
                    not weight or (weights['nulls']==0 and weights['nonfinite']==0)]
        result['checks_passed']=all(required)
        result['outcome']='VALIDATED_NEW_OFFICIAL_INPUT' if all(required) else 'INPUT_VALIDATION_FAILED'
        result['original_files_unchanged']=all(digest(private/x['name'])==x['sha256'] for x in downloaded['objects'])
        assert result['original_files_unchanged']
    except Exception as error:
        result.update(outcome='VALIDATION_ERROR',error_type=type(error).__name__,error=str(error))
    finally:
        result.update(finished_utc=now(),observed_peak_rss_bytes=peak_rss_bytes(),
                      peak_rss_source='getrusage(RUSAGE_SELF).ru_maxrss; bytes on macOS, KiB converted on Linux')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if list(args.output.glob('attempt-*.json')):
        raise SystemExit('use a new attempt/output directory; prior receipts must not be overwritten')
    private=Path(tempfile.mkdtemp(prefix='cit-patents-official-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-',dir='/private/tmp'))
    identity={'started_utc':now(),'private_directory':str(private),'probe_sha256':digest(Path(__file__)),
              'command':sys.argv,'scope':'Local official input preparation only; no Morrobay resources or benchmark'}
    write_json(args.output/'attempt-identity.json',identity)
    received=download(private,args.inventory)
    write_json(args.output/'attempt-download.json',received)
    print(json.dumps({'download':received['outcome'],'bytes':received['received_bytes'],'private':str(private)}),flush=True)
    if received['outcome']!='DOWNLOADED_OFFICIAL_PAIR':return 1
    validated=validate(private,received)
    write_json(args.output/'attempt-validation.json',validated)
    print(json.dumps({'validation':validated['outcome'],'peak_rss_bytes':validated['observed_peak_rss_bytes']}),flush=True)
    return 0 if validated['outcome']=='VALIDATED_NEW_OFFICIAL_INPUT' else 1


if __name__=='__main__':
    raise SystemExit(main())
