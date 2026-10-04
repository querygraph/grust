"""Offline physical-oracle and observer compatibility controls; no engine launch."""
from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
import signal
import subprocess
import tarfile
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError
from pyspark_pecan.types import IterationEvent

import cell
import oracle
import run_one


@dataclass(slots=True)
class Fixture:
    reference: Path
    result: Path
    pairs: npt.NDArray[np.int64]
    expected: npt.NDArray[np.int64]

    def write(self, ids: list[int | None], labels: list[int | None],
              name: str = "part.parquet") -> None:
        pq.write_table(pa.table({"id": pa.array(ids, type=pa.int64()),
                                 "component": pa.array(labels, type=pa.int64())}),
                       self.result / name)


@pytest.fixture
def graph(tmp_path: Path) -> Fixture:
    pairs = np.array([[1, 1], [3, 1], [8, 8], [13, 8], [21, 21]], dtype="<i8")
    reference = tmp_path / "reference.i64le"
    pairs.tofile(reference)
    result = tmp_path / "result"
    result.mkdir()
    expected = oracle.load_oracle(reference, oracle.sha(reference), 5, 21)
    return Fixture(reference, result, pairs, expected)


def test_permuted_exact_membership_includes_isolate(graph: Fixture) -> None:
    graph.write([21, 3, 13, 1, 8], [21, 1, 8, 1, 8])
    result = oracle.verify_output(graph.result, graph.expected, 5)
    assert (result.rows, result.unique, result.membership_mismatches) == (5, 5, 0)
    assert (result.components, result.largest_component_vertices) == (3, 2)
    assert result.result_files == oracle.inventory(graph.result)


@pytest.mark.parametrize("labels", [[1, 1, 1, 1, 1], [1, 3, 8, 8, 21], [3, 3, 8, 8, 21]])
def test_false_merge_split_or_nonminimum_label_fails(graph: Fixture, labels: list[int]) -> None:
    graph.write([1, 3, 8, 13, 21], labels)
    with pytest.raises(oracle.Mismatch, match="membership mismatch"):
        oracle.verify_output(graph.result, graph.expected, 5)


@pytest.mark.parametrize(("ids", "labels"), [
    ([1, 3, 8, 13], [1, 1, 8, 8]),
    ([1, 3, 8, 13, 13], [1, 1, 8, 8, 8]),
    ([1, 3, 8, 13, 20], [1, 1, 8, 8, 20]),
    ([1, 3, 8, 13, None], [1, 1, 8, 8, 21]),
    ([1, 3, 8, 13, 21], [1, 1, 8, 8, None]),
    ([-1, 3, 8, 13, 21], [1, 1, 8, 8, 21]),
    ([0, 3, 8, 13, 21], [1, 1, 8, 8, 21]),
    ([1, 3, 8, 13, 22], [1, 1, 8, 8, 21]),
])
def test_invalid_domain_or_null_rejected(graph: Fixture, ids: list[int | None],
                                        labels: list[int | None]) -> None:
    graph.write(ids, labels)
    with pytest.raises(oracle.Mismatch):
        oracle.verify_output(graph.result, graph.expected, 5)


def test_duplicate_across_files_rejected(graph: Fixture) -> None:
    graph.write([1, 3, 8], [1, 1, 8])
    graph.write([13, 21, 21], [8, 21, 21], "other.parquet")
    with pytest.raises(oracle.Mismatch, match="duplicate"):
        oracle.verify_output(graph.result, graph.expected, 5)


def test_wrong_physical_type_not_cast_to_pass(graph: Fixture) -> None:
    pq.write_table(pa.table({"id": pa.array([1, 3, 8, 13, 21], type=pa.int64()),
                            "component": pa.array([1, 1, 8, 8, 21], type=pa.int32())}),
                   graph.result / "part.parquet")
    with pytest.raises(oracle.Mismatch, match="exactly"):
        oracle.verify_output(graph.result, graph.expected, 5)


