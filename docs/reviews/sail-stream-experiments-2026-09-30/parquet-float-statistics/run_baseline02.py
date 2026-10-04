from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/private/tmp/sail-parquet-float-statistics-baseline')
OUT = Path(__file__).resolve().parent / 'baseline02'
OUT.mkdir(exist_ok=False)
TARGET = '/private/tmp/sail-parquet-float-statistics-baseline-target'

def utc():
    return datetime.now(timezone.utc).isoformat()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def snapshot():
    module = ROOT / 'crates/sail-data-source/src/formats/parquet/read_statistics_tests.rs'
    return dict(head=git('rev-parse', 'HEAD').decode().strip(),
                diff=git('diff', '--binary').decode(),
                test_module_sha256=hashlib.sha256(module.read_bytes()).hexdigest(),
                untracked=git('ls-files', '--others', '--exclude-standard').decode(),
                detached=subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=ROOT, capture_output=True).returncode == 1)

before = snapshot()
assert before['head'] == '200d1cf8eb1db5e9057e09e071ebd57391f4b376' and before['detached']
assert git('diff', '--name-only').decode().splitlines() == ['crates/sail-data-source/src/formats/parquet/mod.rs']
assert before['untracked'].splitlines() == ['crates/sail-data-source/src/formats/parquet/read_statistics_tests.rs']
free = shutil.disk_usage(ROOT).free
assert free > 30*1024**3
command = ['cargo', 'test', '--locked', '-p', 'sail-data-source', '--lib', 'formats::parquet::read_statistics_tests', '--', '--nocapture']
env = dict(os.environ, CARGO_TARGET_DIR=TARGET, CARGO_INCREMENTAL='0', CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0', CARGO_BUILD_JOBS='6')
receipt = dict(started_utc=utc(), outcome='RUNNING', before=before, command=command, free_bytes_before=free,
               target=TARGET, target_seed='APFS clone of idle private candidate target after exploratory test03 completed; never shared',
               scope='Unchanged production 200d1cf8 plus identical candidate readback test module and cfg(test) declaration only')
def save():
    (OUT/'baseline-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
save()
with (OUT/'baseline.log').open('x') as stream:
    result = subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
receipt.update(returncode=result.returncode, finished_utc=utc(), after=snapshot())
text = (OUT/'baseline.log').read_text()
receipt['outcome'] = 'EXPECTED_REGRESSION_FAILURE' if result.returncode == 101 and before == receipt['after'] and 'NaN became 0.5' in text and '2 passed; 2 failed' in text else 'UNEXPECTED_RESULT'
save()
print(receipt['outcome'], flush=True)
print('\n'.join(text.splitlines()[-45:]), flush=True)
assert receipt['outcome'] == 'EXPECTED_REGRESSION_FAILURE'
