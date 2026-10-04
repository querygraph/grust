"""Retain the two review counterexamples against preserved attempt01, locally only."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    current_tests = load(ROOT / 'test_preparation.py', 'prepared_controls')
    before = load(ROOT / 'attempt01/supervise.py', 'before_supervisor')
    current_tests.s = before
    case = current_tests.Supervisor()
    code, receipt, _ = case.exercise('oom_exit_zero')
    assert code == 0 and receipt['container_state']['OOMKilled'] is True
    observations = dict(oom_exit_zero_with_inner_pass=dict(supervisor_returncode=code,
        OOMKilled=receipt['container_state']['OOMKilled'], physical_status=receipt['physical_status']))
    old_prepare = load(ROOT / 'attempt01/prepare.py', 'before_prepare')
    # Preserve the old function bytes, but use the actual experiment source root
    # to resolve the unchanged frozen config/helper during this local fixture.
    old_prepare.__file__ = str(ROOT / 'prepare.py')
    policy = current_tests.Policy(); policy.setUp()
    with tempfile.TemporaryDirectory(prefix='physical-copy-counterexample-') as directory:
        root = Path(directory); inputs = root / 'inputs'; inputs.mkdir()
        producer = inputs / 'receipt.json'; producer.write_text(json.dumps(policy.receipt))
        original_digest = sha(producer)
        closed = inputs / 'closed.json'
        policy.closed['files']['/diagnostics/receipt.json']['sha256'] = original_digest
        closed.write_text(json.dumps(policy.closed))
        bundle = root / 'bundle'
        original_copy = shutil.copyfile
        def mutation(src, dst):
            if Path(src) == producer:
                changed = dict(policy.receipt, outcome='error')
                producer.write_text(json.dumps(changed))
            return original_copy(src, dst)
        args = ['prepare.py', '--receipt', str(producer), '--receipt-sha256', original_digest,
            '--closure-audit', str(closed), '--closure-sha256', sha(closed), '--bundle', str(bundle)]
        with patch.object(sys, 'argv', args), patch.object(old_prepare.shutil, 'copyfile', side_effect=mutation), redirect_stdout(io.StringIO()):
            old_prepare.main()
        request = json.loads((bundle / 'request.json').read_text())
        sealed_digest = request['files']['producer-receipt.json']['sha256']
        assert sealed_digest != original_digest
        observations['copy_replacement_sealed'] = dict(request_written=True, supplied_sha256=original_digest,
            copied_sha256=sealed_digest, supplied_pin_preserved=False)
    report = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome='BOTH_ATTEMPT01_GAPS_REPRODUCED',
        script_sha256=sha(Path(__file__)), original_files={p.name: sha(p) for p in
            (ROOT / 'attempt01/supervise.py', ROOT / 'attempt01/prepare.py')}, observations=observations,
        scope='Mocked Docker and temporary synthetic receipts only. No Docker, SSH, package import, runtime or result scan. Private generated fixtures removed.')
    with (ROOT / 'review-reproductions.json').open('x') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(report['outcome'])


if __name__ == '__main__':
    main()