def test_absent_output_not_pass(graph: Fixture) -> None:
    with pytest.raises(oracle.Mismatch, match="no result Parquet"):
        oracle.verify_output(graph.result, graph.expected, 5)


def test_oracle_hash_and_length_rejected(graph: Fixture) -> None:
    with pytest.raises(ValueError, match="hash/length"):
        oracle.load_oracle(graph.reference, "wrong", 5, 21)
    with pytest.raises(ValueError, match="hash/length"):
        oracle.load_oracle(graph.reference, oracle.sha(graph.reference), 6, 21)


def test_oracle_mutation_during_read_rejected(graph: Fixture) -> None:
    digest = oracle.sha(graph.reference)
    with patch.object(oracle, "sha", side_effect=[digest, "changed"]):
        with pytest.raises(ValueError, match="changed during read"):
            oracle.load_oracle(graph.reference, digest, 5, 21)


def test_output_mutation_during_read_rejected(graph: Fixture) -> None:
    graph.write([1, 3, 8, 13, 21], [1, 1, 8, 8, 21])
    before = oracle.inventory(graph.result)
    after = dict(before, extra=oracle.FileIdentity(bytes=1, sha256="changed"))
    with patch.object(oracle, "inventory", side_effect=[before, after]):
        with pytest.raises(ValueError, match="changed during verification"):
            oracle.verify_output(graph.result, graph.expected, 5)


def test_output_symlink_rejected(graph: Fixture) -> None:
    (graph.result / "outside.parquet").symlink_to(graph.reference)
    with pytest.raises(ValueError, match="symlink"):
        oracle.verify_output(graph.result, graph.expected, 5)


def test_actual_typed_and_legacy_events_preserve_identical_metrics() -> None:
    values = {"kind": "iteration_end", "algorithm": "wcc_randomized_fused", "iteration": 3,
              "run_path": "file:///owned/run", "active_vertices": 5, "edges_before": 8,
              "edges_after": 2, "coefficient_a": 18446744073709551615, "coefficient_b": 0,
              "plan": None}
    expected = {key: value for key, value in values.items() if key != "run_path" and value is not None}
    assert cell.normalize_event(values) == expected
    assert cell.normalize_event(IterationEvent.model_validate(values)) == expected
    assert values["run_path"] == "file:///owned/run"


@pytest.mark.parametrize("event", [
    None, [], "event", {"kind": "bad", "algorithm": "wcc", "iteration": 1},
    {"kind": "iteration_end", "iteration": 1},
    {"kind": "iteration_end", "algorithm": "wcc", "iteration": True},
    {"kind": "iteration_end", "algorithm": "wcc", "iteration": -1},
    {"kind": "iteration_end", "algorithm": "wcc", "iteration": "1"},
    {"kind": "iteration_end", "algorithm": "wcc", "iteration": 1, "residual": float("nan")},
    {"kind": "iteration_end", "algorithm": "wcc", "iteration": 1, "residual": float("inf")},
])
def test_bad_observer_record_is_not_silently_accepted(event: object) -> None:
    with pytest.raises((ValueError, ValidationError)):
        cell.normalize_event(event)


def test_round_intervals_use_differences_and_retain_unfinished_rounds() -> None:
    events = [{"kind": kind, "iteration": iteration, "elapsed_seconds": elapsed}
              for kind, iteration, elapsed in [("iteration_start", 1, 10.0), ("iteration_end", 1, 14.0),
                                                ("iteration_start", 2, 15.0), ("iteration_end", 2, 18.0)]]
    result = cell.round_summary(events, 23.0)
    assert result["completed_round_durations"] == [{"iteration": 1, "seconds": 4.0},
                                                    {"iteration": 2, "seconds": 3.0}]
    assert (result["pre_first_round_seconds"], result["post_last_round_seconds"]) == (10.0, 5.0)
    events.append({"kind": "iteration_start", "iteration": 3, "elapsed_seconds": 20.0})
    assert cell.round_summary(events, None)["incomplete_rounds"] == [3]
    assert cell.round_summary([], None)["completed_round_durations"] == []


