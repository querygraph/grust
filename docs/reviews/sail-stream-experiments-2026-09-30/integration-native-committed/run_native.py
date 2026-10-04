from pathlib import Path
from datetime import datetime, timezone
import subprocess, json, hashlib, os, re
root = Path('/tmp/sail-nutmeg-all-candidate')
out = Path('/tmp/sail-union-289-native-evidence/nutmeg-native')
out.mkdir(parents=True, exist_ok=True)
prior = json.loads(Path('/tmp/nutmeg-all-candidate-evidence/candidate.json').read_text())
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert sha == '2894a962076d3cc404dd72ec736ebeb9239901f6'
assert subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=root, stdout=subprocess.DEVNULL).returncode != 0
assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root, text=True).strip()
env = dict(os.environ, **prior['environment'])
hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in prior['source_hashes']}
assert hashes == prior['source_hashes']
command = prior['command']
record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'source_sha': sha, 'detached_clean_gate': True, 'worktree': str(root), 'target_dir': prior['target_dir'], 'host': os.uname().nodename, 'machine': os.uname().machine, 'environment': prior['environment'], 'python': prior['python'], 'source_hashes': hashes, 'command': command, 'scope': 'Full Nutmeg native-adapter release library unit tests; all Argentea tests included. No Sail runtime/process/transport/cluster proof.', 'prior_candidate_source_hashes_identical': True, 'loaded_control': '/tmp/nutmeg-all-candidate-evidence/loaded-verified/receipt.json (identical native build sources)'}
with (out / 'release.stdout').open('w') as stdout, (out / 'release.stderr').open('w') as stderr:
    result = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr)
record['exit_code'] = result.returncode
stdout = (out / 'release.stdout').read_text()
record['test_summary'] = re.findall(r'^test result:.*$', stdout, re.M)
passed = set(re.findall(r'^test (\S+) \.\.\. ok$', stdout, re.M))
inventory = set(re.findall(r'^(\S+): test$', Path('/tmp/nutmeg-all-candidate-evidence/test-inventory.stdout').read_text(), re.M))
record['test_count'] = len(passed)
record['argentea_tests_passed'] = sum(name.startswith('argentea::') for name in passed)
record['inventory_matches'] = passed == inventory
record['unchanged'] = sha == subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() and not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root, text=True).strip() and all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
record['finished_utc'] = datetime.now(timezone.utc).isoformat()
record['outcome'] = 'passed' if result.returncode == 0 and record['unchanged'] and record['inventory_matches'] else 'failed'
(out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
print('NUTMEG_NATIVE_RELEASE', record['outcome'].upper(), sha, 'detached_clean=True', 'tests=' + str(record['test_count']), 'argentea=' + str(record['argentea_tests_passed']))
raise SystemExit(0 if record['outcome'] == 'passed' else 1)
