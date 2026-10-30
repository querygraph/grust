"""Root-executed exact-candidate CLI build; no source checkout mutation."""
import os
import shutil
import subprocess
import traceback

from common import BUILD_ENV, CLI, LABEL, OUT, ROOT, candidate, helpers, now, sha, snapshot, verify_reference, write_json


def main():
    assert not (OUT / 'build.json').exists(), 'archive the prior attempt before rerunning'
    assert not (OUT / 'build.log').exists(), 'refuse to overwrite a build log'
    receipt = {'label': LABEL, 'started_at': now(), 'outcome': 'starting',
               'command': ['cargo', '+1.98.1', 'build', '-p', 'sail-cli', '--locked'],
               'environment_overrides': BUILD_ENV, 'cli_path': str(CLI),
               'helpers_sha256': helpers(), 'scope': 'CLI build only; no runtime qualification.'}
    try:
        expected = candidate()
        receipt.update(sail_commit=expected['commit'], base=expected['base'])
        receipt['before'] = snapshot(expected)
        receipt['spark_reference'] = verify_reference()
        receipt['disk_free_before'] = shutil.disk_usage(ROOT).free
        assert receipt['disk_free_before'] > 2 * 1024**3, 'existing gate discipline requires 2GiB free'
        write_json(OUT / 'build.json', receipt)
        with (OUT / 'build.log').open('x') as log:
            result = subprocess.run(receipt['command'], cwd=ROOT, env={**os.environ, **BUILD_ENV},
                                    stdout=log, stderr=subprocess.STDOUT)
        receipt['build_exit_code'] = result.returncode
        receipt['build_log_sha256'] = sha(OUT / 'build.log')
        receipt['after'] = snapshot(expected)
        assert receipt['after'] == receipt['before'], 'candidate changed during compilation'
        assert result.returncode == 0, 'CLI build failed; see retained build.log'
        receipt['cli_sha256'] = sha(CLI)
        receipt['cli_size'] = CLI.stat().st_size
        receipt['outcome'] = 'passed'
    except BaseException:
        receipt['outcome'] = 'failed'
        receipt['error'] = traceback.format_exc()
        raise
    finally:
        receipt['completed_at'] = now()
        write_json(OUT / 'build.json', receipt)
    print('PASS exact-candidate CLI build ' + receipt['sail_commit'], flush=True)


if __name__ == '__main__':
    main()