@pytest.mark.parametrize("events", [
    [{"kind": "iteration_end", "iteration": 1, "elapsed_seconds": 1.0}],
    [{"kind": "iteration_start", "iteration": 1, "elapsed_seconds": 1.0},
     {"kind": "iteration_start", "iteration": 1, "elapsed_seconds": 2.0}],
])
def test_bad_round_sequence_rejected(events: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError):
        cell.round_summary(events, None)


def receipt_for(root: Path) -> cell.Receipt:
    config = cell.CellConfig(repo=root, controller_sha=cell.CANDIDATE, harness_repo=root,
                             vertices=root / "vertices", edges=root / "edges", reference=root / "reference",
                             output=root, mode="local")
    return cell.Receipt(started_utc="offline", arguments=config, source_pins={}, helpers_sha256={},
                        resources={}, boundaries={})


@pytest.mark.parametrize("fail", [False, True])
def test_timers_delegate_once_and_restore_on_original_failure(tmp_path: Path, fail: bool) -> None:
    calls: list[str] = []

    class Run:
        path = (tmp_path / "staging" / "run").as_uri()

        def materialize(self, value: str) -> str:
            calls.append(value)
            if fail and value == "edges":
                raise RuntimeError("original write failure")
            return value

    def schema() -> None:
        calls.append("schema")

    def snapshot(run: Run, *, count_vertices: bool) -> str:
        assert count_vertices is False
        assert run.materialize("vertices") == "vertices"
        assert run.materialize("edges") == "edges"
        return "original result"

    module = SimpleNamespace(_check_input_schema=schema, _snapshot=snapshot, StagingRun=Run)
    original = (module._check_input_schema, module._snapshot, Run.materialize)
    receipt = receipt_for(tmp_path)
    with patch.object(cell, "algorithms", module), cell.input_timers(receipt):
        module._check_input_schema()
        if fail:
            with pytest.raises(RuntimeError, match="original write failure"):
                module._snapshot(Run(), count_vertices=False)
        else:
            assert module._snapshot(Run(), count_vertices=False) == "original result"
    assert calls == ["schema", "vertices", "edges"]
    assert (module._check_input_schema, module._snapshot, Run.materialize) == original
    assert len(receipt.timings["input_snapshot_materialize_seconds"]) == 2
    assert receipt.timings["input_snapshot_residual_seconds"] >= 0


def test_timers_reject_unwatched_staging_before_original_call(tmp_path: Path) -> None:
    calls: list[str] = []

    class Run:
        path = (tmp_path / "outside").as_uri()

        def materialize(self, value: str) -> str:
            calls.append(value)
            return value

    def snapshot(run: Run) -> str:
        return run.materialize("write")

    module = SimpleNamespace(_check_input_schema=lambda: None, _snapshot=snapshot, StagingRun=Run)
    original = (module._check_input_schema, module._snapshot, Run.materialize)
    with patch.object(cell, "algorithms", module), cell.input_timers(receipt_for(tmp_path)):
        with pytest.raises(ValueError, match="unexpected GraphUtils staging root"):
            module._snapshot(Run())
    assert calls == []
    assert (module._check_input_schema, module._snapshot, Run.materialize) == original


