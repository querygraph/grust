"""Prepared host runner: launch only when the coordinator schedules this control.

Uses the unchanged 3a benchmark's preflight/container supervisor. A pinned 561
build may occupy CPU0-15; this control uses CPU16-23 and 12GiB. No other workload
is allowed. No bootstrap, dataset preparation, cache deletion or source edits.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('configuration', type=Path)
    args = parser.parse_args()
    configuration = args.configuration.resolve()
    config = json.loads(configuration.read_text())
    root = configuration.parent.parent
    probe = configuration.parent / 'probe.py'
    assert digest(probe) == config['probe_sha256']
    harness = root / 'harness'
    assert digest(harness / 'run_matrix.py') == config['host_matrix_sha256']
    assert config['limits'] == dict(cpus=8, cpuset_cpus='16-23', memory_gib=12, outer_timeout_seconds=360)
    os.environ['PATH'] = '/usr/local/bin:/opt/homebrew/bin:' + os.environ.get('PATH', '')
    sys.path.insert(0, str(harness))
    import run_matrix as matrix
    docker = ['/usr/local/bin/docker', '--context', config['docker_context']]
    active = subprocess.check_output(docker + ['ps', '--format', '{{.Names}}'], text=True).splitlines()
    overlap = []
    for name in active:
        assert name == 'sail-stream-build561-host', ('unexpected active container', name)
        record = json.loads(subprocess.check_output(docker + ['inspect', name], text=True))[0]
        assert record['Image'] == config['image']
        assert record['HostConfig']['CpusetCpus'] == '0-15'
        assert record['HostConfig']['Memory'] == 48 * (1 << 30)
        overlap.append(dict(name=name, id=record['Id'], state=record['State'],
                            limits={k: record['HostConfig'].get(k) for k in ('CpusetCpus', 'Memory', 'NanoCpus')}))
    output = Path(config['host_output'])
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'configuration.json', config)
    command = ['-I', '-B', '-c', probe.read_text(), json.dumps(config)]
    save(output / 'plan.json', dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
                                   probe_sha256=digest(probe), configuration_sha256=digest(configuration),
                                   concurrent_builds=overlap, command=command,
                                   scope='Tiny correctness/plan control on a shared host, not a performance benchmark.'))
    image = matrix.preflight(config, output)
    record = matrix.run_container(config, 'sail-' + config['run_id'], command,
        output / 'cell', image, config['limits']['outer_timeout_seconds'], {'diagnostics': config['probe_output']})
    receipt_path = output / 'cell/diagnostics/receipt.json'
    receipt = None
    try:
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
    except (OSError, ValueError) as error:
        record['receipt_read_error'] = repr(error)
    outcome = matrix.classify(record, receipt, config['harness_source_sha'])
    files = {str(path.relative_to(output)): digest(path) for path in sorted(output.rglob('*')) if path.is_file()}
    save(output / 'collection.json', dict(collected_utc=datetime.now(timezone.utc).isoformat(), sha256=files))
    result = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome=outcome,
                  receipt_outcome=receipt.get('outcome') if receipt else None,
                  output=str(output), full_volume_artifacts=config['probe_output'],
                  scope='Production one-step representatives and physical plans; not complete WCC or timing evidence.')
    save(output / 'result.json', result)
    print(json.dumps(result))
    return 0 if outcome == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
