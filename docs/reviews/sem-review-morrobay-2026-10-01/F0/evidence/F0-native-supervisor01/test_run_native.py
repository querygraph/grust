"""Bounded protocol controls; mocked children execute no native program."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Literal, cast
from unittest import mock

import models
import run_native


def pin(path: Path, size: int = 1) -> models.FilePin:
    return models.FilePin(path=path, bytes=size, sha256="0" * 64)


def config(output: Path) -> models.Config:
    source = Path("/borrowed")
    names = ("README.md", "runs.jsonl", "runs-binary-search.jsonl", "csr-floor/Cargo.toml",
             "csr-floor/Cargo.lock", "csr-floor/src/main.rs")
    data = tuple(models.Dataset(name=cast(Literal["cit-Patents", "graph500-24"], name), vertices=pin(Path("/ssd") / name / "v.parquet"),
        edges=pin(Path("/ssd") / name / "e.parquet"), evidence=pin(Path("/evidence") / name),
        vertex_rows=vertices, edge_rows=edges) for name, vertices, edges in
        (("cit-Patents", 3774768, 16518947), ("graph500-24", 8870942, 260379520)))
    return models.Config(source_root=source, source_files=tuple(pin(source / name) for name in names),
        helper_files=(pin(Path("/helper.py")),), output=output, lock=Path("/serial.lock"), refuse_locks=(),
        cargo=pin(Path("/cargo")), rustc=pin(Path("/rustc")), time=pin(Path("/time")), ps=pin(Path("/ps")),
        binary=pin(Path("/target/release/csr-floor")), build_receipt=pin(Path("/build.json")),
        datasets=data, ssd_root=Path("/ssd"))


def build(configured: models.Config) -> models.RootBuild:
    before = {p.path.relative_to(configured.source_root / "csr-floor").as_posix(): p
              for p in configured.source_files if p.path.is_relative_to(configured.source_root / "csr-floor")}
    assert configured.binary is not None
    return models.RootBuild(started_utc="started", finished_utc="finished",
        outcome="passed_optimized_native_F0_build", owner_pid=1, cargo_pid=2, errors=[],
        source_before=before, source_after=before, cargo_version="cargo 1.98.1 (actual)",
        rustc_verbose="rustc 1.98.1 (actual)\nhost: x86_64-apple-darwin", environment={
            "CARGO_INCREMENTAL": "0", "CARGO_PROFILE_RELEASE_OPT_LEVEL": "3",
            "CARGO_PROFILE_RELEASE_DEBUG": "0", "CARGO_PROFILE_RELEASE_STRIP": "true",
            "CARGO_PROFILE_RELEASE_CODEGEN_UNITS": "1", "CARGO_PROFILE_RELEASE_LTO": "thin"},
        command=("/cargo", "build", "--locked", "--release", "--manifest-path",
                 str(configured.source_root / "csr-floor/Cargo.toml")), returncode=0,
        binary=configured.binary, file_type="Mach-O 64-bit executable x86_64", locks_released=True)


def result(data: models.Dataset, undirected: bool) -> models.NativeResult:
    arcs = data.edge_rows * (2 if undirected else 1)
    return models.NativeResult(vertices=data.vertex_rows, edges=data.edge_rows, arcs=arcs,
        undirected=undirected, target_bits=32, id_mapping="direct table", threads=4,
        read_seconds=0.1, map_seconds=0.2, build_seconds=0.3, total_seconds=0.7,
        max_degree=1, csr_bytes=(data.vertex_rows + 1) * 8 + data.vertex_rows * 8 + arcs * 4)


class Controls(unittest.TestCase):
    def test_exact_four_count_and_byte_contracts(self) -> None:
        cfg = config(Path("/output"))
        for data in cfg.datasets:
            for undirected in (False, True):
                run_native.validate_result(result(data, undirected), data, undirected)

    def test_false_arc_count(self) -> None:
        data = config(Path("/output")).datasets[0]
        with self.assertRaises(ValueError):
            run_native.validate_result(result(data, False).model_copy(update={"arcs": 1}), data, False)

    def test_false_csr_width(self) -> None:
        data = config(Path("/output")).datasets[1]
        with self.assertRaises(ValueError):
            run_native.validate_result(result(data, True).model_copy(update={"csr_bytes": 1}), data, True)

    def test_only_four_threads_and_raw_integer_counts(self) -> None:
        raw = result(config(Path("/output")).datasets[0], False).model_dump()
        for update in ({"threads": 8}, {"vertices": "3774768"}, {"undirected": 1}, {"read_seconds": float("nan")}):
            with self.assertRaises(ValueError):
                models.NativeResult.model_validate({**raw, **update})

    def test_time_unit_bytes_and_one_observation(self) -> None:
        self.assertEqual(run_native.parse_time("  8658452480  maximum resident set size\n"), 8658452480)
        for text in ("", "0 maximum resident set size", "1 maximum resident set size\n2 maximum resident set size"):
            with self.assertRaises(ValueError):
                run_native.parse_time(text)

    def test_root_actual_build_contract(self) -> None:
        cfg = config(Path("/output"))
        run_native.validate_build(build(cfg), cfg)

    def test_build_source_or_compiler_change_refused(self) -> None:
        cfg = config(Path("/output"))
        updates: list[dict[str, object]] = [{"source_after": {}}, {"cargo_version": "cargo 1.97.1 (historical)"},
                                         {"command": ("/cargo", "build", "--release")}, {"environment": {}}]
        for update in updates:
            with self.assertRaises(ValueError):
                run_native.validate_build(build(cfg).model_copy(update=update), cfg)

    def test_initial_receipt_serialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cfg = config(root)
            receipt = models.Receipt(config=cfg, config_pin=pin(Path("/config.json")),
                helper_pin=pin(Path("/helper.py")), started_utc="started", parent_pid=1)
            run_native.save(receipt)
            self.assertEqual(models.Receipt.model_validate_json((root / "receipt.json").read_bytes()), receipt)

    def test_input_identity_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input"
            path.write_bytes(b"original")
            sealed = run_native.file_pin(path)
            run_native.inventory((sealed,))
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                run_native.inventory((sealed,))

    def test_owned_forced_cleanup_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cfg = config(root)
            receipt = models.Receipt(config=cfg, config_pin=pin(Path("/config.json")),
                helper_pin=pin(Path("/helper.py")), started_utc="started", parent_pid=1)
            child = models.Child(id="cit-directed", command=("/not-executed",), outcome="running")
            receipt.children.append(child)
            process = mock.MagicMock(spec=subprocess.Popen)
            process.pid, process.returncode = 100, 0
            process.wait.return_value, process.poll.return_value = 0, 0
            with mock.patch("subprocess.Popen", return_value=cast(subprocess.Popen[bytes], process)), \
                 mock.patch.object(run_native, "group_members", side_effect=[("owned residual",), ()]), \
                 mock.patch.object(run_native, "terminate"):
                run_native.execute(receipt, child, 1, {})
            self.assertEqual(child.outcome, "error")
            self.assertTrue(child.forced_cleanup)
            self.assertFalse(child.group_remaining)


if __name__ == "__main__":
    unittest.main()
