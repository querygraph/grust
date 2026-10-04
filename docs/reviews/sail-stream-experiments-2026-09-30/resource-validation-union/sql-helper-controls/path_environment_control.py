"""Reproduce the helper-only env-python3 failure; no SQL or Sail process."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile

OLD = '0aca81a5819f29095d2592804aea836250d7640de917ce7d959a264ec80f124e'
NEW = 'eaebc96443f9edc621adb1a937d7042ef3b8decaae757693f03872d7ad8fbb96'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    old = load(root/'attempt-failed02/sql_gate.py', 'old_helper')
    new = load(root.parent/'sql_gate.py', 'new_helper')
    assert old.sha(Path(old.__file__)) == OLD and new.sha(Path(new.__file__)) == NEW
    args.output.mkdir(exist_ok=False)
    private = Path(tempfile.mkdtemp(prefix='sql-path-controls-'))
    script = private/'fake-generator'
    script.write_text('#!/usr/bin/env python3\nimport struct, sys\n'
        'sys.stdout.buffer.write(struct.pack("<qqd", 0, 1, 0.5) * 8)\n'
        'print("generator failed after output", file=sys.stderr)\nsys.exit(7)\n')
    script.chmod(0o755)
    bench = args.repo/'examples/extensions/benchmarks'
    original = old.client_environment(bench, args.repo)
    original['PATH'] = '/opt/homebrew/bin:/usr/bin:/bin'
    fixed = dict(original, PATH=str(new.PYTHON.parent)+os.pathsep+original['PATH'])
    result = dict(started_utc=datetime.now(timezone.utc).isoformat(), old_helper_sha256=OLD,
        new_helper_sha256=NEW, source_sha256=new.sha(Path(__file__)), private_fixtures=str(private),
        scope='Tiny generated eight-edge script and exactly two existing benchmark unit fixtures. No SQL, Sail CLI, real Graph500 generator, graph workload or remote operation.', cases=[])
    try:
        for name, env in [('bad_314_with_312_home', original), ('good_312_path_only', fixed)]:
            process = subprocess.run([str(script)], env=env, capture_output=True, timeout=10)
            (args.output/(name+'.stderr')).write_bytes(process.stderr)
            row = dict(name=name, returncode=process.returncode, stdout_bytes=len(process.stdout),
                python3_path=shutil.which('python3', path=env['PATH']))
            result['cases'].append(row)
        assert result['cases'][0]['returncode'] != 7 and result['cases'][0]['stdout_bytes'] == 0
        assert result['cases'][1]['returncode'] == 7 and result['cases'][1]['stdout_bytes'] == 192
        env = new.client_environment(bench, args.repo)
        assert Path(shutil.which('python3', path=env['PATH'])).resolve() == new.PYTHON.resolve()
        commands = [
            ('client-stdlib', [str(new.PYTHON), '-B', str(new.__file__), '--interpreter-probe']),
            ('two-unit-fixtures', [str(new.PYTHON), '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
             str(bench/'test_graph500_fixture.py')+'::test_nonzero_generator_exit_cannot_publish_success',
             str(bench/'test_graph500_fixture.py')+'::test_max_degree_source_is_resolved_from_the_streamed_degrees',
             '--basetemp='+str(private/'pytest'), '--junitxml='+str(args.output/'focused.xml')])]
        for label, command in commands:
            with (args.output/(label+'.log')).open('x') as log:
                process = subprocess.run(command, env=env, cwd=args.repo, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=60)
            result['cases'].append(dict(name=label, command=command, returncode=process.returncode))
            process.check_returncode()
        result['client_identity'] = json.loads((args.output/'client-stdlib.log').read_text())
        result['outcome'] = 'PASS_FOCUSED_ENVIRONMENT_CORRECTION'
    except BaseException as error:
        result.update(outcome='FAIL', error_type=type(error).__name__, error=str(error))
    finally:
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        result['artifact_hashes'] = {p.name: new.sha(p) for p in args.output.iterdir() if p.is_file()}
        new.save(args.output/'receipt.json', result)
    print(result['outcome'])
    return 0 if result['outcome'] == 'PASS_FOCUSED_ENVIRONMENT_CORRECTION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
