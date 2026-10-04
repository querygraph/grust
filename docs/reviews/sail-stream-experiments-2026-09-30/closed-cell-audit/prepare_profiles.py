#!/usr/bin/env python3
"""Freeze local known source/data/artifact identities; no runtime/remote operations."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent

def load(name):
    return json.loads((ROOT/name).read_text())

def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def pin(name):
    return {'path': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest()}

def main():
    native = 'pecan-gate3/measured-1-base/diagnostics/receipt.json'
    graph500 = 'logging01/diagnostics/receipt.json'
    weighted = native
    specs = {
        'logging01': ('logging01.json', graph500, None),
        'compact561-smoke': ('worker-smoke-compact561-cpu16-23.json', weighted, 'linux-builds/compact561-host/final/rebuild-receipt.json'),
        'logging02': ('logging02.json', graph500, 'linux-builds/integration289/final/rebuild-receipt.json'),
        'logging03': ('logging03-compact.json', graph500, 'linux-builds/compact561-host/final/rebuild-receipt.json'),
    }
    cases = {}
    for name, (config_name, dataset, build) in specs.items():
        cfg = load(config_name); reference = load(dataset)
        if build:
            built = load(build)
            assert built['outcome'] == 'passed' and built['source_sha'] == cfg['runtime_source_sha']
            binary = built['host']['sha256']
            assert built['host']['path'] == cfg['container_sail_binary']
        else:
            assert reference['runtime_source_sha'] == cfg['runtime_source_sha']
            binary = reference['binary_sha256']
        identity = load(native)['native_package_identity']
        cases[name] = dict(config_path=config_name, binary_sha256=binary,
            native_identity_canonical_sha256=canonical(identity),
            dataset_canonical_sha256=canonical(reference['dataset']),
            resolved_dataset_path=reference['arguments']['dataset'],
            evidence_pins=[pin(p) for p in sorted({config_name, dataset, native} | ({build} if build else set()))],
            scope='Recorded identity agreement with pinned local evidence, not a remote artifact hash recomputation. logging01 itself supplies the retained Graph500 manifest identity. Native baseline supplies the unchanged package inventory.')
    report = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), cases=cases,
        profiles_scope='Original 3a controller and original ffcf native for these four configurations only; no new workload. These identities do not establish correctness or dedicated-host timing.')
    with (OUT/'profiles.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2)+'\n')

if __name__ == '__main__':
    main()
