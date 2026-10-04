#!/usr/bin/env python3
"""Run bounded isolated allocation cells after the frozen-source gate passes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parent
BINARY = Path('/private/tmp/min-by-allocation-target/release/ordered-last-value-allocation-probe')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = json.loads((ROOT / 'source-receipt.json').read_text())
    gate = Path(source['gate'])
    probe = Path(source['probe_source'])

    def guard():
        assert subprocess.check_output(['git', '-C', str(gate), 'rev-parse', 'HEAD'], text=True).strip() == source['gate_detached_base']
        assert subprocess.run(['git', '-C', str(gate), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
        for name, expected in source['source_sha256'].items():
            assert digest(probe / name) == expected, name
            assert digest(ROOT / name) == expected, name

    guard()
    assert not (ROOT / 'allocation-receipt.json').exists()
    receipt = dict(started_utc=datetime.now(timezone.utc).isoformat(),
        host=platform.node(), platform=platform.platform(),
        binary=str(BINARY), binary_sha256=digest(BINARY),
        source_receipt_sha256=digest(ROOT / 'source-receipt.json'),
        runner_sha256=digest(Path(__file__)), trials=[],
        scope='Single-process requested System allocation counts; shared laptop times exploratory only. Source-derived Sail rewrite; no production physical plan, Linux workload, throughput or whole-query attribution.')
    try:
        for groups in (1000, 10000, 100000):
            stdout = ROOT / f'groups-{groups}.jsonl'
            stderr = ROOT / f'groups-{groups}.stderr'
            command = [str(BINARY), str(groups)]
            trial = dict(groups=groups, command=command,
                         started_utc=datetime.now(timezone.utc).isoformat())
            receipt['trials'].append(trial)
            try:
                with stdout.open('x') as out, stderr.open('x') as err:
                    result = subprocess.run(command, stdout=out, stderr=err, timeout=60)
                trial['exit_code'] = result.returncode
                result.check_returncode()
                rows = [json.loads(line) for line in stdout.read_text().splitlines()]
                assert rows[-1] == {'checks': 'passed', 'groups': groups}
                assert rows[0]['sizeof_inner_vec'] == 24
                guard()
                trial['outcome'] = 'passed'
            except Exception as error:
                trial.update(outcome='failed', error_type=type(error).__name__, error=str(error))
                raise
            finally:
                trial.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                             stdout_sha256=digest(stdout) if stdout.exists() else None,
                             stderr_sha256=digest(stderr) if stderr.exists() else None)
        receipt['outcome'] = 'passed'
    except Exception:
        receipt['outcome'] = 'failed'
        raise
    finally:
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with (ROOT / 'allocation-receipt.json').open('x') as output:
            output.write(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'outcome': 'passed', 'trials': len(receipt['trials']), 'receipt_sha256': digest(ROOT / 'allocation-receipt.json')}, indent=2))


if __name__ == '__main__':
    main()
