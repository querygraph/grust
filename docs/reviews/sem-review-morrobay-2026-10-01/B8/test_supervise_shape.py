"""Offline child, timer, oracle, ownership and disk failure controls."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Self
from unittest.mock import Mock, patch

HARNESS = Path('/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/pecan-f3b3ef8fc/examples/extensions/benchmarks')
sys.path.insert(0, str(HARNESS))
import measurement
import shape_oracle
import supervise_shape as supervisor
from shape_reference import sha


def cgroup(oom: int = 0) -> dict[str, str]:
    return {'cpu.max': '1600000 100000', 'memory.max': str(32 * 2**30), 'memory.swap.max': '0',
            'memory.events': f'oom {oom}\noom_kill {oom}', 'memory.peak': '1000'}


class FakeSampler:
    error: str | None = None

    def __init__(self, output: Path, **_settings: Any) -> None:
        self.output = output
        self.marks: list[str] = []

    def __enter__(self) -> Self:
        return self

    def mark(self, phase: str) -> None:
        self.marks.append(phase)

    def __exit__(self, *_error: object) -> None:
        row = {'phase': 'execute', 'processes': [{'pid': os.getpid(), 'pss_bytes': 9000},
               {'pid': 200001, 'pss_bytes': 400}, {'pid': 200002, 'pss_bytes': 300}]}
        self.output.write_text(json.dumps(row) + '\n')

    def receipt(self) -> dict[str, Any]:
        if self.marks != ['execute', 'transition']:
            raise AssertionError(self.marks)
        return {'execution_sampled': True, 'phase_peaks': {'execute': {'pss_bytes': 9700}}}


class SupervisorControls(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = supervisor.CellConfig(dataset='signed-fixture', shape='adjacency', variant='union',
            repo=self.root/'repo', harness_repo=self.root/'harness', support=self.root/'support',
            output=self.root/'output', vertices=self.root/'vertices.parquet', edges=self.root/'edges.parquet',
            references=self.root/'references', binary=self.root/'sail',
            reference_receipt_sha256='0'*64, support_sha256='1'*64)

    @contextmanager
    def fake_cell(self, failure: BaseException | None = None) -> Iterator[list[str]]:
        clock = [0.0]
        order: list[str] = []

        def identity(_config: supervisor.CellConfig) -> dict[str, Any]:
            order.append('identity')
            clock[0] += 100
            return {'reference_phase': {'vertex_rows': 3, 'isolated_vertices': 1}}

        def wait(*_args: object, **_kwargs: object) -> int:
            order.append('wait')
            clock[0] += 7
            if failure is not None:
                raise failure
            engine = self.config.output/'engine'
            self.assertFalse(engine.exists(), 'child must receive a fresh output directory')
            engine.mkdir()
            (engine/'plan-shape-result.txt').write_text('RAW signed BIGINT physical plan\n')
            config = json.loads((self.config.output/'engine-config.json').read_text())
            witness = {'outcome': 'passed', 'config': config, 'controller_pin': supervisor.PECAN,
                'result_exported': True, 'cleanup_errors': [], 'staging_payload_after_shutdown': [],
                'error': None, 'actual_method': 'adjacency-union',
                'plans': [{'file': 'plan-shape-result.txt', 'relation': 'shape-result', 'scope': 'raw planning'}]}
            (engine/'engine-receipt.json').write_text(json.dumps(witness))
            return 0

        def oracle(*_args: object, **_kwargs: object) -> Mock:
            self.assertEqual(order[-1], 'wait')
            order.append('oracle')
            clock[0] += 200
            witness = Mock()
            witness.model_dump.return_value = {'rows': 3, 'full_oracle': True}
            return witness

        process = Mock(pid=200001, returncode=0)
        process.wait.side_effect = wait
        with ExitStack() as stack:
            changes = [(supervisor, 'identities', identity), (supervisor, 'processes', list),
                (supervisor, 'close_remaining', lambda _receipt: order.append('closure')),
                (shape_oracle, 'load_shape_reference', lambda *_args: object()),
                (shape_oracle, 'verify_shape_output', oracle), (time, 'perf_counter', lambda: clock[0]),
                (measurement, 'Sampler', FakeSampler), (measurement, 'cgroup_snapshot', cgroup),
                (measurement, 'cpu_ticks', lambda: [0]*10), (subprocess, 'Popen', lambda *_args, **_kwargs: process),
                (os, 'killpg', Mock()), (os, 'waitpid', lambda *_args: (0, 0)),
                (shutil, 'disk_usage', lambda _path: Mock(free=256*2**30))]
            for owner, name, replacement in changes:
                stack.enter_context(patch.object(owner, name, replacement))
            yield order

    def test_timer_excludes_hashes_oracle_parent_closure_and_retains_raw_plan(self) -> None:
        with self.fake_cell() as order:
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'passed')
        self.assertEqual(receipt.launch_to_exit_seconds, 7)
        self.assertEqual(receipt.oracle_seconds, 200)
        self.assertEqual(order, ['identity', 'wait', 'oracle', 'identity', 'closure'])
        self.assertEqual(receipt.sampled_engine_pss_peak_bytes, 700)
        self.assertEqual(receipt.actual_engine_method, 'adjacency-union')
        plan = self.config.output/'engine/plan-shape-result.txt'
        self.assertEqual(receipt.plans['engine/plan-shape-result.txt']['sha256'], sha(plan))

    def test_interrupted_wait_has_no_completed_exit_timer_and_always_closes(self) -> None:
        with self.fake_cell(KeyboardInterrupt()) as order:
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'interrupted')
        self.assertIsNone(receipt.launch_to_exit_seconds)
        self.assertEqual(receipt.launch_until_interruption_seconds, 7)
        self.assertIn('closure', order)
        self.assertNotIn('oracle', order)

    def test_oracle_mismatch_is_durable_and_not_a_timing_pass(self) -> None:
        with self.fake_cell(), patch.object(shape_oracle, 'verify_shape_output', side_effect=shape_oracle.Mismatch('wrong pair')):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'mismatch')
        self.assertFalse(receipt.execution_verified)
        self.assertEqual(json.loads((self.config.output/'receipt.json').read_text())['outcome'], 'mismatch')

    def test_disk_refusal_precedes_child_launch(self) -> None:
        with self.fake_cell() as order, patch.object(shutil, 'disk_usage', return_value=Mock(free=1)):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'error')
        self.assertIsNone(receipt.engine_pid)
        self.assertNotIn('wait', order)
        self.assertIn('closure', order)

    def test_missing_plans_disqualifies_an_otherwise_successful_child(self) -> None:
        with self.fake_cell(), patch.object(supervisor, 'plan_inventory', side_effect=ValueError('missing raw physical plans')):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'error')
        self.assertFalse(receipt.execution_verified)

    def test_outer_timeout_preserves_failure_and_enters_parent_closure(self) -> None:
        with self.fake_cell(subprocess.TimeoutExpired('fake', 30)) as order:
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'timeout')
        self.assertTrue(receipt.outer_timeout)
        self.assertIn('closure', order)
        self.assertNotIn('oracle', order)

    def test_own_process_leak_is_closed_and_downgrades_candidate_pass(self) -> None:
        row = supervisor.ProcessRow(pid=200003, name='orphan', state='S', starttime=13)
        alive = [row]
        def kill(pid: int, sig: int) -> None:
            self.assertEqual((pid, sig), (row.pid, signal.SIGTERM))
            alive.clear()
        receipt = supervisor.CellReceipt(config=self.config, started_utc='control', execution_verified=True, ownership_admitted=True)
        with patch.object(supervisor, 'processes', lambda: list(alive)), patch.object(os, 'kill', kill), \
             patch.object(measurement, 'cgroup_snapshot', cgroup):
            supervisor.finalize(receipt)
        self.assertEqual(receipt.outcome, 'cleanup_error')
        self.assertEqual(receipt.remaining_processes, [row])
        self.assertEqual(receipt.remaining_after_cleanup, [])
        self.assertEqual(len(receipt.emergency_cleanup), 1)

    def test_final_oom_and_final_identity_change_downgrade_success(self) -> None:
        with self.fake_cell(), patch.object(measurement, 'cgroup_snapshot', side_effect=[cgroup(), cgroup(), cgroup(), cgroup(1)]):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'oom')
        self.config = self.config.model_copy(update={'output': self.root/'different'})
        with self.fake_cell(), patch.object(supervisor, 'identities', side_effect=[{'version': 1}, {'version': 2}]):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'error')
        self.assertIn('identity changed', receipt.error or '')

    def test_same_bytes_wrong_module_origin_is_refused(self) -> None:
        expected, wrong = self.root/'expected.py', self.root/'wrong.py'
        expected.write_text('PIN=1\n')
        wrong.write_bytes(expected.read_bytes())
        module = ModuleType('control')
        module.__file__ = str(wrong)
        with self.assertRaisesRegex(ValueError, 'loaded module identity'):
            supervisor.module_identity(module, expected, sha(expected))

    def test_preexisting_process_is_refused_without_launch_or_signals(self) -> None:
        row = supervisor.ProcessRow(pid=200004, name='unclaimed', state='S', starttime=19)
        with self.fake_cell(), patch.object(supervisor, 'processes', return_value=[row]), \
             patch.object(subprocess, 'Popen') as launched, patch.object(os, 'kill') as signaled:
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'error')
        self.assertEqual(receipt.preexisting_processes, [row])
        self.assertEqual(receipt.final_processes, [row])
        self.assertEqual(receipt.emergency_cleanup, [])
        launched.assert_not_called()
        signaled.assert_not_called()

    def test_partial_oracle_progress_survives_mismatch(self) -> None:
        progress = shape_oracle.Progress(file='part.parquet', rows_examined=7, physical_schemas=[])
        def wrong(*_args: object, **kwargs: Any) -> Mock:
            kwargs['progress'](progress)
            raise shape_oracle.Mismatch('wrong signed pair')
        with self.fake_cell(), patch.object(shape_oracle, 'verify_shape_output', wrong):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, 'mismatch')
        self.assertEqual(receipt.oracle_progress, progress)
        self.assertEqual(json.loads((self.config.output/'receipt.json').read_text())['oracle_progress']['rows_examined'], 7)

    def test_relative_config_paths_are_rejected(self) -> None:
        text = self.config.model_dump(mode='json')
        text['vertices'] = 'relative.parquet'
        with self.assertRaises(ValueError):
            supervisor.CellConfig.model_validate(text)


if __name__ == '__main__':
    unittest.main()
