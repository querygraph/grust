"""Offline archive, owned removal, shared lock and mocked container controls."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import tempfile
import unittest
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import Mock, patch

import run_shapes_host as host


class MatrixControl(ModuleType):
    capture: host.CaptureAPI
    run_container: Callable[..., dict[str, Any]]


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value))


def identity(path: Path) -> dict[str, Any]:
    return {'bytes': path.stat().st_size, 'sha256': host.sha(path)}


def archive(directory: Path, config: dict[str, Any], config_sha: str, outcome: str = 'passed') -> None:
    config = host.CellConfiguration.model_validate(config).model_dump(mode='json')
    (directory/'engine/result').mkdir(parents=True)
    result = directory/'engine/result/part.parquet'
    result.write_bytes(b'raw result bytes retained, physical oracle tested separately')
    plan = directory/'engine/plan-shape-result.txt'
    plan.write_text('physical plan without edits\n')
    files = {'part.parquet': identity(result)}
    producer = {'outcome': outcome, 'config': config, 'identities_before': {'pin': 1}, 'identities_after': {'pin': 1},
        'engine_returncode': 0, 'engine_wait_completed': True, 'execution_verified': True,
        'ownership_admitted': True,
        'remaining_processes': [], 'remaining_after_cleanup': [], 'emergency_cleanup': [],
        'final_processes': [], 'finalization_errors': [], 'interruption_signals': [],
        'correctness': {'outcome': 'passed', 'shape': config['shape'], 'full_oracle': True,
            'rows': 3, 'expected_rows': 3, 'unique': 3, 'mismatches': 0, 'duplicate_rows': 0,
            'result_files': files, 'result_files_after': files},
        'plans': {'engine/plan-shape-result.txt': {**identity(plan), 'relation': 'shape-result', 'scope': 'raw'}}}
    write_json(directory/'receipt.json', producer)
    write_json(directory/'bootstrap-receipt.json', {'outcome': 'passed', 'producer_returncode': 0,
        'identities_before': {'pin': 1}, 'identities_after': {'pin': 1}, 'config_sha256': config_sha})
    write_json(directory/'archive-manifest.json', {'schema_version': 1, 'files': host.collected_inventory(directory)})


def container_record(returncode: int = 0) -> dict[str, Any]:
    return {'create': {'returncode': 0, 'stdout': 'a'*64}, 'attach_returncode': returncode,
        'remove': {'returncode': 0}, 'copied': {'artifacts': {'returncode': 0}},
        'inspect': {'id': 'a'*64, 'image': host.IMAGE,
            'state': {'Running': False, 'ExitCode': returncode, 'OOMKilled': False},
            'limits': {'NanoCpus': 16*10**9, 'CpusetCpus': '0-15', 'Memory': 32*2**30,
                'MemorySwap': 32*2**30, 'Init': True, 'PidMode': 'private', 'PidsLimit': 1024}}}


class HostControls(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config: dict[str, Any] = {'dataset': 'signed-fixture', 'shape': 'adjacency', 'variant': 'union',
            'repo': host.ROOT+'/repo', 'harness_repo': host.HARNESS_REPO, 'support': host.ROOT+'/support',
            'output': host.ROOT+'/cells/control', 'vertices': '/targets/fixtures/vertices.parquet',
            'edges': '/targets/fixtures/edges.parquet', 'references': host.ROOT+'/references/fixture',
            'binary': host.SAIL, 'support_sha256': '1'*64, 'reference_receipt_sha256': '0'*64,
            'minimum_free_bytes': 256*2**30}
        self.config_file = self.root/'config.json'
        write_json(self.config_file, self.config)

    def test_complete_archive_rejects_changed_missing_and_unlisted_files(self) -> None:
        directory = self.root/'archive'
        archive(directory, self.config, '2'*64)
        self.assertIn('engine/plan-shape-result.txt', host.verify_archive(directory))
        (directory/'engine/result/part.parquet').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'complete guest/host archive hash mismatch'):
            host.verify_archive(directory)
        (directory/'unlisted').write_text('extra')
        with self.assertRaises(ValueError):
            host.verify_archive(directory)

    def test_symlink_collection_refused(self) -> None:
        directory = self.root/'archive'
        directory.mkdir()
        (directory/'link').symlink_to(self.config_file)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            host.collected_inventory(directory)

    def test_failed_producer_and_incomplete_oracle_are_refused(self) -> None:
        directory = self.root/'archive'
        archive(directory, self.config, '2'*64, 'mismatch')
        spec = {'config_text': json.dumps(self.config), 'config_sha256': '2'*64}
        with self.assertRaisesRegex(ValueError, 'producer did not pass'):
            host.producer_check('cell', directory, spec)
        producer = json.loads((directory/'receipt.json').read_text())
        producer['outcome'] = 'passed'
        producer['correctness']['full_oracle'] = False
        write_json(directory/'receipt.json', producer)
        with self.assertRaisesRegex(ValueError, 'full physical output'):
            host.producer_check('cell', directory, spec)

    def run_removal(self, output: Path) -> None:
        namespace: dict[str, Any] = {'pathlib': pathlib, 'os': os, 'shutil': shutil, 'json': json,
            'root': output.parent.parent, 'spec': {'output': str(output), 'run_id': output.name,
                'archive_sha256': host.sha(output/'archive-manifest.json')},
            'guard': lambda: {'pin': 1}, 'quiet': lambda: None, 'sha': host.sha, 'require': host.require}
        exec(compile(host.REMOVE[len(host.COMMON):], '<offline-owned-removal>', 'exec'), namespace)  # noqa: S102 — trusted constant body, temp files and stubbed guards only.

    def test_passed_owned_payload_can_be_removed_after_complete_archive(self) -> None:
        output = self.root/'guest/cells/control'
        archive(output, self.config, '2'*64)
        host.verify_archive(output)
        borrowed = output.parent.parent/'borrowed'
        borrowed.write_text('keep')
        self.run_removal(output)
        self.assertFalse(output.exists())
        self.assertEqual(borrowed.read_text(), 'keep')

    def test_removal_refuses_failed_changed_or_leaked_payload(self) -> None:
        for reason in ('failed', 'changed', 'leak'):
            with self.subTest(reason=reason):
                output = self.root/reason/'cells/control'
                archive(output, self.config, '2'*64, 'error' if reason == 'failed' else 'passed')
                if reason == 'changed':
                    (output/'engine/result/part.parquet').write_bytes(b'changed after archive')
                if reason == 'leak':
                    receipt = json.loads((output/'receipt.json').read_text())
                    receipt['emergency_cleanup'] = ['SIGTERM owned survivor']
                    write_json(output/'receipt.json', receipt)
                    (output/'archive-manifest.json').unlink()
                    write_json(output/'archive-manifest.json', {'schema_version': 1, 'files': host.collected_inventory(output)})
                with self.assertRaises(ValueError):
                    self.run_removal(output)
                self.assertTrue(output.exists())

    def test_all_embedded_guest_programs_compile(self) -> None:
        for script in (host.STAGE, host.PROBE, host.BOOT, host.REMOVE):
            compile(script, '<guest-program>', 'exec')

    def test_container_closure_rejects_unknown_identity_and_forced_kill(self) -> None:
        for bad in ('identity', 'kill', 'envelope'):
            with self.subTest(bad=bad):
                record = container_record()
                if bad == 'identity': record['inspect']['id'] = 'b'*64
                if bad == 'kill': record['forced_cleanup_kill'] = {'returncode': 0}
                if bad == 'envelope': record['inspect']['limits']['MemorySwap'] = -1
                with patch.object(host, 'absent', return_value=host.CommandResult(returncode=1)), \
                     patch.object(host, 'idle'), self.assertRaises(ValueError):
                    host.check_matrix_record(record, 'owned', True)

    def test_copy_timeout_adapter_changes_only_exact_owned_copy_and_restores_capture(self) -> None:
        module = MatrixControl('frozen-matrix-control')
        original = Mock(return_value={'returncode': 0})
        module.capture = original
        output = self.root/'container'
        owned = ['docker', '--context', 'colima-sail-gate', 'cp', 'owned:/targets/cell/.', str(output/'artifacts')]
        foreign = ['docker', '--context', 'colima-sail-gate', 'cp', 'other:/targets/cell/.', str(output/'artifacts')]
        inspection = ['docker', '--context', 'colima-sail-gate', 'inspect', 'owned']
        def run(*_args: object) -> dict[str, Any]:
            module.capture(inspection)
            module.capture(owned, timeout=180)
            module.capture(foreign, timeout=180)
            return {'retained': True}
        module.run_container = run
        host.matrix_run(module, 'owned', [], output, '/targets/cell', 3600)
        self.assertEqual(original.call_args_list[0].kwargs['timeout'], 60)
        self.assertEqual(original.call_args_list[1].kwargs['timeout'], 1800)
        self.assertEqual(original.call_args_list[2].kwargs['timeout'], 180)
        self.assertIs(module.capture, original)
        module.run_container = Mock(side_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            host.matrix_run(module, 'owned', [], output, '/targets/cell', 3600)
        self.assertIs(module.capture, original)

    def mocked_orchestration(self, outcome: str) -> None:
        base = self.root/outcome
        base.mkdir()
        removed: list[str] = []
        def small(_host: Path, _name: str, script: str, spec: dict[str, Any],
                  _payload: Path | None, _copy: str | None, **_kwargs: object) -> dict[str, Any]:
            if script == host.REMOVE:
                removed.append(spec['output'])
                result = {'outcome': 'passed', 'removed': spec['output']}
            else:
                result = {'admission': {'volume_free_bytes': 256*2**30}, 'identities': {'pin': 1}}
            return {'certain_closure': True, 'attach': {'stdout': json.dumps(result)}}
        def run_container(_config: dict[str, Any], _name: str, command: list[str], output: Path,
                          _image: str, _timeout: int, _copy: dict[str, str]) -> dict[str, Any]:
            spec = json.loads(command[-1])
            archive(output/'artifacts', self.config, spec['config_sha256'],
                    'mismatch' if outcome == 'mismatch' else 'passed')
            if outcome == 'bad-copy':
                (output/'artifacts/engine/result/part.parquet').write_bytes(b'transport-corrupted')
            return container_record()
        matrix = Mock()
        matrix.run_container.side_effect = run_container
        pins = {'support_sha256': '1'*64, 'payload_sha256': '2'*64}
        with ExitStack() as stack:
            for name, value in [('BASE', base), ('LOCK', base/'gate.lock'),
                ('CAMPAIGN', host.Campaign(host_root=base, guest_root=host.ROOT)), ('idle', Mock()),
                ('host_pins', lambda: pins), ('snapshot', lambda: {'free': 256*2**30}),
                ('capture', lambda *_args, **_kwargs: host.CommandResult(returncode=0, stdout=host.IMAGE)),
                ('owned_small', small), ('matrix_module', lambda: matrix),
                ('absent', lambda _name: host.CommandResult(returncode=1, stderr='no such object'))]:
                stack.enter_context(patch.object(host, name, value))
            code = host.execute(host.Options('run', 'control', 'cell', self.config_file))
        receipt = json.loads((base/'control/result.json').read_text())
        self.assertEqual(code, 0 if outcome == 'passed' else 1)
        self.assertEqual(bool(removed), outcome == 'passed')
        self.assertEqual((base/'gate.lock').exists(), outcome != 'passed')
        self.assertEqual(receipt['payload_removed'], outcome == 'passed')
        if outcome == 'mismatch':
            self.assertEqual(receipt['producer_outcome'], 'mismatch')

    def test_orchestration_retains_failed_payload_and_lock_but_removes_verified_pass(self) -> None:
        for outcome in ('passed', 'mismatch', 'bad-copy'):
            with self.subTest(outcome=outcome):
                self.mocked_orchestration(outcome)


if __name__ == '__main__':
    unittest.main()
