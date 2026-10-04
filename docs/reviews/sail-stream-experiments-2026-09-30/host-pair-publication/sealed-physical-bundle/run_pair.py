#!/usr/bin/env python3
"""Explicit durable serial execution, only from a sealed completed-six-cell bundle."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')
    temporary.replace(path)


def load_supervisor(path, request):
    need(sha(path) == request['files']['supervise.py']['sha256'], 'supervisor differs')
    spec = importlib.util.spec_from_file_location('pair_cell_supervisor', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate(path, digest, output):
    need(path.name == 'pair-requests.json' and sha(path) == digest, 'pair request differs')
    root = path.parent; manifest = json.loads(path.read_text())
    need(not output.is_relative_to(root) and not root.is_relative_to(output), 'output overlaps prepared inputs')
    need(sha(Path(__file__).resolve()) == manifest['run_pair_sha256'], 'serial wrapper differs')
    need(sha(root / 'pair-collected-evidence.json') == manifest['pair_audit_sha256']
         and sha(root / 'all-six-closures.json') == manifest['all_six_sha256'], 'whole-sequence closure differs')
    pair = json.loads((root / 'pair-collected-evidence.json').read_text())
    whole = json.loads((root / 'all-six-closures.json').read_text())
    need(whole['pair_audit'] == pair and whole['pair_audit_sha256'] == manifest['pair_audit_sha256'], 'whole-sequence audit binding differs')
    need(manifest['original_ratio_eligible'] == pair['ratio_eligible'] and
         manifest['original_shared_host_ratios'] == pair['shared_host_ratios'], 'original ratio fields differ')
    cells = manifest['cells']; need(len(cells) == 6, 'six requests required')
    need([(x['order'], x['phase'], x['host']) for x in cells] == [(1,'warmup','A'), (2,'warmup','B'),
        (3,'measurement','A'), (4,'measurement','B'), (5,'measurement','B'), (6,'measurement','A')], 'sequence order differs')
    need(len({x['cell_output'] for x in cells}) == 6, 'repeated namespace')
    for item in cells:
        need(item['request'] == f"bundles/{item['order']:02d}/request.json", 'unsafe request path')
        request_path = root / item['request']; need(sha(request_path) == item['request_sha256'], 'cell request differs')
        request = json.loads(request_path.read_text()); need(request['cell_output'] == item['cell_output'], 'namespace differs')
        need(request['files']['all-six-closures.json']['sha256'] == manifest['all_six_sha256']
             and request['files']['pair-plan.json']['sha256'] == manifest['plan_sha256'], 'cell/whole-sequence binding differs')
        supervisor = load_supervisor(request_path.parent / 'supervise.py', request)
        supervisor.validate(request_path, item['request_sha256'], output / f"{item['order']:02d}")
    return manifest


def qualifies(manifest, results, unchanged):
    return bool(unchanged and manifest['original_ratio_eligible'] is True and len(results) == 6
        and len({x['cell_output'] for x in results}) == 6
        and all(x.get('supervisor_returncode') == 0 and x.get('physical_status') == 'physical_values_pass'
                and isinstance(x.get('physical_report'), dict) and len(x['physical_report'].get('sha256', '')) == 64
                and x.get('cleanup') == 'removed_after_state_capture' and x.get('container_state', {}).get('OOMKilled') is False
                and x.get('container_state', {}).get('Status') == 'exited' and x.get('container_state', {}).get('Running') is False
                and x.get('container_state', {}).get('ExitCode') == 0 for x in results))


def execute(path, digest, output):
    with (output / 'serial-claim.json').open('x') as stream:
        json.dump(dict(utc=utc(), request_sha256=digest), stream)
    report = dict(started_utc=utc(), outcome='incomplete', cells=[], errors=[], supplemental_physical_qualification=False,
                  scope='Supplemental physical output only. Original benchmark outcomes/ratios unchanged; no timing/causality or new graph certificate.')
    manifest = None
    try:
        manifest = validate(path, digest, output)
        report.update(original_ratio_eligible=manifest['original_ratio_eligible'], original_shared_host_ratios=manifest['original_shared_host_ratios'])
        for item in manifest['cells']:
            row = dict(order=item['order'], phase=item['phase'], host=item['host'], cell_output=item['cell_output'], outcome='started')
            report['cells'].append(row); save(output / 'serial-receipt.json', report)
            cell_output = output / f"{item['order']:02d}"
            request_path = path.parent / item['request']; request = json.loads(request_path.read_text())
            supervisor = load_supervisor(request_path.parent / 'supervise.py', request)
            supervisor.create_evidence_directory(cell_output)
            rc = supervisor.run_supervisor(request_path, item['request_sha256'], cell_output)
            outer = cell_output / 'outer-receipt.json'; data = json.loads(outer.read_text())
            row.update(outcome='closed', supervisor_returncode=rc, outer_receipt_sha256=sha(outer),
                request_sha256=item['request_sha256'], physical_status=data.get('physical_status'),
                physical_report=data.get('physical_report'), cleanup=data.get('cleanup'), container_state=data.get('container_state'))
            save(output / 'serial-receipt.json', report)
            need(data.get('cleanup') == 'removed_after_state_capture', 'checker cleanup incomplete; remaining cells not attempted')
        validate(path, digest, output)
        # Bind the actual report and lifecycle bytes, not just copied status strings.
        for item in report['cells']:
            base = output / f"{item['order']:02d}"
            need(sha(base / 'outer-receipt.json') == item['outer_receipt_sha256'], 'outer receipt changed')
            physical = item['physical_report']
            if physical is not None:
                need(sha(base / 'physical-output.json') == physical['sha256'], 'physical report changed')
        report['inputs_and_reports_unchanged'] = True
        report['supplemental_physical_qualification'] = qualifies(manifest, report['cells'], True)
        report['outcome'] = 'six_checks_closed'
    except Exception as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if manifest is not None:
            attempted = {x['order'] for x in report['cells']}
            for item in manifest['cells']:
                if item['order'] not in attempted:
                    report['cells'].append(dict(order=item['order'], cell_output=item['cell_output'], outcome='not_attempted_after_stop'))
        report['finished_utc'] = utc(); save(output / 'serial-receipt.json', report)
    return 0 if report['supplemental_physical_qualification'] else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', type=Path, required=True); p.add_argument('--request-sha256', required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--execute-after-closure', action='store_true')
    p.add_argument('--detached-child', action='store_true', help=argparse.SUPPRESS)
    a = p.parse_args(); path, output = a.request.resolve(), a.output.resolve()
    if a.detached_child:
        need(a.execute_after_closure, 'explicit execution flag required'); return execute(path, a.request_sha256, output)
    manifest = validate(path, a.request_sha256, output)
    if not a.execute_after_closure:
        print(json.dumps(dict(prepared_only=True, cells=manifest['cells'], original_ratio_eligible=manifest['original_ratio_eligible']), indent=2)); return 0
    output.mkdir(parents=False, exist_ok=False)
    output.chmod(0o700)
    command = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--request', str(path),
               '--request-sha256', a.request_sha256, '--output', str(output), '--execute-after-closure', '--detached-child']
    with (output / 'serial.stdout').open('xb') as stdout, (output / 'serial.stderr').open('xb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True, close_fds=True)
    save(output / 'launch.json', dict(utc=utc(), pid=process.pid, command=command, request_sha256=a.request_sha256,
        scope='Durable serial launch identity only; missing final receipt is incomplete, never success.'))
    print(json.dumps(dict(pid=process.pid, output=str(output)))); return 0


if __name__ == '__main__':
    raise SystemExit(main())
