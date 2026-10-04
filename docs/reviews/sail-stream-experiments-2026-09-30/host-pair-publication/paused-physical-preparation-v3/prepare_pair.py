#!/usr/bin/env python3
"""Local post-six-trial metadata export and bundle creation; no payload/Docker reads."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import uuid

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
PAIR_SHA = '6a377820d65649a72ce4317da11e13245e404109deaa1eef573edff262816987'
COPY_SHA = '938885a595e5d74b134748e4d79f08e54f1bdf16e094ba0199225c1c6254ca57'
ENTRY_SHA = 'af5f8cb2a715efe3373f75a0dc73d28fa7cd599e7294877fa24440bcfd9903fe'
HELPER_SHA = '4c5fe87d0eb0b3f4aec3e70841bc7db968017f952dda6978840d101d2f2f7872'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def load_module(path, name, digest=None):
    need(digest is None or sha(path) == digest, 'module source differs')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')
    path.chmod(0o644)
    return sha(path)


def prepare(collection, output):
    need(not output.is_relative_to(collection) and not collection.is_relative_to(output), 'output overlaps collected evidence')
    need(not output.is_relative_to(EXP), 'generated bundles must stay outside published evidence')
    output.mkdir(parents=False, exist_ok=False)
    status = dict(started_utc=datetime.now(timezone.utc).isoformat(), outcome='preparation_error',
                  scope='Local metadata/archive audit only, no result Parquet or Docker access.', exports=[])
    try:
        pair_path = EXP / 'host-pair-collection-audit/audit_pair.py'
        pair = load_module(pair_path, 'frozen_pair', PAIR_SHA)
        h = pair.support(); plan, configs = pair.prepared(h)
        pair_report = pair.audit_collection(collection)
        pair_sha = save(output / 'pair-collected-evidence.json', pair_report)
        status['pair_audit_sha256'] = pair_sha
        need(pair_report['integrity_status'] == 'integrity_verified' and len(pair_report['cells']) == 6,
             'complete closed six-cell collection required')
        policy = load_module(HERE / 'pair_policy.py', 'pair_policy')
        exports = []
        for entry, config in zip(plan['runs'], configs):
            cell = collection / 'cells' / config['run_id']
            profile = dict(config_path='host-pair-16k/' + entry['configuration'], evidence_pins=[],
                binary_sha256=entry['binary_sha256'],
                native_identity_canonical_sha256=h.canonical(plan['expected_native_package_identity']),
                dataset_canonical_sha256=h.canonical(plan['expected_dataset']),
                resolved_dataset_path=plan['expected_arguments']['dataset'])
            closed = h.audit(cell, profile, pair.EXP)
            path = output / f"{entry['order']:02d}-closed-cell.json"
            digest = save(path, closed)
            status['exports'].append(dict(order=entry['order'], path=path.name, sha256=digest))
            policy.closed_ok(closed)
            receipt = cell / 'diagnostics/receipt.json'; receipt_pin = closed['files'][str(receipt)]
            row = pair_report['cells'][entry['order'] - 1]
            exports.append(dict(order=entry['order'], run_id=config['run_id'], cell_output=entry['cell_output'],
                expected_vertices=16384, expected_source=0, configuration_sha256=entry['configuration_sha256'],
                binary_sha256=entry['binary_sha256'], receipt=str(receipt), receipt_sha256=receipt_pin['sha256'],
                closure_file=path.name, closure_sha256=digest, closed_audit=closed,
                boot_id=row['sequence_row']['boot_id']))
        all_six = dict(pair_audit=pair_report, pair_audit_sha256=pair_sha, cells=exports)
        policy.all_six(all_six, plan)
        all_six_path = output / 'all-six-closures.json'; save(all_six_path, all_six)
        # This exact frozen helper handles original-and-copied SHA guards.
        copier = load_module(HERE / 'baseline-v3/prepare.py', 'frozen_copier', COPY_SHA)
        need(sha(HERE / 'container_check.py') == ENTRY_SHA, 'reviewed entry changed')
        helper = EXP / 'physical-output-audit/audit_output.py'; need(sha(helper) == HELPER_SHA, 'physical helper changed')
        bundle_root = output / 'bundles'; bundle_root.mkdir()
        prepared = []
        for entry, config, item in zip(plan['runs'], configs, exports):
            bundle = bundle_root / f"{entry['order']:02d}"; copier.create_bundle_directory(bundle)
            sources = {'configuration.json': EXP / 'host-pair-16k' / entry['configuration'],
                'producer-receipt.json': Path(item['receipt']), 'closed-audit.json': output / item['closure_file'],
                'audit_output.py': helper, 'container_check.py': HERE / 'container_check.py',
                'supervise.py': HERE / 'supervise.py', 'pair_policy.py': HERE / 'pair_policy.py',
                'pair-plan.json': EXP / 'host-pair-16k' / pair.PLAN_NAME, 'all-six-closures.json': all_six_path}
            required = {'configuration.json': entry['configuration_sha256'], 'producer-receipt.json': item['receipt_sha256'],
                'closed-audit.json': item['closure_sha256'], 'audit_output.py': HELPER_SHA,
                'pair-plan.json': pair.PLAN_SHA, 'container_check.py': ENTRY_SHA}
            files = copier.copy_bundle(sources, required, bundle)
            request = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), prepared_only=True, files=files,
                cell_output=entry['cell_output'], expected_vertices=16384, expected_source=0,
                boot_id=exports[-1]['boot_id'], binary_sha256=entry['binary_sha256'],
                native_path='/targets/graph-nuts-ffcfbd569/venv/lib/python3.12/site-packages/sail_nutmeg/_native.cpython-312-x86_64-linux-gnu.so',
                native_sha256=plan['expected_native_package_identity']['files_sha256']['_native.cpython-312-x86_64-linux-gnu.so'],
                expected_python_version='3.12.14', expected_pyarrow='21.0.0', expected_numpy='2.5.3',
                container_name='physical-output-pair-' + uuid.uuid4().hex[:16], timeout_seconds=1800,
                execution_identity=dict(host_uid=501, host_gid=20, container_user='501:20',
                    bundle_mode='0755', bundle_file_mode='0644', evidence_mode='0700'),
                limits=dict(cpus=1, memory_bytes=2147483648, memory_swap_bytes=2147483648, pids=64),
                disk_admission=dict(host_evidence_minimum_free_bytes=268435456, target_volume_minimum_free_bytes=1073741824))
            digest = save(bundle / 'request.json', request)
            policy.validate_context(request, bundle)
            prepared.append(dict(order=entry['order'], phase=entry['phase'], host=entry['host'],
                cell_output=entry['cell_output'], request=str((bundle / 'request.json').relative_to(output)), request_sha256=digest))
        # Exact recipe stability check through the complete export/copy interval.
        for name, pin in pair_report['evidence_files'].items():
            need(not Path(name).is_symlink() and h.file_info(Path(name)) == pin, 'collected evidence changed: ' + name)
        pair.prepared(h)
        need(sha(pair_path) == PAIR_SHA and sha(EXP / 'closed-cell-audit/audit_cell.py') == pair.HELPER_SHA, 'audit sources changed')
        shutil.copyfile(HERE / 'run_pair.py', output / 'run_pair.py')
        need(sha(HERE / 'run_pair.py') == sha(output / 'run_pair.py'), 'serial wrapper copy differs')
        manifest = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), plan_sha256=pair.PLAN_SHA,
            pair_audit_sha256=pair_sha, all_six_sha256=sha(all_six_path), cells=prepared,
            run_pair_sha256=sha(output / 'run_pair.py'), original_ratio_eligible=pair_report['ratio_eligible'],
            original_shared_host_ratios=pair_report['shared_host_ratios'], scope='Prepared after all six closed trials; no payload scan. Original benchmark outcomes and ratios unchanged.')
        status.update(outcome='PREPARED_ONLY', pair_request_sha256=save(output / 'pair-requests.json', manifest))
    except Exception as error:
        status['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        status['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save(output / 'preparation-receipt.json', status)
    return status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collection', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = prepare(a.collection.resolve(), a.output.resolve())
    print(json.dumps(result)); return 0 if result['outcome'] == 'PREPARED_ONLY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
