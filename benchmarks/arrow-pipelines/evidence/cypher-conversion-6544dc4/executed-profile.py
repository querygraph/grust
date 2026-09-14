import datetime, hashlib, json, os, pathlib, shutil, subprocess
root = pathlib.Path('/Users/alexy/src/grust-arrow-pipeline')
source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert source.startswith('6544dc4')
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip()
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
receipt = pathlib.Path('/tmp/grust-cypher-end-to-end-runs') / stamp
receipt.mkdir(parents=True)
binary = receipt / 'cypher_end_to_end'
shutil.copy2(root / 'benchmarks/arrow-pipelines/target/release/cypher_end_to_end', binary)
shutil.copy2(__file__, receipt / 'executed-profile.py')
for kind in ['build', 'clippy']:
    shutil.copy2('/tmp/grust-cypher-end-to-end-' + kind + '.log', receipt / (kind + '.log'))
state = {'source':source, 'host':'capitola', 'complete':False, 'runs':[],
         'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
         'boundary':'Cold row-graph representation; no deadline; no equivalent full resource policy. See each raw configuration.'}
print('RECEIPT', receipt, flush=True)
for nodes in [0, 1, 3, 4, 17, 100000, 1000000]:
    path = receipt / (str(nodes) + '.jsonl')
    command = ['nice', '-n', '10', str(binary), str(nodes), '3']
    with path.open('w') as output:
        code = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT).returncode
    lines = path.read_text().splitlines()
    events = []
    try:
        events = [json.loads(line) for line in lines]
    except json.JSONDecodeError:
        pass
    configs = [e for e in events if e.get('event') == 'configuration']
    trials = [e for e in events if e.get('event') == 'trial']
    expected_pairs = {(route, trial) for route in ['indexed','datafusion'] for trial in range(3)}
    valid = (code == 0 and len(configs) == 1 and configs[0]['source'] == source
             and len(trials) == 6 and {(t['route'],t['trial']) for t in trials} == expected_pairs
             and all(t['status'] == 'pass' for t in trials))
    state['runs'].append({'nodes':nodes, 'command':command, 'exit_code':code, 'oracle_checks':len(trials), 'qualified':valid})
    (receipt / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
    print('DONE', nodes, code, valid, flush=True)
    if not valid:
        raise SystemExit('Qualification failed; raw outcome retained; larger fixtures not run')
state['complete'] = True
(receipt / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
print('COMPLETE', flush=True)
