#!/usr/bin/env python3
"""Prepare a sealed logging03 physical-check bundle locally; never contact Docker."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid

CONFIG = 'b28132996612b11edb77bb02019288e4a562db5e4d22c4430a6a8815a220aea0'
HELPER = '4c5fe87d0eb0b3f4aec3e70841bc7db968017f952dda6978840d101d2f2f7872'
CLOSED = 'c8d59db362136879bbd3a6efe8f527311849e3e0be18ddb64e6da996bdfcd318'
CELL = '/targets/sail-stream-experiments-20260930/logging03-compact/cells/stream-log03-compact-r1-scale24-pecan-sssp-delta_star'
BOOT = 'f5443bfc-c939-491a-a984-b73cc6d1cb20'
BINARY = '5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
NATIVE = 'eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def pinned(path, digest):
    need(path.is_file() and not path.is_symlink(), 'not a regular nonsymlink evidence file')
    need(sha(path) == digest, 'evidence SHA256 differs')
    value = json.loads(path.read_text())
    need(isinstance(value, dict), 'evidence must be an object')
    return value


def validate(config, receipt, closed, receipt_sha):
    need(closed.get('integrity_status') == 'integrity_verified' and closed.get('errors') == []
         and closed.get('inconclusive_reasons') == [] and closed.get('helper_sha256') == CLOSED,
         'closed-cell audit not complete with pinned helper')
    pins = closed.get('files', {})
    need(any(k.endswith('/diagnostics/receipt.json') and v.get('sha256') == receipt_sha
             for k, v in pins.items()), 'closed audit does not pin producer receipt')
    need(any(v.get('sha256') == CONFIG for v in pins.values()), 'closed audit does not pin exact config')
    recorded = closed.get('recorded_outcomes', {})
    state = recorded.get('docker_state', {})
    need(state.get('Running') is False and state.get('Status') == 'exited', 'producer not closed')
    need(receipt.get('outcome') not in (None, '', 'running', 'started'), 'producer not terminal')
    need(recorded.get('receipt_outcome') == receipt['outcome'], 'closure/producer outcomes differ')
    for key in ('runtime_source_sha', 'native_source_sha', 'harness_source_sha'):
        need(receipt.get(key) == config[key], key + ' differs')
    a = receipt.get('arguments', {})
    need(a.get('sail_binary') == config['container_sail_binary'], 'producer binary path differs')
    need(a.get('output') == CELL and a.get('engine') == 'pecan' and a.get('algorithm') == 'sssp'
         and a.get('variant') == 'delta_star', 'wrong producer/cell namespace')
    need(type(a.get('expected_vertices')) is int and a['expected_vertices'] == 16777216
         and type(a.get('source')) is int and a['source'] == 13507776, 'wrong domain/source')
    need(isinstance(receipt.get('result_files'), list) and bool(receipt['result_files']),
         'no completed physical output; preserve producer outcome, do not launch a scan')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('receipt', 'closure-audit', 'bundle'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('receipt-sha256', 'closure-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    own = Path(__file__).resolve().parent
    exp = own.parent
    config_path = exp / 'logging03-compact.json'
    config = pinned(config_path, CONFIG)
    receipt = pinned(args.receipt, args.receipt_sha256)
    closed = pinned(args.closure_audit, args.closure_sha256)
    validate(config, receipt, closed, args.receipt_sha256)
    helper = exp / 'physical-output-audit/audit_output.py'
    need(sha(helper) == HELPER, 'physical verifier differs')
    bundle = args.bundle.resolve()
    for source in (args.receipt.resolve().parent, args.closure_audit.resolve().parent, own, helper.parent):
        need(not bundle.is_relative_to(source), 'bundle must be outside evidence/source trees')
    bundle.mkdir(parents=False, exist_ok=False)
    sources = {'configuration.json': config_path, 'producer-receipt.json': args.receipt,
               'closed-audit.json': args.closure_audit, 'audit_output.py': helper,
               'container_check.py': own / 'container_check.py', 'supervise.py': own / 'supervise.py'}
    files = {}
    for name, source in sources.items():
        shutil.copyfile(source, bundle / name)
        files[name] = dict(sha256=sha(bundle / name), bytes=(bundle / name).stat().st_size)
    request = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), prepared_only=True,
        cell_output=CELL, expected_vertices=16777216, expected_source=13507776,
        config_sha256=CONFIG, files=files, boot_id=BOOT, binary_sha256=BINARY,
        native_path='/targets/graph-nuts-ffcfbd569/venv/lib/python3.12/site-packages/sail_nutmeg/_native.cpython-312-x86_64-linux-gnu.so',
        native_sha256=NATIVE, expected_python_version='3.12.14', expected_pyarrow='21.0.0', expected_numpy='2.5.3',
        container_name='physical-output-log03-' + uuid.uuid4().hex[:16], timeout_seconds=1800,
        limits=dict(cpus=1, memory_bytes=2147483648, memory_swap_bytes=2147483648, pids=64),
        scope='Prepared only. Physical value/domain check, not shortest paths, benchmark correctness, or timing. '
              'Interpreter/package versions are prior observed; current file hashes will be recorded, not claimed historical byte parity.')
    save(bundle / 'request.json', request)
    print(json.dumps(dict(bundle=str(bundle), request_sha256=sha(bundle / 'request.json'), launched=False)))


if __name__ == '__main__':
    main()