@pytest.mark.parametrize(("failure", "outcome"), [
    (oracle.Mismatch("injected physical mismatch"), "mismatch"),
    (RuntimeError("injected worker failure"), "error"),
    (TimeoutError("injected deadline"), "timeout"),
    (cell.algorithms.ConvergenceError("injected cap"), "nonconverged"),
    (KeyboardInterrupt("injected interrupt"), "interrupted"),
])
def test_failure_receipt_retains_original_error_without_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException, outcome: str,
) -> None:
    vertices, edges, reference = (tmp_path / name for name in ("vertices.parquet", "edges.parquet", "oracle.i64le"))
    pq.write_table(pa.table({"id": pa.array([1], type=pa.int64())}), vertices)
    pq.write_table(pa.table({"source": pa.array([1], type=pa.int64()),
                            "target": pa.array([1], type=pa.int64())}), edges)
    np.array([[1, 1]], dtype="<i8").tofile(reference)
    output = tmp_path / "cell"
    argv = ["cell", "--repo", str(tmp_path), "--controller-sha", cell.CANDIDATE,
            "--harness-repo", str(tmp_path), "--vertices", str(vertices), "--edges", str(edges),
            "--reference", str(reference), "--output", str(output), "--mode", "local"]
    monkeypatch.setattr(cell.sys, "argv", argv)
    for name, value in (("VERTICES_SHA", oracle.sha(vertices)), ("EDGES_SHA", oracle.sha(edges)),
                        ("REFERENCE_SHA", oracle.sha(reference)), ("ROWS", 1), ("EDGE_ROWS", 1)):
        monkeypatch.setattr(cell, name, value)
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")
    original_exists = Path.exists

    def exists(path: Path) -> bool:
        return True if str(path) in ("/.dockerenv", "/proc/stat") else original_exists(path)

    def fail_execute(config: cell.CellConfig, receipt: cell.Receipt) -> None:
        raise failure

    handlers = {number: signal.getsignal(number) for number in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM)}
    try:
        with patch.object(Path, "exists", exists), patch.object(cell, "identity", return_value={"offline_stub": True}), \
             patch.object(cell.runtime, "package_versions", return_value={}), patch.object(cell, "execute", fail_execute), \
             patch.dict(cell.os.environ):
            assert cell.main() == 1
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["outcome"] == outcome
    assert str(failure) in receipt["error"]
    assert receipt["correctness"] is None
    assert receipt["inputs_before"] == receipt["inputs_after"]
    assert receipt["identities"]["before"] == receipt["identities"]["after"] == {"offline_stub": True}


@pytest.mark.parametrize("foreign", [None, "image", "entrypoint", "command", "mount", "writable"])
def test_observer_timeout_only_stops_proven_owned_container(tmp_path: Path, foreign: str | None) -> None:
    command = run_one.DOCKER + ["run", "--name", "typed-offline-probe", run_one.IMAGE, "-I", "-c", "probe"]
    item: dict[str, Any] = {"Image": run_one.IMAGE, "Id": "owned-immutable-id",
                           "Config": {"Entrypoint": [run_one.PYTHON], "Cmd": ["-I", "-c", "probe"]},
                           "Mounts": [{"Name": "sail-extension-targets", "RW": False}],
                           "State": {"Running": True}}
    if foreign == "image":
        item["Image"] = "foreign"
    elif foreign == "entrypoint":
        item["Config"]["Entrypoint"] = ["foreign"]
    elif foreign == "command":
        item["Config"]["Cmd"] = ["foreign"]
    elif foreign == "mount":
        item["Mounts"][0]["Name"] = "foreign"
    elif foreign == "writable":
        item["Mounts"][0]["RW"] = True
    results: list[object] = [subprocess.TimeoutExpired(command, 90),
                            subprocess.CompletedProcess([], 0, json.dumps([item]), "")]
    if foreign is None:
        results.append(subprocess.CompletedProcess([], 0, "stopped", ""))
    with patch.object(run_one.subprocess, "run", side_effect=results) as mock_run:
        with pytest.raises(subprocess.TimeoutExpired):
            run_one.observe(command, tmp_path, "admission")
        calls = mock_run.call_args_list
    saved = json.loads((tmp_path / "admission-timeout.json").read_text())
    assert saved["command"] == command
    if foreign is None:
        assert len(calls) == 3
        assert calls[-1].args[0] == run_one.DOCKER + ["stop", "--time", "10", "owned-immutable-id"]
        assert saved["stop"]["returncode"] == 0
    else:
        assert len(calls) == 2
        assert "cleanup_error" in saved and "stop" not in saved


