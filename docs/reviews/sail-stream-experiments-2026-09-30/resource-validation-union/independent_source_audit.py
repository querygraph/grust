#!/usr/bin/env python3
"""Read-only union source/receipt audit. No builds, tests, checkout or remote calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

BASE = '200d1cf8eb1db5e9057e09e071ebd57391f4b376'
TREE = 'd43293b4e5de64878c85c1d3d756077e2b7b749b'
CORE = '7f5b80d0fe35cf8520f80078ee0dbd50b1a5833d'
PYTHON = '7df2f32f070e041eed5416eb44f7ff8fa4ce0d01'
PARQUET = '837e8e82acc5e971fce4533a7c4ecf08355cafe8'
DRIVER = 'ac1b12fbe08ac290b862c4453431fe31f95ef3d61b9ba27506b1f1c0ee6c1bdd'
SQL = 'eaebc96443f9edc621adb1a937d7042ef3b8decaae757693f03872d7ad8fbb96'
GUARD = '8688696dc1fd519092cb58f17ac29ac78f8d1a309617dd7126a0fd9b46f4f03e'
CHAIN = '9a38020a41ba8557927418988497b1e7dc38fde26bc728dba6f53bb94b48cb1d'
CANDIDATE = 'candidate-gate03'
FAILURES = {'candidate-gate': '06ce2b3527ce9d5f3689fb04fd68e5624867126677a74a12712c97ed96844a0e',
            'candidate-gate02': '33557f1696710e458be628acf746a4d3cb82969ee127a8b3593ee4f206af61f2'}
PREFIXES = {'examples/extensions/argentea': CORE, 'examples/extensions/nutmeg': CORE,
            'examples/extensions/benchmarks': PYTHON, 'crates/sail-data-source': PARQUET}
STEP_NAMES = ['diff-check', 'host-format', 'host-clippy', 'host-tests', 'core-format',
              'core-clippy', 'native-changed-format', 'core-release', 'native-build',
              'native-registry', 'native-release',
              'core-loaded', 'native-loaded', 'cli-build', 'python-sql']
COUNTS = {'host-tests': 77, 'core-release': 120, 'core-loaded': 120,
          'native-release': 51, 'native-loaded': 51}
UNIT = dict(tests=430, failures=0, errors=0, skipped=97)
SQL_COUNTS = dict(tests=58, failures=0, errors=0, skipped=0)


class NotClosed(Exception):
    pass


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1 << 20), b''):
            h.update(data)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--exact-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    repo = args.repo.resolve()
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), outcome='INCONCLUSIVE',
                  repository='querygraph/sail', requested_exact_sha=args.exact_sha,
                  scope='Independent recorded-evidence and source-boundary audit only. '
                  'No test rerun, build, new SQL request, remote operation or performance verdict.',
                  source_proofs=[], gate_summaries=[], files={}, errors=[])
    check(not args.output.resolve().is_relative_to(repo), 'audit output must be outside Sail source')
    check(not args.output.exists(), 'audit output already exists')

    def pin(path):
        path = Path(path)
        check(path.is_file() and not path.is_symlink(), 'missing/nonregular evidence: ' + str(path))
        value = dict(bytes=path.stat().st_size, sha256=sha(path))
        prior = report['files'].get(str(path))
        check(prior is None or prior == value, 'evidence changed during audit: ' + str(path))
        report['files'][str(path)] = value
        return value

    def read(path):
        pin(path)
        value = json.loads(Path(path).read_text())
        check(isinstance(value, dict), 'expected object: ' + str(path))
        return value

    def git(*command):
        return subprocess.check_output(['git', '-C', str(repo), *command],
            env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), timeout=30)

    def inventory(ref, prefix=None):
        command = ['ls-tree', '-r', '-z', ref]
        if prefix:
            command.extend(['--', prefix])
        result = {}
        for row in git(*command).split(b'\0'):
            if row:
                metadata, path = row.split(b'\t', 1)
                mode, kind, blob = metadata.decode().split()
                check(kind == 'blob', 'unexpected nonblob source')
                result[os.fsdecode(path)] = [mode, blob]
        return result

    def test_xml(path, expected):
        pin(path)
        document = ET.parse(path).getroot()
        suites = document.findall('testsuite')
        counts = {key: sum(int(s.attrib[key]) for s in suites) for key in expected}
        check(counts == expected, 'XML coverage differs: ' + str(path))
        return document

    def source_snapshot(path, head, mode):
        value = read(path)
        check(value['head'] == head and value['tree'] == TREE, 'snapshot HEAD/tree differs')
        if mode == 'exact':
            check(value.get('status', '') == '', 'exact snapshot is dirty')
        return value

    def check_sql(directory, gate, mode):
        child = read(directory/'receipt.json')
        check(pin(directory/'receipt.json')['sha256'] == gate['sql_receipt_sha256'], 'SQL receipt binding differs')
        check(child['outcome'] == 'passed' and child['mode'] == mode, 'SQL child did not pass expected scope')
        check(child['expected_head'] == gate['head'] and child['expected_tree'] == TREE, 'SQL source differs')
        check(child['unit_tests'] == UNIT and child['sql_tests'] == SQL_COUNTS, 'SQL receipt counts differ')
        check(child['source_and_runtime_unchanged'] is True and child['server_reaped'] is True,
              'SQL identity/cleanup proof missing')
        for name, digest in child['logs_sha256'].items():
            check(pin(directory/name)['sha256'] == digest, 'SQL member hash differs: ' + name)
        test_xml(directory/'unit.xml', UNIT)
        xml = test_xml(directory/'sql.xml', SQL_COUNTS)
        classes = [x.attrib['classname'] for x in xml.findall('.//testcase')]
        check(sum(x.endswith('test_pagerank_metadata') for x in classes) == 52 and
              sum(x.endswith('test_wcc_certificate') for x in classes) == 6, 'SQL fixture inventory differs')
        before = source_snapshot(directory/'source-before.json', gate['head'], mode)
        after = source_snapshot(directory/'source-after.json', gate['head'], mode)
        check(before == after, 'SQL source snapshots differ')
        check(child['client_before'] == child['client_after'], 'client package/interpreter changed')
        client = child['client_before']
        check(client['real_executable'] == client['path_python3_real'] and
              client['executable_sha256'] == client['path_python3_sha256'] and
              client['version'].startswith('3.12.8 ') and
              client['stdlib_encodings_file'].startswith(client['base_prefix']+'/lib/python3.12/'),
              'client shebang interpreter or standard library differs')
        settings = child['selected_server_environment']
        check(settings == dict(SAIL_MODE='local', SAIL_EXECUTION__DEFAULT_PARALLELISM='2',
              SAIL_EXECUTION__COLLECT_STATISTICS='true', TOKIO_WORKER_THREADS='2',
              RAYON_NUM_THREADS='2', RUST_LOG='warn'), 'SQL server settings differ')
        check(child['server_command'][0] == gate['binary']['path'], 'SQL launched another binary')
        pins = child['runtime_and_interpreter_pins']
        check(pins[gate['binary']['path']] == gate['binary']['sha256'], 'SQL binary hash differs')
        check(pins[str(root/'sql_gate.py')] == SQL, 'SQL helper pin missing')
        control = read(directory/'default-statistics.json')
        check(control['outcome'] == 'passed' and len(control['checks']) == 2, 'default-statistics control failed')
        cases = {x['case']: x for x in control['checks']}
        check(set(cases) == {'mixed_nan_finite', 'finite_fixed_point'}, 'default-statistics cases differ')
        for name, case in cases.items():
            check(case['footer_min'] == case['footer_max'] == .5, 'constant finite footer bound was not exercised')
            expected_mask = [True, False] if name == 'mixed_nan_finite' else [False, False]
            check(case['direct_read_nan_mask'] == expected_mask, 'direct read did not preserve payload')
            check(set(case['policies']) == {'reference', 'certificate'}, 'policy coverage differs')
            for proof in case['policies'].values():
                if name == 'mixed_nan_finite':
                    check(proof['outcome'] == 'expected_rejection' and
                          'invalid PageRank scores' in proof['error'], 'NaN rejection absent')
                else:
                    check(proof['outcome'] == 'passed' and proof['proof']['rows'] == 2 and
                          proof['proof']['unique_ids'] == 2 and proof['proof']['true_fixed_point_residual'] == 0,
                          'finite fixed-point positive control failed')
        return dict(unit_passed=333, unit_skipped=97, sql_passed=58,
                    pagerank_sql=52, wcc_sql=6, default_statistics_cases=list(cases),
                    source_runtime_unchanged=True, server_reaped=True)

    def gate_audit(directory, exact):
        path = directory/'receipt.json'
        if not path.exists():
            raise NotClosed('missing ' + str(path))
        value = read(path)
        if value.get('outcome') == 'RUNNING' or not value.get('finished_utc'):
            raise NotClosed('gate is not closed: ' + str(directory))
        check(value['outcome'] == 'PASS', 'gate failure retained: ' + str(directory))
        head = args.exact_sha if exact else BASE
        check(value['head'] == head and value['tree'] == TREE and value['exact'] is exact,
              'gate source/scope differs')
        check(value['repo'] == str(repo), 'gate names another worktree')
        check(value['script_sha256'] == DRIVER and value['sql_helper_sha256'] == SQL, 'helper pins differ')
        check([step['name'] for step in value['steps']] == STEP_NAMES, 'gate step inventory differs')
        nload = len(value['saturation'])
        check(nload > 0 and value['all_saturators_reaped'] is True, 'saturation/cleanup absent')
        check(len(value['cleanup']) == nload, 'saturator cleanup inventory differs')
        for item in value['cleanup']:
            check(item['reaped'] is True and item['group_cleanup']['group_absent'] is True,
                  'saturator group remains')
        registry = read(directory/'native-registry.json')
        registry_sha = pin(directory/'native-registry.json')['sha256']
        check(value['native_registry'] == dict(registry, registry_sha256=registry_sha),
              'native registry receipt binding differs')
        registry_text = (directory/'native-registry.log').read_text()
        lines = [line for line in registry_text.splitlines() if line.strip()]
        names = [match[1] for line in lines if (match := re.fullmatch(r'(\S+): test', line))]
        check(len(names) == len(set(names)) == 51 and len(lines) == 52 and
              lines[-1] == '51 tests, 0 benchmarks', 'actual native registry inventory differs')
        check(sum(name.startswith('argentea::') for name in names) == 45 and
              registry['names'] == sorted(names) and registry['tests'] == 51 and
              registry['argentea_tests'] == 45, 'native registry adapter identity differs')
        check(pin(directory/'native-registry.log')['sha256'] == registry['registry_log_sha256'],
              'actual native registry bytes differ')
        native_artifacts = [json.loads(line) for line in (directory/'native-build.log').read_text().splitlines()
                            if line.startswith('{')]
        native_matches = [item for item in native_artifacts if item.get('reason') == 'compiler-artifact'
                          and item.get('target', {}).get('name') == '_native' and item.get('executable')]
        check(native_matches == [registry['cargo_artifact']], 'Cargo native artifact proof differs')
        native_artifact = registry['cargo_artifact']
        check(Path(native_artifact['manifest_path']) == repo/'examples/extensions/nutmeg/Cargo.toml' and
              native_artifact['profile']['test'] is True and
              native_artifact['executable'] == registry['binary'] and
              Path(registry['binary']).is_relative_to(Path(value['target_root'])/'native/release'),
              'native registry refers to another source or target')
        for step in value['steps']:
            name = step['name']
            check(step['outcome'] == 'PASS' and step['returncode'] == 0, 'step failed: ' + name)
            check(step['process_cleanup']['leader_reaped'] and step['process_cleanup']['group_absent'],
                  'command cleanup failed: ' + name)
            check(not step['process_cleanup']['group_alive_on_entry'], 'command left descendants: ' + name)
            check(pin(directory/step['log'])['sha256'] == step['log_sha256'], 'log changed: ' + name)
            if 'stderr_log' in step:
                check(pin(directory/step['stderr_log'])['sha256'] == step['stderr_log_sha256'],
                      'stderr log changed: ' + name)
            text = (directory/step['log']).read_text()
            if name in COUNTS:
                summaries = [list(map(int, row)) for row in re.findall(
                    r'^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; '
                    r'(\d+) measured; (\d+) filtered out;', text, re.M)]
                check(summaries and summaries == step['summaries'] and
                      sum(row[0] for row in summaries) == step['tests_passed'] == COUNTS[name] and
                      all(row[1:] == [0, 0, 0, 0] for row in summaries), 'Rust test count differs: ' + name)
            if name == 'native-registry':
                check('stderr_log' in step and registry['binary'] in
                      (directory/step['stderr_log']).read_text(), 'registry Cargo execution identity absent')
            if name in ('native-release', 'native-loaded'):
                check(summaries == [[51, 0, 0, 0, 0]] and step['argentea_tests_passed'] == 45 and
                      step['native_registry_sha256'] == registry_sha and
                      step['native_binary_sha256'] == registry['binary_sha256'] and
                      registry['binary'] in text, 'native full-registry execution proof differs')
            if name.endswith('-loaded'):
                check(step['load_alive_before'] == step['load_alive_after'] == nload, 'saturation coverage differs')
        baseline = source_snapshot(directory/'source-before.json', head, 'exact' if exact else 'candidate')
        check(pin(directory/'source-before.json')['sha256'] == value['source_before_sha256'], 'source receipt hash differs')
        digest = canonical(baseline)
        expected_labels = [label for name in STEP_NAMES for label in (name+'-before', name+'-after')] + ['final']
        check([g['label'] for g in value['guards']] == expected_labels, 'source guard coverage differs')
        check(all(g['source_sha256'] == digest for g in value['guards']), 'source guard fingerprint differs')
        artifact = value['cli_cargo_artifact']
        found = [json.loads(line) for line in (directory/'cli-build.log').read_text().splitlines()
                 if line.startswith('{')]
        matches = [x for x in found if x.get('reason') == 'compiler-artifact'
                   and x.get('target', {}).get('name') == 'sail' and x.get('executable')]
        check(matches == [artifact], 'Cargo CLI artifact proof differs')
        check(Path(artifact['manifest_path']) == repo/'crates/sail-cli/Cargo.toml', 'CLI comes from another source')
        check(artifact['executable'] == value['binary']['path'], 'CLI executable differs')
        check(value['binary']['path'] == str(Path(value['target_root'])/'host/debug/sail'), 'unexpected CLI target')
        sql = check_sql(directory/'sql', value, 'exact' if exact else 'candidate')
        report['gate_summaries'].append(dict(scope='exact_commit' if exact else 'staged_candidate',
            head=head, tree=TREE, receipt_sha256=pin(path)['sha256'], rust_counts=COUNTS,
            argentea_native_tests=45, saturators=nload, binary=value['binary'], sql=sql))
        return value, baseline

    try:
        for name, expected in [('run_gate.py', DRIVER), ('sql_gate.py', SQL),
                               ('guard_commit.py', GUARD), ('candidate-and-commit.sh', CHAIN)]:
            check(pin(root/name)['sha256'] == expected, 'frozen orchestration source changed: ' + name)
        report['retained_failed_attempts'] = []
        for name, expected_sha in FAILURES.items():
            path = root/name/'receipt.json'
            failed = read(path)
            check(pin(path)['sha256'] == expected_sha and failed['outcome'] == 'FAIL',
                  'failed candidate receipt changed: ' + name)
            for step in failed['steps']:
                check(pin(path.parent/step['log'])['sha256'] == step['log_sha256'],
                      'failed candidate log changed: ' + name+'/'+step['log'])
                if 'stderr_log' in step:
                    check(pin(path.parent/step['stderr_log'])['sha256'] == step['stderr_log_sha256'],
                          'failed candidate stderr changed: ' + name)
            report['retained_failed_attempts'].append(dict(path=name, receipt_sha256=expected_sha,
                outcome=failed['outcome'], error=failed.get('error'),
                failed_steps=[step['name'] for step in failed['steps'] if step['outcome'] != 'PASS']))
        prep = read(root/'source-preparation.json')
        check(prep['base'] == BASE and prep['tree'] == TREE and set(prep['components']) == {CORE, PYTHON, PARQUET},
              'source preparation differs')
        expected = inventory(BASE)
        for prefix, ref in PREFIXES.items():
            replacement = inventory(ref, prefix)
            expected = {name: blob for name, blob in expected.items() if not name.startswith(prefix+'/')}
            expected.update(replacement)
            check(inventory(TREE, prefix) == replacement, 'component tree mismatch: ' + prefix)
            report['source_proofs'].append(dict(prefix=prefix, component=ref,
                files=len(replacement), inventory_sha256=canonical(replacement), all_equal=True))
        actual = inventory(TREE)
        check(actual == expected, 'unexpected source changes outside admitted component trees')
        changed = git('diff-tree', '--no-commit-id', '--name-only', '-r', BASE, TREE).decode().splitlines()
        check(changed == prep['changed_paths'], 'changed-path inventory differs')
        report.update(source_files=len(actual), changed_paths=changed,
                      complete_expected_tree_sha256=canonical(expected),
                      other_paths_and_all_lockfiles_unchanged=not any(x.endswith('Cargo.lock') for x in changed))
        candidate, _ = gate_audit(root/CANDIDATE, False)
        guard = read(root/'candidate-commit-guard.json')
        check(guard['outcome'] == 'PASS_COMMIT_GUARD' and guard['base'] == BASE and guard['tree'] == TREE,
              'conditional commit guard did not pass expected tree')
        check(guard['candidate_gate_sha256'] == pin(root/CANDIDATE/'receipt.json')['sha256'] and
              guard['sql_receipt_sha256'] == candidate['sql_receipt_sha256'] and guard['driver_sha256'] == GUARD,
              'commit guard evidence binding differs')
        check(git('rev-parse', args.exact_sha+'^{tree}').decode().strip() == TREE, 'exact commit tree differs')
        parents = git('show', '-s', '--format=%P', args.exact_sha).decode().split()
        check(set(parents) <= {BASE, CORE, PYTHON, PARQUET} and {CORE, PYTHON, PARQUET} <= set(parents),
              'commit parents differ from the admitted merge')
        report['exact_parents'] = parents
        exact, frozen = gate_audit(root/'exact-gate', True)
        check(git('rev-parse', 'HEAD').decode().strip() == args.exact_sha and not git('status', '--porcelain'),
              'detached worktree is no longer clean at exact SHA')
        check(subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1,
              'exact worktree is no longer detached')
        check(git('rev-parse', 'refs/heads/work/stream-review-followup').decode().strip() == args.exact_sha,
              'integration branch moved')
        for name, expected_pin in frozen['files'].items():
            path = repo/name
            content_hash = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest() if path.is_symlink() else sha(path)
            check(content_hash == expected_pin['sha256'] and path.lstat().st_mode == expected_pin['mode'],
                  'live source no longer matches exact gate: ' + name)
        check(not (Path(exact['target_root'])/'.resource-validation-gate.lock').exists(), 'gate target remains locked')
        check(pin(Path(exact['binary']['path']))['sha256'] == exact['binary']['sha256'], 'exact CLI artifact changed')
        check(pin(Path(exact['native_registry']['binary']))['sha256'] ==
              exact['native_registry']['binary_sha256'], 'exact native test artifact changed')
        for path, digest in read(root/'exact-gate/sql/receipt.json')['runtime_and_interpreter_pins'].items():
            check(pin(path)['sha256'] == digest, 'exact runtime/interpreter pin changed: ' + path)
        for path, fingerprint in list(report['files'].items()):
            check(pin(path) == fingerprint, 'consumed evidence changed')
        report.update(outcome='PASS_INDEPENDENT_EXACT_UNION_AUDIT', exact_sha=args.exact_sha,
                      exclusions=['No Linux rebuild, remote run or worker/Flight qualification.',
                                  'No combined rebuilt native extension loaded into the new CLI.',
                                  'Pecan/other host code inherits exact source identity, not a newly rerun full-workspace suite.',
                                  'Full native formatting inherited exclusions remain explicit.',
                                  'No performance, historical corruption or stream-cause claim.'])
    except NotClosed as error:
        report.update(outcome='INCONCLUSIVE_GATE_NOT_CLOSED')
        report['errors'].append(str(error))
    except Exception as error:
        report.update(outcome='FAIL_INDEPENDENT_AUDIT')
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['auditor_sha256'] = sha(Path(__file__))
        with args.output.open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(report['outcome'], args.exact_sha)
    return 0 if report['outcome'] == 'PASS_INDEPENDENT_EXACT_UNION_AUDIT' else 2


if __name__ == '__main__':
    raise SystemExit(main())
