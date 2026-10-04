"""Offline supervisor lifecycle controls; fake children, no engine launches."""
from __future__ import annotations

import errno
import json
import os
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

# Load only the frozen helper modules' definitions; their server is never used.
HARNESS = Path("/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/pecan-f3b3ef8fc/examples/extensions/benchmarks")
sys.path.insert(0, str(HARNESS))
import measurement
import supervise_cell as supervisor
from output_oracle import Mismatch, sha


def snapshot(oom: int = 0) -> dict[str, str]:
    return {"cpu.max": "1600000 100000", "memory.max": str(32 * 2**30),
            "memory.swap.max": "0", "memory.events": f"oom {oom}\noom_kill {oom}", "memory.peak": "1000"}


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def read(self) -> float:
        return self.now


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
        row = {"phase": "execute", "processes": [
            {"pid": os.getpid(), "pss_bytes": 9000},
            {"pid": 200001, "pss_bytes": 400}, {"pid": 200002, "pss_bytes": 300}]}
        self.output.write_text(json.dumps(row) + "\n")

    def receipt(self) -> dict[str, Any]:
        if self.marks != ["execute", "transition"]:
            raise AssertionError(self.marks)
        return {"execution_sampled": True, "phase_peaks": {"execute": {"pss_bytes": 9700}},
                "phase_sample_counts": {"execute": 1}, "interval_seconds": 0.1}