@pytest.mark.parametrize("fault", ["host-after", "final-idle", "late-helper-identity"])
def test_wrapper_final_fault_cannot_pass_or_lose_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    host, old = tmp_path / "host", tmp_path / "old"
    host.mkdir()
    old.mkdir()
    matrix_file = old / "run_matrix.py"
    matrix_file.write_text("# offline import is mocked\n")
    (old / "sem-wcc-support-pins.json").write_text("{}")
    manifest = host / "support-manifest.json"
    manifest.write_text('{"files_sha256": {}}')
    monkeypatch.setattr(run_one, "HOST", host)
    monkeypatch.setattr(run_one, "OLD", old)
    monkeypatch.setattr(run_one, "MATRIX", matrix_file)
    monkeypatch.setattr(run_one.sys, "argv", ["run_one", "--run-id", "typed-offline",
                        "--revision", "candidate", "--mode", "local", "--kind", "smoke",
                        "--support-sha256", run_one.sha(manifest)])
    actual_sha = run_one.sha
    helper_reads = 0

    def fake_sha(path: Path) -> str:
        nonlocal helper_reads
        if path == matrix_file:
            return run_one.MATRIX_SHA
        if path == old / "sem-wcc-support-pins.json":
            return "23ee8504d18cd8db931421f81854e0e01d05dcb6bb5a5c031e1684089f3d69ad"
        if path == Path(run_one.__file__):
            helper_reads += 1
            if fault == "late-helper-identity" and helper_reads >= 3:
                return "changed"
        return actual_sha(path)

    monkeypatch.setattr(run_one, "sha", fake_sha)
    loader = SimpleNamespace(exec_module=lambda module: None)
    matrix = SimpleNamespace(preflight=lambda *args: {}, run_container=lambda *args: {
        "inspect": {"state": {"ExitCode": 0, "OOMKilled": False, "Running": False}},
        "attach_returncode": 0, "outer_timeout": False, "transport_errors": [], "remove": {"returncode": 0}})
    monkeypatch.setattr(run_one.importlib.util, "spec_from_file_location", lambda *args: SimpleNamespace(loader=loader))
    monkeypatch.setattr(run_one.importlib.util, "module_from_spec", lambda spec: matrix)

    def observe(command: list[str], output: Path, label: str, stdout: Any = None) -> subprocess.CompletedProcess[bytes]:
        if label == "collection":
            data = b'{"outcome": "passed"}\n'
            with tarfile.open(fileobj=stdout, mode="w") as archive:
                entry = tarfile.TarInfo("receipt.json")
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        return subprocess.CompletedProcess(command, 0, b"{}", b"")

    monkeypatch.setattr(run_one, "observe", observe)
    snapshots: list[object] = [{}, RuntimeError("host snapshot failure") if fault == "host-after" else {}]
    idle_results: list[object] = [None, None, None,
                                RuntimeError("idle check failure") if fault == "final-idle" else None]
    old_path = list(run_one.sys.path)
    try:
        with patch.object(run_one, "host_snapshot", side_effect=snapshots), \
             patch.object(run_one, "idle", side_effect=idle_results), patch.dict(run_one.os.environ):
            assert run_one.main() == 1
    finally:
        run_one.sys.path[:] = old_path
    final = json.loads((host / "typed-offline" / "result.json").read_text())
    assert final["outcome"] == "error"
    if fault == "final-idle":
        assert final["lock_retained"] is True
        assert "idle check failure" in final["final_cleanup_error"]
    elif fault == "host-after":
        assert "host snapshot failure" in final["final_observation_error"]
    else:
        assert "AssertionError" in final["error"]
