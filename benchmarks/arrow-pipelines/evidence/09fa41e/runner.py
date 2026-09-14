import datetime, hashlib, json, os, pathlib, shutil, subprocess, time
root = pathlib.Path('/Users/alexy/src/grust-arrow-pipeline')
os.chdir(root)
source = '09fa41e' # Resolved against the unchanged baseline checkout below.
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
if not head.startswith(source) or subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
    raise SystemExit('Baseline checkout must remain clean and pinned to 09fa41e')
binary = root / 'target/release/grust-arrow-pipeline-profile'
if not binary.is_file():
    raise SystemExit('Qualified baseline build is not available')
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
receipt = pathlib.Path('/tmp/grust-relational-baseline') / stamp
receipt.mkdir(parents=True)
shutil.copy2(binary, receipt / binary.name)
binary = receipt / binary.name
state = {'source': head, 'host': 'capitola', 'started': stamp, 'complete': False,
         'binary_sha256': hashlib.file_digest(binary.open('rb'), 'sha256').hexdigest(),
         'platform': subprocess.check_output(['sw_vers'], text=True),
         'physical_memory_bytes': int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True)),
         'rustc': subprocess.check_output(['/opt/homebrew/bin/rustc', '-Vv'], text=True),
         'boundary': 'Distinct local execution classes; 256 MiB DataFusion working pool is not a process RSS or Cypher cap. No deadline. /usr/bin/time -l reports process resource usage.',
         'runs': []}
print(receipt, flush=True)
for nodes, fanout, repeats in [(4,1,1), (4,5,1), (20,1,1), (2000,8,3), (20000,8,3)]:
    name = f'{nodes}-{fanout}-{repeats}'
    command = ['/usr/bin/time', '-l', str(binary), str(nodes), str(fanout), str(repeats)]
    started = time.monotonic()
    with (receipt / (name + '.jsonl')).open('w') as output, (receipt / (name + '.stderr')).open('w') as error:
        code = subprocess.run(command, stdout=output, stderr=error).returncode
    records = [json.loads(line) for line in (receipt / (name + '.jsonl')).read_text().splitlines()]
    configs = [r for r in records if r.get('event') == 'configuration']
    qualified = len(configs) == 1 and configs[0]['source'] == head
    state['runs'].append({'command': command, 'name': name, 'exit_code': code,
                          'seconds': time.monotonic()-started, 'source_qualified': qualified})
    (receipt / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
    print(name, code, 'source_qualified', qualified, flush=True)
    if not qualified:
        raise SystemExit('Preserved unqualified receipt; refusing larger measurements')
state['complete'] = True
(receipt / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
