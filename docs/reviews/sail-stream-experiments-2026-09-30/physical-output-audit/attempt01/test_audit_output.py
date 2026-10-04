"""Offline controls; all Parquet fixture bodies stay in pytest's private temp root."""
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import audit_output as audit


def valid():
    return {'id': list(range(8)), 'distance': [0.] + [.5] * 6 + [None],
            'parent': [0] * 7 + [None], 'hops': [0] + [1] * 6 + [None]}


def table(data):
    return pa.table({key: pa.array(value, type=audit.SCHEMA[key]) for key, value in data.items()})


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def fixture(tmp_path, data=None, outcome='passed', split=False):
    result = tmp_path / 'result'
    result.mkdir()
    payload = table(data or valid())
    if split:
        pq.write_table(payload.slice(0, 1), result / 'part0.parquet')
        pq.write_table(payload.slice(1), result / 'part1.parquet')
    else:
        pq.write_table(payload, result / 'part0.parquet')
    now = datetime.now(timezone.utc).isoformat()
    receipt = dict(started_utc=now, finished_utc=now, outcome=outcome,
                   harness_source_sha=audit.PRODUCER, runtime_source_sha='test-runtime',
                   arguments=dict(output='/targets/exact-cell', algorithm='sssp', engine='pecan',
                                  variant='delta_star', expected_vertices=8, source=0),
                   dataset=dict(family='traversal', counts=dict(vertices=8),
                                purpose='bounded correctness fixture; not a Graph500 input'),
                   result_files=[dict(name=p.name, bytes=p.stat().st_size, sha256=audit.sha256(p))
                                 for p in sorted(result.glob('*.parquet'))])
    args = SimpleNamespace(receipt=tmp_path/'receipt.json', receipt_sha256=None,
                           closure_audit=tmp_path/'closure.json', closure_sha256=None,
                           result_dir=result, expected_cell_output='/targets/exact-cell',
                           expected_vertices=8, expected_source=0)
    repin(args, receipt)
    return args


def repin(args, receipt):
    dump(args.receipt, receipt)
    args.receipt_sha256 = audit.sha256(args.receipt)
    closure = dict(integrity_status='integrity_verified', helper_sha256=audit.CLOSED_HELPER,
                   errors=[], inconclusive_reasons=[],
                   files={'cell/diagnostics/receipt.json': dict(sha256=args.receipt_sha256,
                                                               bytes=args.receipt.stat().st_size)},
                   recorded_outcomes=dict(receipt_outcome=receipt['outcome'],
                                          producer_finished_utc=receipt['finished_utc'],
                                          docker_state=dict(Running=False, Status='exited',
                                                            FinishedAt=receipt['finished_utc'])))
    dump(args.closure_audit, closure)
    args.closure_sha256 = audit.sha256(args.closure_audit)


def test_valid_unreachable_and_signed_zero(tmp_path):
    data = valid()
    data['distance'][0] = -0.
    result = audit.audit(fixture(tmp_path, data))
    assert result['status'] == 'physical_values_pass', result
    assert result['counts']['rows'] == result['counts']['unique_ids'] == 8
    assert result['counts']['unreachable_rows'] == 1
    assert result['identities_unchanged']
    assert result['files'][0]['before'] == result['files'][0]['after']


def test_default_statistics_nan_and_finite_payload_is_rejected(tmp_path):
    data = valid()
    data['distance'][1] = float('nan')
    args = fixture(tmp_path, data, split=True)
    column = pq.ParquetFile(args.result_dir/'part1.parquet').metadata.row_group(0).column(1)
    assert column.statistics.min == column.statistics.max == .5
    result = audit.audit(args)
    assert result['status'] == 'physical_values_fail', result
    assert result['counts']['nan_distance'] == 1
    assert result['counts']['rows'] == 8
    assert result['identities_unchanged']


@pytest.mark.parametrize('value,counter', [(float('inf'), 'positive_infinity_distance'),
                                         (-float('inf'), 'negative_infinity_distance'),
                                         (-.5, 'negative_finite_distance')])
def test_invalid_distances(tmp_path, value, counter):
    data = valid()
    data['distance'][1] = value
    result = audit.audit(fixture(tmp_path, data))
    assert result['status'] == 'physical_values_fail'
    assert result['counts'][counter] == 1


