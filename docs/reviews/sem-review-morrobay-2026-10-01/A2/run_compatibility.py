"""Fresh tiny engine controls and an explicitly scoped signed-isolate witness.

This is compatibility evidence, not a performance comparison. The host owns
the private container and lock. Every oracle runs after its engine child exits.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from output_oracle import (
    FileIdentity,
    PhysicalField,
    PhysicalSchema,
    inventory,
    load_bfs_reference,
    load_wcc_reference,
    require,
    sha,
    verify_bfs_output,
    verify_wcc_output,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

LOGGER = logging.getLogger(__name__)
PECAN = "f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a"
HARNESS = "6ae2e43a903c2cee02da170465c922c72b76198e"
SAIL_SHA = "5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec"
GF_SHA = "b2a7fc0f077fafc158aaa8a45ac32e5f2af5b3d96b8050c348421fa79442722f"
ISOLATE = -7694170072594669674
Engine = Literal["graphframes", "pecan"]
Algorithm = Literal["wcc-randomized", "wcc-min-label", "bfs"]
PINS = {
    "test-wcc-directed/test-wcc-directed.v": "18141096de2a76fe8eb7209177e51f78b44b07b1c33bf6bdf576d24568b97179",
    "test-wcc-directed/test-wcc-directed.e": "2d2967618f1e642a5db81ac9a3c2b571157991e2a7bbc9dcea5296253dfdc805",
    "test-wcc-directed/test-wcc-directed.properties": "97631846ac6422b68aea2020a1ce9cfa5918107925c17247c610be798115a6fa",
    "test-wcc-directed/test-wcc-directed-WCC": "7a07f80af0a965e41d3283702183a41151563b43287cf85b54fe1eb9585bb99b",
    "test-bfs-directed/test-bfs-directed.v": "bf794518e35d7f1ce3a50b3058c4191bb9401e568fc645d77e10b0f404cf1f22",
    "test-bfs-directed/test-bfs-directed.e": "43327080e3b82f83319dcde548fcd74dd9556199bd8bb118b18d539e5a676b4b",
    "test-bfs-directed/test-bfs-directed.properties": "0eb7212411fa10aae0f16b81f1bcfe67b5465c666de0b470c457cc384d2ba79d",
    "test-bfs-directed/test-bfs-directed-BFS": "a75a576822a1a41687982a845905732e9bcad017161ebe1465ccca2ce9e36abb",
}


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Config(Record):
    model_config = ConfigDict(frozen=True, strict=True)
    repo: Path
    harness_repo: Path
    support: Path
    output: Path
    binary: Path
    graphframes_binary: Path
    fixtures_root: Path

    @model_validator(mode="after")
    def absolute_paths(self) -> Config:
        require(all(path.is_absolute() for path in (self.repo, self.harness_repo, self.support,
                    self.output, self.binary, self.graphframes_binary, self.fixtures_root)),
                "configured paths must be absolute")
        return self


class Identities(Record):
    fixtures: dict[str, FileIdentity]
    helpers: dict[str, FileIdentity]
    binary: FileIdentity
    graphframes_binary: FileIdentity
    pecan_commit: str
    harness_commit: str


class Process(Record):
    pid: int
    name: str
    state: str
    starttime: int


class Cgroup(Record):
    cpu_max: str
    memory_max: str
    memory_swap_max: str
    memory_events: dict[str, int]
    memory_peak_bytes: int


class PhysicalRow(Record):
    model_config = ConfigDict(strict=True)
    id: int
    value: int | float | None


class CleanupError(Record):
    operation: str
    error: str


class EngineSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    outcome: str
    finished_utc: str | None = None
    cleanup_errors: list[CleanupError] = Field(default_factory=list)
    staging_payload_after_shutdown: list[str] = Field(default_factory=list)
    incomplete_rounds: list[int] = Field(default_factory=list)


class EngineArguments(Record):
    repo: Path
    harness_repo: Path
    output: Path
    vertices: Path
    edges: Path
    binary: Path
    mode: Literal["local"] = "local"
    algorithm: Algorithm
    source: int
    partitions: Literal[16] = 16
    pool_bytes: Literal[32212254720] = 32212254720
    native_quota: Literal[268435456] = 268435456


class Control(Record):
    id: str
    engine: Engine
    algorithm: Algorithm
    fixture: str
    source: int
    outcome: Literal["running", "passed", "known_mismatch", "error", "timeout"] = "running"
    command: list[str] = Field(default_factory=list)
    pid: int | None = None
    returncode: int | None = None
    launch_to_exit_seconds: float | None = None
    timing_scope: str = "diagnostic child launch through completed wait; no performance comparison"
    input_files: dict[str, FileIdentity] = Field(default_factory=dict)
    result_files: dict[str, FileIdentity] = Field(default_factory=dict)
    physical_schemas: list[PhysicalSchema] = Field(default_factory=list)
    raw_rows: list[PhysicalRow] = Field(default_factory=list)
    expected_rows: list[PhysicalRow] = Field(default_factory=list)
    remaining_processes: list[Process] = Field(default_factory=list)
    remaining_after_cleanup: list[Process] = Field(default_factory=list)
    closure_observed: bool = False
    emergency_cleanup: list[str] = Field(default_factory=list)
    engine_receipt: EngineSummary | None = None
    engine_receipt_identity: FileIdentity | None = None
    cgroup_before: Cgroup | None = None
    cgroup_after: Cgroup | None = None
    witness_scope: str | None = None
    error: str | None = None


class ProceedScope(Record):
    dataset: Literal["cit-Patents"] = "cit-Patents"
    requires_zero_isolates: Literal[True] = True
    per_cell_full_oracle: Literal[True] = True
    generic_signed_wcc_qualified: Literal[False] = False


class Receipt(Record):
    config: Config
    started_utc: str
    finished_utc: str | None = None
    outcome: Literal["running", "passed", "passed_with_known_mismatch", "error"] = "running"
    before: Identities | None = None
    after: Identities | None = None
    controls: list[Control] = Field(default_factory=list)
    fixture_adapter: str = "WCC raw .properties incorrectly says edge-file=.v; use pinned actual .e without modifying originals"
    bfs_reference_adapter: str = "official 9223372036854775807 unreachable becomes reference -1; engine bytes remain unchanged"
    proceed_scope: ProceedScope = Field(default_factory=ProceedScope)
    generic_signed_id_qualification: Literal[False] = False
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TinyFixture:
    name: str
    ids: tuple[int, ...]
    edges: tuple[tuple[int, int], ...]
    expected: dict[int, int]
    source: int


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, value: BaseModel) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        stream.write(value.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def file_identity(path: Path) -> FileIdentity:
    require(path.is_file() and not path.is_symlink(), "missing/unsafe evidence file: " + str(path))
    return FileIdentity(bytes=path.stat().st_size, sha256=sha(path))


def source_guard(path: Path, expected: str) -> str:
    environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    head = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                   env=environment, text=True, timeout=30).strip()
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"],
                                    env=environment, text=True, timeout=30)
    detached = subprocess.run(["git", "-C", str(path), "symbolic-ref", "-q", "HEAD"],
                              stdout=subprocess.DEVNULL, env=environment, timeout=30, check=False).returncode
    require(head == expected and not dirty and detached == 1, "source must be clean and detached at " + expected)
    return head


def identities(config: Config) -> Identities:
    fixtures = {name: file_identity(config.fixtures_root / name) for name in PINS}
    require(all(fixtures[name].sha256 == expected for name, expected in PINS.items()), "tiny fixture pin mismatch")
    helpers = {path.name: file_identity(path) for path in sorted(config.support.glob("*.py"))}
    manifest = config.support / "support-manifest.json"
    if manifest.exists():
        helpers[manifest.name] = file_identity(manifest)
    binary, graphframes = file_identity(config.binary), file_identity(config.graphframes_binary)
    require(binary.sha256 == SAIL_SHA and graphframes.sha256 == GF_SHA, "engine binary pin mismatch")
    return Identities(fixtures=fixtures, helpers=helpers, binary=binary, graphframes_binary=graphframes,
                      pecan_commit=source_guard(config.repo, PECAN),
                      harness_commit=source_guard(config.harness_repo, HARNESS))


def integer_rows(path: Path, width: int) -> list[tuple[int, ...]]:
    result: list[tuple[int, ...]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = tuple(int(value) for value in line.split())
        require(len(row) == width and all(-(2**63) <= value < 2**63 for value in row),
                "unexpected fixture row width/signed64 domain")
        result.append(row)
    return result


def read_fixture(root: Path, name: str, algorithm: Literal["wcc", "bfs"]) -> TinyFixture:
    base = root / name / name
    ids = tuple(sorted(row[0] for row in integer_rows(base.with_suffix(".v"), 1)))
    edges = tuple((row[0], row[1]) for row in integer_rows(base.with_suffix(".e"), 2))
    require(len(ids) == len(set(ids)) and all(vertex > 0 for vertex in ids), "invalid fixture vertex domain")
    require(all(source in ids and target in ids for source, target in edges), "unknown fixture endpoint")
    rows = integer_rows(base.with_name(name + "-" + algorithm.upper()), 2)
    require(len(rows) == len(ids) and {row[0] for row in rows} == set(ids), "incomplete/duplicate fixture truth")
    properties: dict[str, str] = {}
    for line in base.with_suffix(".properties").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            properties[key.strip()] = value.strip()
    require(properties[f"graph.{name}.directed"] == "true", "fixture direction mismatch")
    source = int(properties[f"graph.{name}.bfs.source-vertex"]) if algorithm == "bfs" else ids[0]
    require(source in ids, "fixture source must exist")
    expected = {row[0]: row[1] for row in rows}
    if algorithm == "wcc":
        minima = {label: min(vertex for vertex in ids if expected[vertex] == label)
                  for label in set(expected.values())}
        expected = {vertex: minima[label] for vertex, label in expected.items()}
    else:
        expected = {vertex: -1 if value == 2**63 - 1 else value for vertex, value in expected.items()}
    return TinyFixture(name, ids, edges, expected, source)


def make_inputs(root: Path, fixture: TinyFixture) -> Path:
    destination = root / fixture.name
    destination.mkdir()
    pq.write_table(pa.table({"id": pa.array(fixture.ids, type=pa.int64())}), destination / "vertices.parquet")
    pq.write_table(pa.table({"source": pa.array([pair[0] for pair in fixture.edges], type=pa.int64()),
                             "target": pa.array([pair[1] for pair in fixture.edges], type=pa.int64())}),
                   destination / "edges.parquet")
    np.array(fixture.ids, dtype="<i8").tofile(destination / "ids.i64le")
    np.array([fixture.expected[vertex] for vertex in fixture.ids], dtype="<i8").tofile(destination / "values.i64le")
    np.array([(vertex, fixture.expected[vertex]) for vertex in fixture.ids], dtype="<i8").tofile(destination / "pairs.i64le")
    return destination


def processes() -> list[Process]:
    require(Path("/proc/self/stat").is_file(), "private Linux PID observer unavailable")
    result: list[Process] = []
    for path in Path("/proc").glob("[0-9]*"):
        try:
            if int(path.name) in (1, os.getpid()):
                continue
            raw = (path / "stat").read_text()
            tail = raw[raw.rfind(")") + 2:].split()
            if tail[0] not in ("Z", "X"):
                result.append(Process(pid=int(path.name), name=(path / "comm").read_text().strip(),
                                      state=tail[0], starttime=int(tail[19])))
        except FileNotFoundError:
            continue
    return result


def close_remaining(control: Control) -> None:
    observed = processes()
    if not control.closure_observed:
        control.remaining_processes = observed
        control.closure_observed = True
    else:
        control.remaining_processes.extend(row for row in observed if row not in control.remaining_processes)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for row in processes():
            try:
                actual = next((item for item in processes() if item.pid == row.pid), None)
                require(actual is not None and actual.starttime == row.starttime, "PID identity changed during cleanup")
                os.kill(row.pid, sig)
                control.emergency_cleanup.append(f"{sig.name} pid={row.pid} starttime={row.starttime}")
            except ProcessLookupError:
                continue
        deadline = time.monotonic() + 3
        while processes() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not processes():
            break
    control.remaining_after_cleanup = processes()


def cgroup() -> Cgroup:
    root = Path("/sys/fs/cgroup")
    result = Cgroup(cpu_max=(root / "cpu.max").read_text().strip(),
                    memory_max=(root / "memory.max").read_text().strip(),
                    memory_swap_max=(root / "memory.swap.max").read_text().strip(),
                    memory_events={key: int(value) for key, value in
                                   (line.split() for line in (root / "memory.events").read_text().splitlines())},
                    memory_peak_bytes=int((root / "memory.peak").read_text().strip()))
    require(result.cpu_max == "1600000 100000" and result.memory_max == str(32 * 2**30)
            and result.memory_swap_max == "0", "requires 16 CPU / 32 GiB / no swap")
    return result


def engine_command(config: Config, control: Control, inputs: Path, output: Path) -> list[str]:
    if control.engine == "graphframes":
        command = [str(config.graphframes_binary), "shortest-path" if control.algorithm == "bfs" else "wcc",
                   "--vertices", (inputs / "vertices.parquet").as_uri(), "--edges", (inputs / "edges.parquet").as_uri(),
                   "--output", (output / "result").as_uri(), "--src-col-name", "source", "--dst-col-name", "target",
                   "--max-memory", "30G", "--num-workers", "16", "--checkpoint-dir", str(output / "gf_workdir"),
                   "--max-temp-file", "200G"]
        return command + (["--landmarks", str(control.source)] if control.algorithm == "bfs" else ["--seed", "42"])
    arguments = EngineArguments(repo=config.repo, harness_repo=config.harness_repo, output=output,
        vertices=inputs / "vertices.parquet", edges=inputs / "edges.parquet", binary=config.binary,
        algorithm=control.algorithm, source=control.source)
    path = output / "engine-config.json"
    with path.open("x") as stream:
        stream.write(arguments.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return [sys.executable, "-B", str(config.support / "engine_pecan.py"), "--config", str(path)]


def physical_rows(directory: Path, expected_ids: tuple[int, ...], value_name: str,
                  value_type: pa.DataType, *, ordered: bool = True) -> tuple[list[PhysicalRow], list[PhysicalSchema]]:
    before = inventory(directory)
    rows: list[PhysicalRow] = []
    schemas: list[PhysicalSchema] = []
    for name in (name for name in before if name.endswith(".parquet")):
        with pq.ParquetFile(directory / name) as parquet:
            schema = parquet.schema_arrow
            valid_names = (schema.names == ["id", value_name] if ordered else
                           len(schema.names) == 2 and len(set(schema.names)) == 2
                           and set(schema.names) == {"id", value_name})
            require(valid_names and schema.field("id").type == pa.int64()
                    and schema.field(value_name).type == value_type, "unexpected physical control schema")
            schemas.append(PhysicalSchema(file=name, fields=[PhysicalField(name=field.name,
                           arrow_type=str(field.type), nullable=field.nullable) for field in schema]))
            table = parquet.read(use_threads=False)
            require(table.num_rows == parquet.metadata.num_rows and table.column("id").null_count == 0,
                    "physical/footer/null-id control violation")
            for vertex, value in zip(table.column("id").to_pylist(), table.column(value_name).to_pylist(), strict=True):
                if not isinstance(vertex, int):
                    raise TypeError("physical vertex is not a signed64 integer")
                rows.append(PhysicalRow(id=vertex, value=value))
    require(before == inventory(directory), "physical control bytes changed during read")
    return sorted(rows, key=lambda row: row.id), schemas


def check_output(control: Control, fixture: TinyFixture, inputs: Path, output: Path) -> None:
    directory = output / "result"
    control.expected_rows = [PhysicalRow(id=vertex, value=fixture.expected[vertex]) for vertex in fixture.ids]
    value_name, value_type = ((f"dist_{fixture.source}", pa.int32()) if control.engine == "graphframes"
                              else ("distance", pa.float64())) if control.algorithm == "bfs" else ("component", pa.int64())
    control.raw_rows, control.physical_schemas = physical_rows(directory, fixture.ids, value_name, value_type,
                                                              ordered=control.algorithm != "bfs")
    control.result_files = inventory(directory)
    require(len(control.raw_rows) == len(fixture.ids)
            and {row.id for row in control.raw_rows} == set(fixture.ids),
            "incomplete/duplicate physical control vertex domain")
    if control.fixture == "signed-isolate":
        actual = {row.id: row.value for row in control.raw_rows}
        control.witness_scope = "seed42 namespace collision; no generic signed-ID qualification"
        if actual == {1: ISOLATE, 2: ISOLATE, ISOLATE: ISOLATE}:
            control.outcome = "known_mismatch"
        else:
            require(actual == fixture.expected, "unexpected signed-isolate mismatch")
            control.outcome = "passed"
    elif control.algorithm == "bfs":
        reference = load_bfs_reference(inputs / "ids.i64le", sha(inputs / "ids.i64le"),
            inputs / "values.i64le", sha(inputs / "values.i64le"), len(fixture.ids), max(fixture.ids), fixture.source)
        verdict = verify_bfs_output(directory, reference, control.engine)
        control.physical_schemas = verdict.physical_schemas
        control.outcome = "passed"
    else:
        wcc_reference = load_wcc_reference(inputs / "pairs.i64le", sha(inputs / "pairs.i64le"),
                                            len(fixture.ids), max(fixture.ids))
        verdict_wcc = verify_wcc_output(directory, wcc_reference)
        control.physical_schemas = verdict_wcc.physical_schemas
        control.outcome = "passed"


def execute_control(config: Config, control: Control, fixture: TinyFixture, inputs: Path) -> None:
    output = config.output / "controls" / control.id
    output.mkdir(parents=True)
    path = output / "control-receipt.json"
    save(path, control)
    process: subprocess.Popen[bytes] | None = None
    try:
        require(not processes(), "private container contains another live process")
        control.cgroup_before = cgroup()
        control.input_files = inventory(inputs)
        control.command = engine_command(config, control, inputs, output)
        save(path, control)
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("DATAFUSION_", "GRAPHFRAMES_"))}
        environment.update(RUST_LOG="warn", TOKIO_WORKER_THREADS="16", RAYON_NUM_THREADS="16",
            OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
        environment["PYTHONPATH"] = os.pathsep.join([
            str(config.repo / "examples/extensions/graph-algorithms/src"),
            str(config.harness_repo / "examples/extensions/benchmarks"), str(config.support),
            environment.get("PYTHONPATH", "")])
        with (output / "engine.log").open("xb") as log:
            started = time.perf_counter()
            try:
                process = subprocess.Popen(control.command, cwd=output, env=environment, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                control.pid = process.pid
                control.returncode = process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                control.outcome = "timeout"
                raise
            finally:
                if process is not None and process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                    control.returncode = process.returncode
                control.launch_to_exit_seconds = time.perf_counter() - started
        close_remaining(control)
        control.cgroup_after = cgroup()
        require(control.cgroup_after.memory_events.get("oom", -1) == control.cgroup_before.memory_events.get("oom", -2)
                and control.cgroup_after.memory_events.get("oom_kill", -1) == control.cgroup_before.memory_events.get("oom_kill", -2),
                "engine cgroup OOM event")
        if control.engine == "pecan":
            engine_path = output / "engine-receipt.json"
            control.engine_receipt = EngineSummary.model_validate_json(engine_path.read_bytes())
            control.engine_receipt_identity = file_identity(engine_path)
            require(control.engine_receipt.outcome == "passed" and control.engine_receipt.finished_utc is not None
                    and not control.engine_receipt.cleanup_errors and not control.engine_receipt.staging_payload_after_shutdown
                    and not control.engine_receipt.incomplete_rounds, "Pecan engine receipt failed")
        require(control.returncode == 0 and not control.remaining_processes
                and not control.remaining_after_cleanup, "engine exit/cleanup failed")
        check_output(control, fixture, inputs, output)
        require(control.input_files == inventory(inputs), "prepared tiny inputs changed during engine control")
    except BaseException:
        LOGGER.exception("Compatibility control failed: %s", control.id)
        if control.outcome != "timeout":
            control.outcome = "error"
        control.error = traceback.format_exc()
    finally:
        if process is not None:
            close_remaining(control)
        else:
            control.remaining_after_cleanup = processes()
        if control.remaining_after_cleanup or control.remaining_processes:
            control.outcome = "error"
        save(path, control)


def execute(config: Config, receipt: Receipt) -> None:
    receipt.before = identities(config)
    require(not processes(), "private compatibility container has another process")
    cgroup()
    root = config.output / "inputs"
    root.mkdir()
    wcc = read_fixture(config.fixtures_root, "test-wcc-directed", "wcc")
    bfs = read_fixture(config.fixtures_root, "test-bfs-directed", "bfs")
    signed = TinyFixture("signed-isolate", tuple(sorted((1, 2, ISOLATE))), ((1, 2),),
                          {1: 1, 2: 1, ISOLATE: ISOLATE}, 1)
    fixtures = {fixture.name: fixture for fixture in (wcc, bfs, signed)}
    paths = {fixture.name: make_inputs(root, fixture) for fixture in fixtures.values()}
    controls = [
        Control(id="wcc-graphframes", engine="graphframes", algorithm="wcc-randomized", fixture=wcc.name, source=wcc.source),
        Control(id="wcc-pecan-randomized", engine="pecan", algorithm="wcc-randomized", fixture=wcc.name, source=wcc.source),
        Control(id="wcc-pecan-min-label", engine="pecan", algorithm="wcc-min-label", fixture=wcc.name, source=wcc.source),
        Control(id="bfs-graphframes", engine="graphframes", algorithm="bfs", fixture=bfs.name, source=bfs.source),
        Control(id="bfs-pecan", engine="pecan", algorithm="bfs", fixture=bfs.name, source=bfs.source),
        Control(id="b9-signed-isolate", engine="pecan", algorithm="wcc-randomized", fixture=signed.name, source=1),
    ]
    for control in controls:
        receipt.controls.append(control)
        save(config.output / "receipt.json", receipt)
        execute_control(config, control, fixtures[control.fixture], paths[control.fixture])
        save(config.output / "receipt.json", receipt)
        require(control.outcome in ("passed", "known_mismatch"), "compatibility control did not pass: " + control.id)
    require(all(control.outcome == "passed" for control in receipt.controls[:-1]), "ordinary controls must all pass")
    receipt.after = identities(config)
    require(receipt.before == receipt.after and not processes(), "final compatibility identity/closure failure")
    receipt.outcome = "passed_with_known_mismatch" if receipt.controls[-1].outcome == "known_mismatch" else "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    config = Config.model_validate_json(parser.parse_args().config.read_bytes())
    config.output.mkdir(parents=True, exist_ok=False)
    receipt = Receipt(config=config, started_utc=utc())
    save(config.output / "receipt.json", receipt)
    try:
        execute(config, receipt)
    except BaseException:
        LOGGER.exception("Compatibility phase failed")
        receipt.outcome, receipt.error = "error", traceback.format_exc()
    finally:
        if receipt.before is not None and receipt.after is None:
            try:
                receipt.after = identities(config)
                require(receipt.before == receipt.after, "compatibility fixture/source/helper bytes changed during failure")
            except BaseException:
                LOGGER.exception("Final compatibility identity observation failed")
                receipt.outcome = "error"
                receipt.error = (receipt.error or "") + "\nFinal identity observation:\n" + traceback.format_exc()
        receipt.finished_utc = utc()
        save(config.output / "receipt.json", receipt)
    print(json.dumps({"outcome": receipt.outcome, "receipt": str(config.output / "receipt.json")}), flush=True)
    return 0 if receipt.outcome in ("passed", "passed_with_known_mismatch") else 1


if __name__ == "__main__":
    raise SystemExit(main())
