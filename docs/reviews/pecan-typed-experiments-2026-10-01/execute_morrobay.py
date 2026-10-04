"""Execute the frozen serial plan; retain every outcome and stop on failure.

The first three cells were launched individually. This driver accepts them only
after checking their closed evidence. It never retries or removes an old lock.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import tarfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
HOST = pathlib.Path('/Users/alexy/src/sail-extensions-gates/pecan-typed-tests-20261001')
ARCHIVE = pathlib.Path('/Volumes/Apo/graph-tests/results/pecan-typed-20261001')
LOGS = pathlib.Path('/Volumes/Apo/graph-tests/logs/pecan-typed-20261001')
REPORT = HERE / 'morrobay-20261001'
SUPPORT = '0f378b86d2feaa93413d1fe573eef524c110f1c019f2dace955c22d1a8f5dc39'
HEADS = {'baseline': 'cab6bacc0ad0d1fc8b3070e9e4267e99751909fe',
         'candidate': '6ae2e43a903c2cee02da170465c922c72b76198e'}
PRELAUNCHED = {'typed-smoke-local', 'typed-smoke-process-cluster',
              'typed-warmup-local-baseline'}
DOCKER = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']


@dataclass(frozen=True, slots=True)
class Step:
    run_id: str
    kind: str
    mode: str
    revision: str
    role: str


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(path: pathlib.Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path: pathlib.Path, value: dict[str, Any]) -> None:
    with path.open('x') as stream:
        json.dump({'recorded_utc': utc(), **value}, stream, indent=2)
        stream.write('\n')


def audit(step: Step, output: pathlib.Path) -> dict[str, Any]:
    result = json.loads((output / 'result.json').read_text())
    producer = json.loads((output / 'diagnostics/receipt.json').read_text())
    collection = json.loads((output / 'collection.json').read_text())
    orchestration = json.loads((output / 'container/orchestration.json').read_text())
    args = producer['arguments' if step.kind == 'wcc' else 'options']
    assert result['run_id'] == step.run_id and args['mode'] == step.mode
    assert args['controller_sha'] == HEADS[step.revision]
    assert args['repo'] == '/targets/pecan-typed-tests-20261001/' + step.revision
    assert args['output'] == '/targets/pecan-typed-tests-20261001/cells/' + step.run_id
    assert result['outcome'] == producer['outcome'] == 'passed'
    assert result['source'] == HEADS[step.revision] and not result['lock_retained']
    state = result['container_state']
    assert state['ExitCode'] == 0 and state['Running'] is False and state['OOMKilled'] is False
    assert orchestration['inspect']['state'] == state
    assert orchestration['attach_returncode'] == 0 and orchestration['remove']['returncode'] == 0
    assert not orchestration['outer_timeout'] and not orchestration['transport_errors']
    assert not producer['cleanup_errors']
    assert collection['returncode'] == 0 and sha(output / 'diagnostics.tar') == collection['sha256']
    if step.kind == 'wcc':
        assert producer['correctness']['rows'] == 3774768
        assert producer['correctness']['unique'] == 3774768
        assert producer['correctness']['membership_mismatches'] == 0
        assert producer['correctness']['components'] == 3627
        assert producer['inputs_before'] == producer['inputs_after']
        assert producer['identities']['before'] == producer['identities']['after']
        assert not producer['rounds']['incomplete_rounds']
        assert producer['memory']['error'] is None and not producer['staging_files_after_shutdown']
        assert producer['error'] is None and producer['integrity_error'] is None
        events = dict(line.split() for line in producer['cgroups']['after']['memory.events'].splitlines())
        assert int(events['oom']) == int(events['oom_kill']) == 0
    assert not (HOST / 'cell.lock').exists()
    closed = subprocess.run(DOCKER + ['ps', '-aq', '--filter', 'name=^/sail-' + step.run_id + '$'],
                            capture_output=True, text=True, timeout=30, check=True)
    assert not closed.stdout.strip(), 'cell container still exists'
    idle = subprocess.run(DOCKER + ['ps', '-q'], capture_output=True, text=True, timeout=30, check=True)
    assert not idle.stdout.strip(), 'another container is running'
    return dict(step=asdict(step), outcome='passed', producer_outcome=producer['outcome'],
                source=result['source'], collection_sha256=collection['sha256'],
                container_removed=True, lock_cleared=True)


def preserve(step: Step, output: pathlib.Path) -> None:
    if not output.exists():
        return
    destination = ARCHIVE / step.run_id
    shutil.copytree(output, destination)
    if (LOGS / (step.run_id + '.log')).exists():
        shutil.copy2(LOGS / (step.run_id + '.log'), destination / 'wrapper.log')
    if (LOGS / (step.run_id + '-launch.json')).exists():
        shutil.copy2(LOGS / (step.run_id + '-launch.json'), destination / 'launch.json')
    # The tar collection duplicates diagnostics; preserve it on Apo, omit the
    # duplicate from the lossless repository evidence bundle.
    bundle = REPORT / (step.run_id + '.tar.gz')
    with tarfile.open(bundle, 'x:gz', compresslevel=6) as tar:
        for path in sorted(destination.rglob('*')):
            if path.is_file() and path.name != 'diagnostics.tar':
                assert not path.is_symlink()
                tar.add(path, arcname=str(path.relative_to(destination)), recursive=False)
    save(REPORT / (step.run_id + '-bundle.json'),
         dict(step=asdict(step), archive=str(destination), bundle=bundle.name,
              bundle_sha256=sha(bundle), bundle_bytes=bundle.stat().st_size))


def main() -> int:
    REPORT.mkdir(exist_ok=False)
    ARCHIVE.mkdir(parents=True, exist_ok=False)
    LOGS.mkdir(parents=True, exist_ok=True)
    frozen_plan = HERE / 'plan.json'
    assert sha(frozen_plan) == sha(HOST / 'plan.json')
    manifest = HOST / 'support-manifest.json'
    assert sha(manifest) == SUPPORT
    for name, expected in json.loads(manifest.read_text())['files_sha256'].items():
        assert sha(HOST / name) == expected and sha(HERE / name) == expected
    steps = [Step(**value) for value in json.loads(frozen_plan.read_text())['steps']]
    completed: list[dict[str, Any]] = []
    start = utc()
    failed: dict[str, Any] | None = None
    try:
        for step in steps:
            output = HOST / step.run_id
            rc = 0
            try:
                if step.run_id not in PRELAUNCHED:
                    assert not output.exists() and not (HOST / 'cell.lock').exists()
                    command = ['/usr/local/bin/python3.12', '-I', '-B', str(HOST / 'run_one.py'),
                               '--run-id', step.run_id, '--revision', step.revision,
                               '--mode', step.mode, '--kind', step.kind, '--support-sha256', SUPPORT]
                    save(LOGS / (step.run_id + '-launch.json'), dict(command=command, step=asdict(step)))
                    print(json.dumps(dict(started_utc=utc(), step=asdict(step))), flush=True)
                    with (LOGS / (step.run_id + '.log')).open('xb') as log:
                        rc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log,
                                            stderr=subprocess.STDOUT).returncode
                assert rc == 0, f'wrapper exited {rc}'
                verdict = audit(step, output)
                save(REPORT / (step.run_id + '-audit.json'), verdict)
            finally:
                preserve(step, output)
            completed.append(verdict)
            print(json.dumps(dict(finished_utc=utc(), **verdict)), flush=True)
    except BaseException as error:
        failed = dict(step=asdict(step), error=repr(error))
        print(json.dumps(dict(stopped_utc=utc(), failure=failed)), flush=True)
    final = dict(started_utc=start, finished_utc=utc(), outcome='passed' if failed is None else 'stopped',
                 plan_sha256=sha(frozen_plan), support_sha256=SUPPORT, driver_sha256=sha(pathlib.Path(__file__)),
                 completed=completed, failure=failed, host='morrobay', shared_host_ratios_only=True,
                 archive=str(ARCHIVE), remaining=[asdict(s) for s in steps[len(completed):]])
    save(REPORT / 'receipt.json', final)
    save(ARCHIVE / 'receipt.json', final)
    return 0 if failed is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