class SupervisorControls(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = supervisor.CellConfig(engine="graphframes", algorithm="wcc-randomized", mode="local",
            repo=self.root / "repo", harness_repo=self.root / "harness", support=self.root / "support",
            output=self.root / "output", inputs=self.root / "inputs", references=self.root / "references",
            sail_binary=self.root / "sail", graphframes_binary=self.root / "graphframes",
            reference_receipt_sha256="unused", support_sha256="unused")

    @contextmanager
    def fake_cell(self, failure: BaseException | None = None) -> Iterator[list[str]]:
        clock, order = Clock(), []
        reference = {"validation": {"source": 750000, "vertex_rows": 3, "maximum_id": 9},
                     "references": {"wcc_membership": {"identity": {"sha256": "unused"}}}}

        def identity(_config: supervisor.CellConfig) -> dict[str, Any]:
            order.append("identity")
            clock.now += 100
            return {"reference_phase": reference}

        def wait(*_args: object, **_kwargs: object) -> int:
            order.append("wait")
            clock.now += 7
            if failure is not None:
                raise failure
            return 0

        def oracle(*_args: object) -> Mock:
            self.assertEqual(order[-1], "wait")
            order.append("oracle")
            clock.now += 200
            witness = Mock()
            witness.model_dump.return_value = {"rows": 3, "membership_mismatches": 0}
            return witness

        def closure(_receipt: supervisor.CellReceipt) -> None:
            order.append("closure")

        process = Mock(pid=200001, returncode=0)
        process.wait.side_effect = wait
        with ExitStack() as stack:
            changes = [(supervisor, "identities", identity), (supervisor, "processes", list),
                       (supervisor, "close_remaining", closure),
                       (supervisor, "load_wcc_reference", lambda *_args: object()),
                       (supervisor, "verify_wcc_output", oracle),
                       (time, "perf_counter", clock.read),
                       (measurement, "Sampler", FakeSampler),
                       (measurement, "cgroup_snapshot", snapshot),
                       (measurement, "cpu_ticks", lambda: [0] * 10),
                       (subprocess, "Popen", lambda *_args, **_kwargs: process),
                       (os, "killpg", Mock()),
                       (os, "waitpid", lambda *_args: (0, 0))]
            for owner, name, replacement in changes:
                stack.enter_context(patch.object(owner, name, replacement))
            yield order

    def test_timer_excludes_hashes_oracle_and_parent_closure(self) -> None:
        with self.fake_cell() as order:
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, "passed")
        self.assertEqual(receipt.launch_to_exit_seconds, 7)
        self.assertTrue(receipt.engine_wait_completed)
        self.assertEqual(receipt.oracle_seconds, 200)
        self.assertEqual(order, ["identity", "wait", "oracle", "identity", "closure"])
        self.assertEqual(receipt.sampled_engine_pss_peak_bytes, 700)
        self.assertEqual(receipt.sampled_engine_pss_rows, 1)
        self.assertEqual(receipt.memory["phase_peaks"]["execute"]["pss_bytes"], 9700)
        self.assertEqual(json.loads((self.config.output / "receipt.json").read_text())["outcome"], "passed")

    def test_interrupted_wait_always_closes_and_has_no_completed_exit_timer(self) -> None:
        with self.fake_cell(KeyboardInterrupt()) as order:
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, "interrupted")
        self.assertIn("closure", order)
        self.assertNotIn("oracle", order)
        self.assertIsNone(receipt.launch_to_exit_seconds)
        self.assertEqual(receipt.launch_until_interruption_seconds, 7)

    def test_outer_timeout_kill_failure_still_enters_parent_closure(self) -> None:
        with self.fake_cell(subprocess.TimeoutExpired("fake-engine", 30)) as order:
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, "timeout")
        self.assertTrue(receipt.outer_timeout)
        self.assertIn("closure", order)
        self.assertNotIn("oracle", order)
        self.assertFalse(receipt.engine_wait_completed)

    def test_oracle_mismatch_preserved_and_owned_closure_runs(self) -> None:
        with self.fake_cell() as order, patch.object(supervisor, "verify_wcc_output",
                                                     side_effect=Mismatch("wrong component")):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, "mismatch")
        self.assertIn("closure", order)
        self.assertTrue(receipt.engine_wait_completed)
        self.assertFalse(receipt.execution_verified)

    def test_final_receipt_write_failure_replaces_passing_receipt(self) -> None:
        original_save = supervisor.save
        failed = False

        def failing_save(path: Path, value: Any) -> None:
            nonlocal failed
            original_save(path, value)
            if value.outcome == "passed" and not failed:
                failed = True
                raise OSError("late directory fsync failure")

        with self.fake_cell(), patch.object(supervisor, "save", failing_save), \
             self.assertRaisesRegex(OSError, "late directory fsync"):
            supervisor.run_cell(self.config)
        receipt = json.loads((self.config.output / "receipt.json").read_text())
        self.assertEqual(receipt["outcome"], "cleanup_error")
        self.assertEqual(receipt["finalization_errors"][-1]["operation"], "final_receipt_write")

    def test_sigterm_handler_closes_ownership(self) -> None:
        def interrupted_execute(_config: supervisor.CellConfig, _receipt: supervisor.CellReceipt) -> None:
            handler = signal.getsignal(signal.SIGTERM)
            if not callable(handler):
                raise TypeError("SIGTERM handler missing")
            handler(signal.SIGTERM, None)

        with self.fake_cell() as order, patch.object(supervisor, "execute", interrupted_execute):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, "interrupted")
        self.assertEqual(receipt.interruption_signals, [signal.SIGTERM])
        self.assertEqual(order, ["closure"])

    def test_late_oom_downgrades_success(self) -> None:
        with self.fake_cell(), patch.object(measurement, "cgroup_snapshot",
                                            side_effect=[snapshot(), snapshot(), snapshot(), snapshot(1)]):
            receipt = supervisor.run_cell(self.config)
        self.assertTrue(receipt.execution_verified)
        self.assertEqual(receipt.outcome, "oom")

    def test_late_observation_error_downgrades_success(self) -> None:
        with self.fake_cell(), patch.object(measurement, "cgroup_snapshot",
            side_effect=[snapshot(), snapshot(), snapshot(), OSError("final observation failed")]):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, "cleanup_error")
        self.assertEqual(receipt.finalization_errors[-1]["operation"], "final_observation")

    def test_late_owned_closure_error_downgrades_success(self) -> None:
        with self.fake_cell(), patch.object(supervisor, "close_remaining", side_effect=OSError("cannot inspect owner")):
            receipt = supervisor.run_cell(self.config)
        self.assertEqual(receipt.outcome, "cleanup_error")
        self.assertEqual(receipt.finalization_errors[0]["operation"], "owned_process_closure")

    def test_child_nonconvergence_classification_survives_nonzero_exit(self) -> None:
        config = self.config.model_copy(update={"engine": "pecan"})
        process = Mock(pid=200001, returncode=1)

        def wait(**_args: object) -> int:
            (config.output / "engine-receipt.json").write_text(json.dumps({"outcome": "nonconverged"}))
            return 1

        process.wait.side_effect = wait
        with self.fake_cell() as order, patch.object(subprocess, "Popen", return_value=process):
            receipt = supervisor.run_cell(config)
        self.assertEqual(receipt.outcome, "nonconverged")
        self.assertEqual(receipt.engine_returncode, 1)
        self.assertTrue(receipt.engine_wait_completed)
        self.assertIn("closure", order)
        self.assertNotIn("oracle", order)

    def test_classified_engine_failures_are_preserved(self) -> None:
        kinds: tuple[supervisor.Outcome, ...] = ("nonconverged", "cleanup_error", "interrupted", "timeout", "error")
        for kind in kinds:
            with self.subTest(kind=kind):
                receipt = supervisor.CellReceipt(config=self.config.model_copy(update={"engine": "pecan"}),
                    started_utc="control", engine_receipt={"outcome": kind})
                receipt.cgroups["after_engine"] = snapshot()
                with self.assertRaises(supervisor.CellFailure) as raised:
                    supervisor.engine_verdict(receipt)
                self.assertEqual(raised.exception.outcome, kind)
        receipt.outer_timeout = True
        self.assertEqual(supervisor.classify(RuntimeError("wait failed"), receipt), "timeout")

    def test_missing_engine_sample_rejected(self) -> None:
        receipt = supervisor.CellReceipt(config=self.config, started_utc="control", engine_returncode=0,
            engine_wait_completed=True, memory={"execution_sampled": True})
        receipt.cgroups["after_engine"] = snapshot()
        with self.assertRaisesRegex(ValueError, "no complete engine PSS sample"):
            supervisor.engine_verdict(receipt)

    def test_owned_leak_is_killed_and_downgrades_pass(self) -> None:
        row = supervisor.ProcessRow(pid=200003, name="orphan", state="S", starttime=13)
        alive = [row]

        def kill(pid: int, sig: int) -> None:
            self.assertEqual((pid, sig), (row.pid, signal.SIGTERM))
            alive.clear()

        receipt = supervisor.CellReceipt(config=self.config, started_utc="control", execution_verified=True)
        with patch.object(supervisor, "processes", lambda: list(alive)), patch.object(os, "kill", kill), \
             patch.object(measurement, "cgroup_snapshot", snapshot):
            supervisor.finalize(receipt)
        self.assertEqual(receipt.outcome, "cleanup_error")
        self.assertEqual(receipt.remaining_processes, [row])
        self.assertEqual(receipt.remaining_after_cleanup, [])
        self.assertEqual(len(receipt.emergency_cleanup), 1)

    def test_actual_method_does_not_mislabel_external_control(self) -> None:
        for algorithm in ("wcc-randomized", "wcc-min-label"):
            config = self.config.model_copy(update={"algorithm": algorithm})
            self.assertEqual(supervisor.actual_method(config), "randomized-contraction")
        self.assertEqual(supervisor.actual_method(self.config.model_copy(update={"algorithm": "bfs"})), "unweighted-forward-hops")

    def test_module_same_bytes_wrong_path_rejected(self) -> None:
        expected, wrong = self.root / "expected.py", self.root / "wrong.py"
        expected.write_text("PIN=1\n")
        wrong.write_bytes(expected.read_bytes())
        module = ModuleType("control")
        module.__file__ = str(wrong)
        with self.assertRaisesRegex(ValueError, "loaded module identity"):
            supervisor.module_identity(module, expected, sha(expected))
        module.__file__ = str(expected)
        supervisor.module_identity(module, expected, sha(expected))

    def test_directory_fsync_only_ignores_documented_macos_errors(self) -> None:
        with patch.object(sys, "platform", "darwin"), \
             patch.object(os, "fsync", side_effect=OSError(errno.EINVAL, "unsupported")):
            supervisor.fsync_directory(self.root)
        for platform, number in (("linux", errno.EINVAL), ("darwin", errno.EIO)):
            with self.subTest(platform=platform, errno=number), patch.object(sys, "platform", platform), \
                 patch.object(os, "fsync", side_effect=OSError(number, "failed")), self.assertRaises(OSError):
                supervisor.fsync_directory(self.root)


if __name__ == "__main__":
    unittest.main()