@pytest.mark.parametrize('column,index,value,counter', [
    ('parent', 7, 0, 'unreachable_with_metadata'), ('hops', 7, 0, 'unreachable_with_metadata'),
    ('parent', 1, None, 'reached_null_parent'), ('hops', 1, None, 'reached_null_hops'),
    ('id', 1, None, 'null_ids'), ('id', 1, 8, 'ids_out_of_domain'),
    ('id', 1, 2, 'duplicate_ids'), ('parent', 1, 8, 'parent_out_of_domain'),
    ('hops', 1, -1, 'hops_out_of_range'), ('hops', 1, 8, 'hops_out_of_range'),
    ('hops', 1, 0, 'nonroot_reached_zero_hops'), ('distance', 0, .5, 'invalid_root'),
])
def test_domain_and_null_contract(tmp_path, column, index, value, counter):
    data = valid()
    data[column][index] = value
    result = audit.audit(fixture(tmp_path, data))
    assert result['status'] == 'physical_values_fail', result
    assert result['counts'][counter] == 1


def test_wrong_hash(tmp_path):
    args = fixture(tmp_path)
    receipt = json.loads(args.receipt.read_text())
    receipt['result_files'][0]['sha256'] = '0' * 64
    repin(args, receipt)
    assert audit.audit(args)['status'] == 'integrity_error'


def test_wrong_rows(tmp_path):
    data = {key: value[:-1] for key, value in valid().items()}
    result = audit.audit(fixture(tmp_path, data))
    assert result['status'] == 'physical_values_fail'
    assert result['counts']['missing_ids'] == 1
    assert result['counts']['rows'] == 7


def test_wrong_schema(tmp_path):
    args = fixture(tmp_path)
    payload = table(valid()).set_column(1, 'distance', pa.array([0.] + [.5] * 6 + [None], type=pa.float32()))
    path = args.result_dir/'part0.parquet'
    pq.write_table(payload, path)
    receipt = json.loads(args.receipt.read_text())
    receipt['result_files'][0].update(bytes=path.stat().st_size, sha256=audit.sha256(path))
    repin(args, receipt)
    assert audit.audit(args)['status'] == 'integrity_error'


@pytest.mark.parametrize('missing', ['closure', 'file', 'inventory'])
def test_missing_evidence_is_inconclusive(tmp_path, missing):
    args = fixture(tmp_path)
    if missing == 'closure':
        args.closure_audit.unlink()
    elif missing == 'file':
        (args.result_dir/'part0.parquet').unlink()
    else:
        receipt = json.loads(args.receipt.read_text())
        del receipt['result_files']
        repin(args, receipt)
    assert audit.audit(args)['status'] == 'inconclusive'


def test_failed_producer_is_not_promoted(tmp_path):
    result = audit.audit(fixture(tmp_path, outcome='error'))
    assert result['status'] == 'physical_values_pass'
    assert result['producer_outcome'] == 'error'
    assert 'certificate replacement' in result['scope']


def test_wrong_namespace_and_receipt_binding(tmp_path):
    args = fixture(tmp_path)
    args.expected_cell_output = '/targets/other-cell'
    assert audit.audit(args)['status'] == 'integrity_error'
    args.expected_cell_output = '/targets/exact-cell'
    closure = json.loads(args.closure_audit.read_text())
    closure['files']['cell/diagnostics/receipt.json']['sha256'] = '0' * 64
    dump(args.closure_audit, closure)
    args.closure_sha256 = audit.sha256(args.closure_audit)
    assert audit.audit(args)['status'] == 'integrity_error'


def test_basename_collision_rejected(tmp_path):
    args = fixture(tmp_path)
    nested = args.result_dir/'nested'
    nested.mkdir()
    (nested/'part0.parquet').write_bytes((args.result_dir/'part0.parquet').read_bytes())
    assert audit.audit(args)['status'] == 'integrity_error'


def test_post_scan_mutation_rejected(tmp_path, monkeypatch):
    args = fixture(tmp_path)
    original = audit.scan_file
    def mutate(*arguments):
        rows = original(*arguments)
        changed = valid()
        changed['distance'][1] = .75
        pq.write_table(table(changed), args.result_dir/'part0.parquet')
        return rows
    monkeypatch.setattr(audit, 'scan_file', mutate)
    result = audit.audit(args)
    assert result['status'] == 'integrity_error', result
    assert not result.get('identities_unchanged')
