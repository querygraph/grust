from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = Path('/private/tmp/sail-parquet-float-statistics')
BASE = '200d1cf8eb1db5e9057e09e071ebd57391f4b376'
TREE = '7063e31260100901bd43d8820c4e1e733aa99605'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

receipt = json.loads((OUT/'candidate-gate02/receipt.json').read_text())
assert receipt['outcome'] == 'PASS' and receipt['before'] == receipt['after']
assert receipt['before']['head'] == BASE and receipt['before']['tree'] == TREE
assert git('rev-parse','HEAD').decode().strip() == BASE
assert git('write-tree').decode().strip() == TREE
assert git('symbolic-ref','--short','HEAD').decode().strip() == 'work/parquet-float-statistics'
assert not git('diff','--name-only')
assert not git('ls-files','--others','--exclude-standard')
for name in git('diff','--cached','--name-only').decode().splitlines():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == receipt['before']['source'][name]
baseline = json.loads((OUT/'baseline02/baseline-receipt.json').read_text())
assert baseline['outcome'] == 'EXPECTED_REGRESSION_FAILURE'
assert baseline['before']['test_module_sha256'] == receipt['before']['source']['crates/sail-data-source/src/formats/parquet/read_statistics_tests.rs']
(OUT/'precommit-guard.json').write_text(json.dumps(dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='PASS',base=BASE,tree=TREE,candidate_gate_sha256=hashlib.sha256((OUT/'candidate-gate02/receipt.json').read_bytes()).hexdigest(),baseline_receipt_sha256=hashlib.sha256((OUT/'baseline02/baseline-receipt.json').read_bytes()).hexdigest()),indent=2)+'\n')
print('PRECOMMIT_GUARD PASS', TREE)
