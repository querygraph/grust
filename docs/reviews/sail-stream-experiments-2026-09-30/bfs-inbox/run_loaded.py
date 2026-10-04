from pathlib import Path
from datetime import datetime, timezone
import subprocess, json, hashlib, os, re, time

root = Path('/private/tmp/sail-bfs-inbox-gate')
out = Path('/tmp/bfs-inbox-evidence/exact-loaded')
out.mkdir(exist_ok=False)
sha = 'c6126c27aae1b6262be3b1ecd6271008cc64fc69'
git = lambda *args: subprocess.check_output(['git', *args], cwd=root, text=True).strip()
assert git('rev-parse', 'HEAD') == sha and not git('status', '--porcelain')
assert subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=root, stdout=subprocess.DEVNULL).returncode != 0
prior = json.loads(Path('/tmp/bfs-inbox-evidence/exact-native/receipt.json').read_text())
assert prior['outcome'] == 'passed' and prior['source_sha'] == sha
environment = dict(prior['environment'])
core_environment = dict(environment, CARGO_TARGET_DIR='/private/tmp/sail-bfs-inbox-core-target')
record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'source_sha': sha,
          'detached_clean_gate': True, 'host': os.uname().nodename,
          'scope': 'Local saturated regression control; no timing or remote transport claim.',
          'load_process_count': os.cpu_count(), 'runs': []}
processes = []
try:
    processes = [subprocess.Popen(['yes'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(os.cpu_count())]
    time.sleep(1)
    for name, path, env, options, count in [
        ('core', 'argentea', core_environment, [], 108),
        ('native', 'nutmeg', environment, ['--lib'], 49),
    ]:
        command = ['cargo', 'test', '--manifest-path', str(root / f'examples/extensions/{path}/Cargo.toml'), '--locked', '--release', *options, '--', '--nocapture']
        live_before = sum(p.poll() is None for p in processes)
        with (out / f'{name}.stdout').open('w') as stdout, (out / f'{name}.stderr').open('w') as stderr:
            result = subprocess.run(command, cwd=root, env=dict(os.environ, **env), stdout=stdout, stderr=stderr)
        live_after = sum(p.poll() is None for p in processes)
        output = (out / f'{name}.stdout').read_text()
        summaries = re.findall(r'^test result:.*$', output, re.M)
        passed = sum(int(n) for n in re.findall(r'^test result: ok\. (\d+) passed;', output, re.M))
        success = result.returncode == 0 and passed == count and live_before == live_after == os.cpu_count()
        record['runs'].append({'name': name, 'command': command, 'environment': env, 'exit_code': result.returncode,
                               'summaries': summaries, 'tests_passed': passed, 'expected_count': count,
                               'load_alive_before': live_before, 'load_alive_after': live_after, 'passed': success})
        if not success:
            break
finally:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        process.wait()
record['all_load_reaped'] = all(p.poll() is not None for p in processes)
record['unchanged'] = git('rev-parse', 'HEAD') == sha and not git('status', '--porcelain') and all(
    hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in prior['source_hashes'].items())
record['finished_utc'] = datetime.now(timezone.utc).isoformat()
record['outcome'] = 'passed' if len(record['runs']) == 2 and all(r['passed'] for r in record['runs']) and record['unchanged'] and record['all_load_reaped'] else 'failed'
(out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
print('BFS_INBOX_LOADED', record['outcome'].upper(), sha, f'load={len(processes)}',
      [(r['name'], r['tests_passed']) for r in record['runs']])
raise SystemExit(0 if record['outcome'] == 'passed' else 1)
