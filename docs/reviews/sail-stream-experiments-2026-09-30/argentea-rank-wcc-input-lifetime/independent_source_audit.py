"""Read-only final source/evidence review; does not compile or rerun tests."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

OUT = Path(__file__).resolve().parent
REPO = Path('/private/tmp/sail-rank-wcc-lifetime-gate')
BASE = 'a3462345a6764096024c055dc4d105a3c634e5a4'
COMMIT = '33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9'
TREE = '3f4399056199b49708340abf0b4d1205fca860dd'
DRIVER = '65510edd0cf4586b21f683769d24be951a8e9f7a2d51eff57a517667dfb8f344'
inputs = {}

def check(ok, why):
    if not ok:
        raise AssertionError(why)

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def bind(path, expected=None):
    digest = sha(path)
    if expected is not None:
        check(digest == expected, 'hash: ' + str(path))
    inputs[str(path.relative_to(OUT.parent))] = digest
    return digest

def read(name):
    p = OUT / name
    bind(p)
    return json.loads(p.read_text())

def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args], env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))

check(git('rev-parse', 'HEAD').decode().strip() == COMMIT, 'exact HEAD')
check(not git('status', '--porcelain'), 'clean exact source')
check(subprocess.run(['git', '-C', str(REPO), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1, 'detached')
check(git('rev-parse', 'HEAD^{tree}').decode().strip() == TREE, 'exact tree')
check(int(git('rev-list', '--count', BASE + '..HEAD')) == 2, 'two scoped commits')
pin = read('extended-frozen.json')
check(pin['component_base'] == BASE and pin['tree'] == TREE, 'frozen identity')
changed = set(git('diff', '--name-only', BASE, COMMIT).decode().splitlines())
check(changed == set(pin['paths']) and len(changed) == 27, 'exact 27-path scope')
check(all(p.startswith(('examples/extensions/argentea/', 'examples/extensions/nutmeg/src/argentea/')) for p in changed), 'scope confined')
for path, digest in pin['paths'].items():
    check(sha(REPO/path) == digest, 'frozen source hash: ' + path)
bind(OUT/'extended-candidate.patch', pin['patch_sha256'])
bind(OUT/'run_extended_gate.py', DRIVER)
check(pin['driver_sha256'] == DRIVER, 'driver pin')
for name in ['extended_commit_and_gate.sh', 'verify_extended_precommit.py', 'extended-precommit-verification.json', 'README.md', 'analyze.py']:
    bind(OUT/name)

expected_steps = ['diff-check', 'core-format', 'core-clippy', 'native-changed-format', 'core-release', 'native-build', 'native-registry', 'native-release', 'core-loaded', 'native-loaded']
gates = {}
for folder, exact, head in [('extended-candidate-gate', False, pin['base']), ('extended-exact-gate', True, COMMIT)]:
    r = read(folder+'/receipt.json')
    check((r['outcome'], r['head'], r['tree'], r['exact'], r['script_sha256']) == ('PASS', head, TREE, exact, DRIVER), 'gate identity')
    check([s['name'] for s in r['steps']] == expected_steps, 'complete ordered steps')
    src = read(folder+'/source-before.json')
    bind(OUT/folder/'source-before.json', r['source_before_sha256'])
    check(src['head'] == head and src['tree'] == TREE, 'source snapshot identity')
    source_digest = hashlib.sha256(json.dumps(src, sort_keys=True).encode()).hexdigest()
    check(len(r['guards']) == 21 and all(x['source_sha256'] == source_digest for x in r['guards']), 'every step/final frozen guards')
    tracked = set(git('ls-files', '-z').decode().rstrip('\0').split('\0'))
    check(tracked == set(src['files']), 'full tracked source inventory')
    for path, meta in src['files'].items():
        p = REPO/path
        digest = hashlib.sha256(os.fsencode(os.readlink(p))).hexdigest() if p.is_symlink() else sha(p)
        check(digest == meta['sha256'], 'unchanged tracked file: '+path)
    registry = read(folder+'/native-registry.json')
    bind(OUT/folder/'native-registry.json', r['native_registry']['registry_sha256'])
    names = registry['names']
    check(len(names) == len(set(names)) == 55 and sum(x.startswith('argentea::') for x in names) == 49, 'native registry 55/49')
    check(registry['tests'] == 55 and registry['argentea_tests'] == 49, 'registry counts')
    listed = re.findall(r'^(\S+): test$', (OUT/folder/'native-registry.log').read_text(), re.M)
    check(sorted(listed) == names, 'actual --list names')
    for s in r['steps']:
        check(s['outcome'] == 'PASS' and s['returncode'] == s['final_returncode'] == 0, 'step pass')
        bind(OUT/folder/s['log'], s['log_sha256'])
        if 'stderr_log' in s:
            bind(OUT/folder/s['stderr_log'], s['stderr_log_sha256'])
        check(s['process_cleanup']['group_absent'] and s['process_cleanup']['leader_reaped'], 'command cleanup')
        check(min(s['free_bytes_before'], s['free_bytes_after']) >= 32*1024**3, 'disk admission')
        if s['name'].startswith(('core-release', 'core-loaded', 'native-release', 'native-loaded')):
            rows = [tuple(map(int, row)) for row in re.findall(r'^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', (OUT/folder/s['log']).read_text(), re.M)]
            expected = 136 if s['name'].startswith('core') else 55
            check(sum(row[0] for row in rows) == s['tests_passed'] == expected and all(row[1:] == (0,0,0,0) for row in rows), 'full summaries')
            if s['name'].startswith('native'):
                check(rows == [(55,0,0,0,0)] and s['argentea_tests_passed'] == 49, 'native unfiltered pass')
                check(s['native_binary_sha256'] == registry['binary_sha256'], 'same native executable')
                check(registry['binary'] in (OUT/folder/s['log']).read_text(), 'executed artifact')
            if s['name'].endswith('loaded'):
                check(s['load_alive_before'] == s['load_alive_after'] == len(r['saturation']) == 10, 'saturation present')
    check(r['all_saturators_reaped'] and len(r['cleanup']) == 10 and all(x['reaped'] and x['group_cleanup']['group_absent'] for x in r['cleanup']), 'all load cleanup')
    check(not (Path(r['target_root'])/'.rank-wcc-input-gate.lock').exists(), 'target lock released')
    gates[folder] = dict(receipt_sha256=inputs['argentea-rank-wcc-input-lifetime/'+folder+'/receipt.json'], core_tests_each=136, native_tests_each=55, argentea_native_each=49, ordinary_and_loaded=True, tracked_files=len(tracked))

for name, log in [('baseline02-receipt.json','baseline02.log'), ('partition-lease-baseline-receipt.json','partition-lease-baseline.log')]:
    r = read(name)
    check(r['outcome'] == 'BASELINE_REPRODUCED' and r['returncode'] == 101 and r['source_unchanged'], 'retained failing baseline')
    bind(OUT/log, r['log_sha256'])
check(re.findall(r'bytes_at_lease_release=(\d+) final_live_bytes=0', (OUT/'baseline02.log').read_text()) == ['688', '688'], 'WCC baseline values')
part_values = dict(re.findall(r'PARTITION_SUCCESSFUL_DROP kind=(\w+) admitted_at_lease_release=(\d+) final_live_bytes=0', (OUT/'partition-lease-baseline.log').read_text()))
check(part_values == {'bfs':'816','sssp':'824','residual_pagerank':'502'}, 'partition baseline values')
for name, peak_offset, status, code in [('baseline-native-extended01',0,'EXPECTED_BASELINE_FAILURE',101), ('candidate-native-extended01',1,'PASS_ACTUAL_ADAPTER_CONTROLS',0)]:
    r = read(name+'/receipt.json')
    check(r['outcome'] == status and r['returncode'] == code and r['source_unchanged'], 'adapter control')
    for file in ['source-before.json','stdout','stderr']:
        bind(OUT/name/file, r[file.replace('-','_').replace('.json','')+'_sha256'])
    rows = r['lifetime_rows']
    check(len(rows) == 8 and len({tuple(row[:3]) for row in rows}) == 8, 'eight actual adapter cells')
    for kind, algo, n, calls, peak in rows:
        check(int(n) in (1024,65536) and int(calls) == (4 if kind == 'RESIDUAL' else 3) and int(peak) == int(calls)-peak_offset, 'adapter matched buffers')
    if peak_offset == 0:
        baseline_changed = git('diff','--name-only',BASE,r['tree']).decode().splitlines()
        check(all('/tests/' in p or p.endswith('/tests.rs') for p in baseline_changed), 'baseline production unchanged')

allocation = read('allocation-comparison.json')
check(allocation['commit'] == COMMIT and allocation['tree'] == TREE, 'allocation source identity')
bind(OUT/'extended-exact-gate/core-release.log', allocation['source_log_sha256'])
pattern = r'RANK_WCC_INPUT_LIFETIME n=(\d+) degree=(\d+) kind=(\w+) release=(true|false) allocation_calls=(\d+) allocated_bytes=(\d+) peak_requested_bytes=(\d+) retained_admitted_bytes=(\d+) peak_admitted_bytes=(\d+) work=(\d+)'
keys = ['n','degree','kind','release','allocation_calls','allocated_bytes','peak_requested_bytes','retained_admitted_bytes','peak_admitted_bytes','work']
rows = [dict(zip(keys,[int(v) if i not in (2,3) else v == 'true' if i == 3 else v for i,v in enumerate(row)])) for row in re.findall(pattern,(OUT/'extended-exact-gate/core-release.log').read_text())]
check(rows == allocation['rows'] and len(rows) == 72, 'raw allocator rows')
indexed = {(r['n'],r['degree'],r['kind'],r['release']):r for r in rows}
check(len(indexed) == 72, 'unique allocator cells')
unchanged_admission = 0
for (n,degree,kind,release), new in indexed.items():
    if not release:
        continue
    old = indexed[n,degree,kind,False]
    check(all(old[k] == new[k] for k in ['allocation_calls','allocated_bytes','retained_admitted_bytes','work']), 'matched volume/work')
    check(new['peak_requested_bytes'] <= old['peak_requested_bytes'] and new['peak_admitted_bytes'] <= old['peak_admitted_bytes'], 'peak ordering')
    if n >= 1024:
        check(old['peak_requested_bytes']-new['peak_requested_bytes'] >= n*8, 'nontrivial overlap reduction')
        check(old['peak_admitted_bytes'] == new['peak_admitted_bytes'], 'admission peak unchanged n>=1024')
        unchanged_admission += 1
check(unchanged_admission == 24, '24 unchanged admission pairs')
cursor = OUT.parent/'argentea-cursor-lease-control/final-receipt.json'
c = json.loads(cursor.read_text()); bind(cursor, 'd97a6bacacfb99a0cf4ebdace0d0093dd9f47e423c0f7763a4ffc4e1746701a8')
check(c['sequence_bytes'] == 2056 and c['baseline_last_owner_sequence_live_at_lease_release'] and not c['candidate_last_owner_sequence_live_at_lease_release'], 'cursor premise')
check(sha(REPO/'examples/extensions/argentea/tests/pagerank_cursor_lease.rs') == c['control_test_sha256'], 'same cursor control integrated')
check(git('rev-parse','HEAD').decode().strip() == COMMIT and not git('status','--porcelain'), 'final source unchanged')
result = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome='PASS_INDEPENDENT_EXPANDED_SOURCE_AND_EXACT_GATE_AUDIT', repository='querygraph/sail', commit=COMMIT, tree=TREE, component_base=BASE, changed_paths=sorted(changed), gates=gates, inputs=inputs, auditor_sha256=sha(Path(__file__)), findings=[], source_review=['Prepared CSR owns buffers before Resources; finish destructures Resources before adjacency for reverse local error cleanup.', 'PR/residual/WCC dense-state initialization statements preserve operation/validation/work and float order; adapters drop vectors before their admission and finish.', 'Resources-last changes are limited to reproduced WCC/BFS/SSSP/Delta partition defects; sequence reorder is limited to reproduced reference-PR cursor.', 'Exact-size pointer controls, admitted-byte callbacks, independent WCC oracle and candidate API bit traces have distinct evidence scopes.'], controls=dict(allocator_cells=72,matched_pairs=36,unchanged_admission_peak_pairs_n_ge_1024=24,actual_adapter_cells_each=8,baseline_partition_admitted_bytes=part_values,cursor_sequence_bytes=2056), limits=['Read-only source/log/hash audit; no independent rerun of suites.', 'Borrowed-versus-prepared protocol/cost controls compare candidate APIs; historical preservation also relies on extraction diff and existing tests.', 'Cursor experiment was authored by this reviewer and independently integrated/reviewed by Native; its evidence is not a second independent experiment.', 'Requested allocation and admission measures are not RSS/timing or historical stream-cause proof.', 'No host CLI/SQL/Linux/worker/Flight/wheel/runtime or performance qualification.'])
with (OUT/'independent-exact-review.json').open('x') as f:
    json.dump(result,f,indent=2); f.write('\n')
print(result['outcome'], COMMIT, sha(OUT/'independent-exact-review.json'))
