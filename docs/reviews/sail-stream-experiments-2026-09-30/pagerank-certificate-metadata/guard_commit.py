"""Verify the frozen detached verdict and exact staged tree before committing."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = Path('/private/tmp/sail-pagerank-certificate-metadata')
candidate = json.loads((ROOT/'candidate02.json').read_text())
receipt = json.loads((ROOT/'candidate02-gate/receipt.json').read_text())
review_path = ROOT/'independent-candidate02-review.json'
assert hashlib.sha256(review_path.read_bytes()).hexdigest() == 'dbc8b5b47d18d37733cc0f3acb3f4c19b02f15dcd2504a40c5212f5a625d7997'
assert receipt['outcome'] == 'passed' and receipt['source_and_runtime_unchanged']
assert receipt['source_commit'] == candidate['detached_candidate']
assert receipt['sql_tests'] == dict(tests=58, failures=0, errors=0, skipped=0)
assert receipt['unit_tests'] == dict(tests=430, failures=0, errors=0, skipped=97)
for path, pin in receipt['source_pins'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == pin, path
for name, pin in receipt['logs_sha256'].items():
    assert hashlib.sha256((ROOT/'candidate02-gate'/name).read_bytes()).hexdigest() == pin, name


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args], text=True).strip()


assert git('symbolic-ref', 'HEAD') == 'refs/heads/work/pagerank-certificate-metadata'
assert git('rev-parse', 'HEAD') == candidate['base']
assert git('write-tree') == candidate['tree']
assert subprocess.run(['git', '-C', str(REPO), 'diff', '--quiet']).returncode == 0
assert sorted(git('diff', '--cached', '--name-only').splitlines()) == sorted(candidate['files_sha256'])
for name, pin in candidate['files_sha256'].items():
    assert hashlib.sha256((REPO/name).read_bytes()).hexdigest() == pin, name
assert subprocess.run(['git', '-C', str(REPO), 'diff', '--cached', '--check']).returncode == 0
print('PAGERANK_METADATA_FROZEN_GATE_AND_REVIEW VERIFIED '+candidate['detached_candidate'])
