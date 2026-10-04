from pathlib import Path
from datetime import datetime, timezone
import subprocess, json, hashlib, os, re, sys

root = Path('/private/tmp/sail-bfs-inbox-gate')
out = Path(sys.argv[1])
exact = len(sys.argv) == 3
out.mkdir(parents=True, exist_ok=False)
prior = json.loads(Path('/tmp/bfs-inbox-evidence/candidate.json').read_text())

def git(*args):
    return subprocess.check_output(['git', *args], cwd=root)

sha = git('rev-parse', 'HEAD').decode().strip()
assert subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=root, stdout=subprocess.DEVNULL).returncode != 0
status = git('status', '--porcelain', '--untracked-files=all')
diff = git('diff', 'HEAD', '--binary')
if exact:
    assert sha == sys.argv[2] and not status and not diff
else:
    assert sha == prior['base_sha']
    assert diff == Path('/tmp/bfs-inbox-evidence/candidate.patch').read_bytes()
hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in prior['source_hashes']}
assert hashes == prior['source_hashes']
env = dict(os.environ, **prior['environment'])
manifest = str(root / 'examples/extensions/nutmeg/Cargo.toml')
record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'source_sha': sha,
          'candidate_not_commit': not exact, 'detached_clean_gate': exact,
          'candidate_patch_sha256': hashlib.sha256(diff).hexdigest() if not exact else None,
          'worktree': str(root), 'host': os.uname().nodename, 'machine': os.uname().machine,
          'environment': prior['environment'], 'source_hashes': hashes, 'commands': [],
          'scope': 'Full native adapter release library tests, including all Argentea tests. No remote transport or cluster execution.',
          'format_scope': 'No native adapter file changed. Core crate fmt is a separate required gate. Full native fmt has inherited failures, preserved in Grust bfs-completion/baseline-native-format.'}
commands = [
    ('format', ['rustfmt', '--edition', '2024', '--check', str(root / 'examples/extensions/nutmeg/src/argentea/bfs/tests/controls.rs')]),
    ('inventory', ['cargo', 'test', '--manifest-path', manifest, '--locked', '--release', '--lib', '--', '--list']),
    ('release', ['cargo', 'test', '--manifest-path', manifest, '--locked', '--release', '--lib', '--', '--nocapture']),
]
for name, command in commands:
    with (out / f'{name}.stdout').open('w') as stdout, (out / f'{name}.stderr').open('w') as stderr:
        result = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr)
    record['commands'].append({'name': name, 'command': command, 'exit_code': result.returncode})
    if result.returncode:
        break
stdout = (out / 'release.stdout').read_text() if (out / 'release.stdout').exists() else ''
inventory_stdout = (out / 'inventory.stdout').read_text() if (out / 'inventory.stdout').exists() else ''
passed = set(re.findall(r'^test (\S+) \.\.\. ok$', stdout, re.M))
inventory = set(re.findall(r'^(\S+): test$', inventory_stdout, re.M))
record.update(test_summary=re.findall(r'^test result:.*$', stdout, re.M), tests_passed=len(passed),
              argentea_tests_passed=sum(name.startswith('argentea::') for name in passed),
              inventory_matches=passed == inventory and len(passed) == 49,
              unchanged=(sha == git('rev-parse', 'HEAD').decode().strip()
                         and status == git('status', '--porcelain', '--untracked-files=all')
                         and diff == git('diff', 'HEAD', '--binary')
                         and all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())),
              finished_utc=datetime.now(timezone.utc).isoformat())
record['outcome'] = 'passed' if (len(record['commands']) == 3 and all(c['exit_code'] == 0 for c in record['commands'])
                                and record['inventory_matches'] and record['unchanged']) else 'failed'
(out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
print('BFS_INBOX_NATIVE', record['outcome'].upper(), sha, f'detached_clean={exact}',
      f'tests={len(passed)}', f'argentea={record["argentea_tests_passed"]}')
raise SystemExit(0 if record['outcome'] == 'passed' else 1)
