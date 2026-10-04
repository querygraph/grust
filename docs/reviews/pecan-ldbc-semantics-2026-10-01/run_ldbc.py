"""Official tiny LDBC correctness checks; no performance comparisons."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import traceback
from types import ModuleType
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pyspark.sql.connect.dataframe import DataFrame
    from pyspark.sql.connect.session import SparkSession
    from pyspark_pecan import GraphAlgorithms
    from pyspark_pecan.lifecycle import GraphResult

CONTROLLER = "6ae2e43a903c2cee02da170465c922c72b76198e"
RUNTIME = "56194b170155301ba91077f0ba3df31fe2c78b6b"
BINARY = Path("/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release")
BINARY_SHA = "5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec"
NATIVE_SHA = "eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50"
UNREACHABLE_BFS = (1 << 63) - 1
Algorithm = Literal["bfs", "pr", "wcc", "sssp"]
Number = int | float
CORRECTIONS = {"test-wcc-directed", "test-sssp-undirected"}


class Options(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    repo: Path
    inputs: Path
    output: Path
    deadline: int = Field(default=600, ge=300, le=600)


class Member(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    archive_member: str
    sha256: str
    bytes: int


class Archive(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    name: str
    url: str
    archive_sha256: str
    archive_bytes: int
    members: dict[str, Member]


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    schema_version: Literal[1]
    entries: list[Archive]
    explicit_property_corrections: dict[str, object]
    unsupported_algorithms: list[str]


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    algorithm: Algorithm


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: str
    outcome: Literal["running", "passed", "mismatch", "error", "not_run"] = "running"
    evidence: dict[str, object] = Field(default_factory=dict)


class DeadlineExceeded(BaseException):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def deadline(_signum: int, _frame: object) -> None:
    raise DeadlineExceeded("correctness suite exceeded its global deadline")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("+Infinity" if value > 0 else "-Infinity")
    if isinstance(value, Mapping):
        return {str(key): portable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [portable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def save(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(portable(value), stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def guard(options: Options, runtime: ModuleType) -> dict[str, object]:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(options.repo), *args], env=env, text=True).strip()
    require(git("rev-parse", "HEAD") == CONTROLLER and not git("status", "--porcelain"), "source pin/cleanliness")
    import pyspark_pecan
    package = options.repo / "examples/extensions/graph-algorithms/src/pyspark_pecan"
    require(Path(pyspark_pecan.__file__).resolve() == package / "__init__.py", "Pecan import origin")
    for name, module in sys.modules.copy().items():
        if name.startswith("pyspark_pecan.") and module is not None:
            require(Path(module.__file__ or "").resolve().is_relative_to(package), "submodule origin " + name)
    require(Path(runtime.__file__ or "").resolve() == options.repo / "examples/extensions/benchmarks/runtime.py", "runtime helper origin")
    require(sha(BINARY) == BINARY_SHA, "runtime binary SHA")
    packages = {name: version(name) for name in ("pyspark", "pydantic", "pydantic_core")}
    require(packages == {"pyspark": "4.0.1", "pydantic": "2.11.10", "pydantic_core": "2.33.2"}, "package versions")
    native = runtime.native_package_identity()
    require(NATIVE_SHA in [value for key, value in native["files_sha256"].items() if key.endswith(".so")], "native binary SHA")
    return {"controller": CONTROLLER, "runtime_source": RUNTIME, "binary_sha256": sha(BINARY),
            "packages": packages, "native": native, "runtime_helper_sha256": sha(Path(runtime.__file__ or "")),
            "package_files": {str(path.relative_to(package)): sha(path) for path in sorted(package.rglob("*.py"))}}


def properties(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            require(key.strip() not in result, "duplicate property")
            result[key.strip()] = value.strip()
    return result


def reference(path: Path, algorithm: Algorithm) -> dict[int, Number]:
    result: dict[int, Number] = {}
    for line in path.read_text().splitlines():
        vertex, text = line.split()
        identifier = int(vertex)
        require(identifier not in result, "duplicate reference vertex")
        result[identifier] = int(text) if algorithm in ("bfs", "wcc") else float(text)
    return result


def compare(algorithm: Algorithm, expected: dict[int, Number], rows: list[dict[str, object]]) -> dict[str, object]:
    column = {"pr": "pagerank", "wcc": "component", "bfs": "distance", "sssp": "distance"}[algorithm]
    actual: dict[int, object] = {}
    errors: list[str] = []
    for row in rows:
        identifier = row.get("id")
        if type(identifier) is not int or identifier in actual:
            errors.append("null/non-BIGINT/duplicate vertex")
            continue
        actual[cast(int, identifier)] = row.get(column)
    if set(actual) != set(expected) or len(rows) != len(expected):
        errors.append("vertex coverage/cardinality")
    mismatches: list[dict[str, object]] = []
    for identifier in sorted(set(actual) & set(expected)):
        value, target = actual[identifier], expected[identifier]
        if algorithm == "wcc":
            valid = type(value) is int
        elif algorithm == "bfs":
            valid = (value is None and target == UNREACHABLE_BFS) or (
                type(value) in (int, float) and math.isfinite(cast(Number, value)) and value == target)
        else:
            normalized = math.inf if algorithm == "sssp" and value is None else value
            valid = type(normalized) in (int, float) and not math.isnan(cast(Number, normalized))
            if valid:
                number = cast(Number, normalized)
                valid = number == math.inf if target == math.inf else (
                    math.isfinite(number) and abs(number - target) <= 0.0001 * abs(target))
            if algorithm == "pr" and target == math.inf:
                valid = False
        if not valid:
            mismatches.append({"id": identifier, "expected": target, "actual": value})
    canonical = True
    if algorithm == "wcc" and not errors and not mismatches:
        forward: dict[Number, object] = {}
        backward: dict[object, Number] = {}
        for identifier, label in expected.items():
            value = actual[identifier]
            if (label in forward and forward[label] != value) or (value in backward and backward[value] != label):
                mismatches.append({"id": identifier, "expected": label, "actual": value})
            forward[label], backward[value] = value, label
        canonical = all(actual[identifier] == label for identifier, label in expected.items())
    return {"official_pass": not errors and not mismatches, "coverage_errors": errors,
            "mismatch_count": len(mismatches), "mismatches": mismatches,
            "canonical_min_label_pass": canonical if algorithm == "wcc" else None}


def self_controls() -> list[str]:
    checks: list[tuple[str, Algorithm, dict[int, Number], list[dict[str, object]], bool]] = [
        ("valid-pr", "pr", {1: 0.5}, [{"id": 1, "pagerank": 0.5}], True),
        ("missing", "pr", {1: 0.5}, [], False),
        ("duplicate", "pr", {1: 0.5}, [{"id": 1, "pagerank": 0.5}] * 2, False),
        ("wrong-pr", "pr", {1: 0.5}, [{"id": 1, "pagerank": 0.51}], False),
        ("relative-pr", "pr", {1: 1e-6}, [{"id": 1, "pagerank": 1.01e-6}], False),
        ("zero-sssp", "sssp", {1: 0.0}, [{"id": 1, "distance": 1e-12}], False),
        ("finite-for-inf", "sssp", {1: math.inf}, [{"id": 1, "distance": 2.0}], False),
        ("inf-for-finite", "sssp", {1: 2.0}, [{"id": 1, "distance": math.inf}], False),
        ("null-for-inf", "sssp", {1: math.inf}, [{"id": 1, "distance": None}], True),
        ("wcc-merge", "wcc", {1: 1, 2: 2}, [{"id": 1, "component": 1}, {"id": 2, "component": 1}], False),
        ("wcc-split", "wcc", {1: 1, 2: 1}, [{"id": 1, "component": 1}, {"id": 2, "component": 2}], False),
        ("wcc-equivalence", "wcc", {1: 1, 2: 1}, [{"id": 1, "component": 7}, {"id": 2, "component": 7}], True),
    ]
    for name, algorithm, expected, rows, verdict in checks:
        require(compare(algorithm, expected, rows)["official_pass"] is verdict, "oracle self-control " + name)
    return [name for name, *_ in checks]


def frames(spark: SparkSession, folder: Path, case: Case, directed: bool) -> tuple[DataFrame, DataFrame]:
    identifiers = [int(line) for line in (folder / (case.name + ".v")).read_text().splitlines()]
    edges: list[tuple[int, int, float]] = []
    for line in (folder / (case.name + ".e")).read_text().splitlines():
        values = line.split()
        edges.append((int(values[0]), int(values[1]), float(values[2]) if len(values) == 3 else 1.0))
    if case.algorithm == "pr" and not directed:
        edges += [(target, source, weight) for source, target, weight in edges]
    vertices = spark.sql("SELECT CAST(id AS BIGINT) id FROM VALUES " + ",".join(f"({identifier})" for identifier in identifiers) + " AS v(id)")
    literals = ",".join(f"({source},{target},CAST('{weight!r}' AS DOUBLE))" for source, target, weight in edges)
    adjacency = spark.sql("SELECT CAST(src AS BIGINT) src, CAST(dst AS BIGINT) dst, weight FROM VALUES " + literals + " AS e(src,dst,weight)")
    return vertices, adjacency


def execute(graph: GraphAlgorithms, vertices: DataFrame, edges: DataFrame, case: Case, props: dict[str, str]) -> GraphResult:
    prefix = "graph." + case.name + "."
    directed = props[prefix + "directed"] == "true"
    if case.algorithm == "pr":
        return graph.pagerank(vertices, edges, method="power", tolerance=None, partitions=2,
                              reset_probability=1.0 - float(props[prefix + "pr.damping-factor"]),
                              max_iterations=int(props[prefix + "pr.num-iterations"]))
    if case.algorithm == "wcc":
        return graph.wcc(vertices, edges, method="randomized_fused", seed=42, max_iterations=64, partitions=2)
    source = int(props[prefix + case.algorithm + ".source-vertex"])
    if case.algorithm == "bfs":
        return graph.bfs(vertices, edges, source=source, directed=directed, method="frontier", max_iterations=64, partitions=2)
    return graph.sssp(vertices, edges, source=source, directed=directed, method="delta_star", delta=1.0, max_iterations=64, partitions=2)


def check_metadata(result: GraphResult, case: Case, props: dict[str, str]) -> dict[str, object]:
    metadata = {name: getattr(result, name) for name in ("algorithm", "iterations", "converged", "method", "seed", "residual", "error_bound")}
    names = {"pr": "pagerank", "wcc": "wcc-randomized-fused-contraction", "bfs": "bfs-frontier", "sssp": "sssp-delta-star"}
    require(result.algorithm == names[case.algorithm], "algorithm metadata")
    require(type(result.iterations) is int and 0 <= result.iterations <= 64, "iteration metadata")
    if case.algorithm == "pr":
        require(result.iterations == int(props["graph." + case.name + ".pr.num-iterations"]) and result.converged is None, "fixed-step PR metadata")
    else:
        require(result.converged is True, "convergence metadata")
    if case.algorithm == "wcc":
        require(result.method == "randomized_fused" and result.seed == 42, "WCC method/seed metadata")
    return metadata


def run_case(spark: SparkSession, graph: GraphAlgorithms, options: Options, case: Case) -> Receipt:
    directory = options.output / (case.name + "--" + case.algorithm)
    directory.mkdir()
    receipt = Receipt(case=directory.name)
    save(directory / "receipt.json", receipt.model_dump())
    try:
        folder = options.inputs / case.name
        props = properties(folder / (case.name + ".properties"))
        shutil.copyfile(folder / (case.name + ".properties"), directory / "raw.properties")
        consumed = [case.name + suffix for suffix in (".v", ".e", ".properties", "-" + case.algorithm.upper())]
        receipt.evidence["member_sha256"] = {name: sha(folder / name) for name in consumed}
        prefix = "graph." + case.name + "."
        edge_property = props[prefix + "edge-file"]
        expected_property = case.name + (".v" if case.name in CORRECTIONS else ".e")
        require(edge_property == expected_property and props[prefix + "vertex-file"] == case.name + ".v", "input filename property")
        receipt.evidence.update(properties=props, resolved_edge_file=case.name + ".e", correction_applied=case.name in CORRECTIONS)
        expected = reference(folder / (case.name + "-" + case.algorithm.upper()), case.algorithm)
        vertices, edges = frames(spark, folder, case, props[prefix + "directed"] == "true")
        save(directory / "reference.json", expected)
        with execute(graph, vertices, edges, case, props) as result:
            schema = [(field.name, field.dataType.simpleString()) for field in result.frame.schema]
            receipt.evidence.update(schema=schema, metadata={name: getattr(result, name) for name in ("algorithm", "iterations", "converged", "method", "seed")})
            save(directory / "receipt.json", receipt.model_dump())
            rows = [cast(dict[str, object], row.asDict()) for row in result.frame.collect()]
            save(directory / "raw-rows.json", rows)
            expected_schema = [("id", "bigint"), ("component", "bigint")] if case.algorithm == "wcc" else (
                [("id", "bigint"), ("pagerank", "double")] if case.algorithm == "pr" else
                [("id", "bigint"), ("distance", "double"), ("hops", "bigint"), ("parent", "bigint")])
            require(schema == expected_schema, "exact output schema")
            receipt.evidence["metadata"] = check_metadata(result, case, props)
            verdict = compare(case.algorithm, expected, rows)
            receipt.evidence["oracle"] = verdict
            save(directory / "oracle.json", verdict)
            receipt.outcome = "passed" if verdict["official_pass"] and verdict["canonical_min_label_pass"] is not False else "mismatch"
    except Exception:
        receipt.outcome = "error"
        receipt.evidence["error"] = traceback.format_exc()
    except BaseException:
        receipt.outcome = "error"
        receipt.evidence["error"] = traceback.format_exc()
        raise
    finally:
        remaining = [str(path.relative_to(options.output / "staging")) for path in (options.output / "staging").rglob("*")]
        receipt.evidence["staging_remaining"] = remaining
        if remaining:
            receipt.outcome = "error"
        save(directory / "receipt.json", receipt.model_dump())
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "inputs", "output"):
        parser.add_argument("--" + name, required=True, type=lambda text: Path(text).resolve())
    parser.add_argument("--deadline", type=int, default=600)
    options = Options.model_validate(vars(parser.parse_args()))
    options.output.mkdir(parents=True, exist_ok=False)
    sys.dont_write_bytecode = True
    for relative in ("examples/extensions/benchmarks", "examples/extensions/graph-algorithms/src"):
        sys.path.insert(0, str(options.repo / relative))
    summary: dict[str, object] = {"outcome": "error", "started_utc": datetime.now(timezone.utc).isoformat(),
                                 "options": options.model_dump(), "purpose": "correctness only", "cells": []}
    cleanup: list[dict[str, str]] = []
    cells: list[dict[str, object]] = []
    cases = [Case(f"test-{algorithm}-{direction}", cast(Algorithm, algorithm)) for algorithm in ("bfs", "pr", "wcc", "sssp") for direction in ("directed", "undirected")]
    cases += [Case("example-" + direction, cast(Algorithm, algorithm)) for direction in ("directed", "undirected") for algorithm in ("bfs", "pr", "wcc", "sssp")]
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(options.deadline)
    try:
        import runtime
        from pyspark.sql.connect.client.retries import DefaultPolicy
        from pyspark.sql.connect.session import SparkSession
        from pyspark_pecan import GraphAlgorithms
        summary["identities_before"] = guard(options, runtime)
        summary["oracle_self_controls"] = self_controls()
        manifest_path = options.inputs / "manifest.json"
        manifest = Manifest.model_validate_json(manifest_path.read_text())
        shutil.copyfile(manifest_path, options.output / "input-manifest.json")
        summary["input_manifest_sha256"] = sha(manifest_path)
        require(len(manifest.entries) == 14 and {entry.name for entry in manifest.entries} == {f"test-{a}-{d}" for a in ("bfs", "pr", "wcc", "sssp", "cdlp", "lcc") for d in ("directed", "undirected")} | {"example-directed", "example-undirected"}, "complete 14-archive inventory")
        require(set(manifest.unsupported_algorithms) == {"cdlp", "lcc"}, "unsupported inventory")
        members: dict[str, object] = {}
        for entry in manifest.entries:
            for name, member in entry.members.items():
                require(Path(name).name == name, "member basename")
                path = options.inputs / entry.name / name
                require(path.stat().st_size == member.bytes and sha(path) == member.sha256, "member bytes/hash " + str(path))
                members[entry.name + "/" + name] = member.model_dump()
        summary["verified_members"] = members
        summary["unsupported"] = [{"graph": f"test-{a}-{d}", "algorithm": a, "outcome": "unsupported"} for a in ("cdlp", "lcc") for d in ("directed", "undirected")]
        save(options.output / "receipt.json", summary)
        os.environ["SAIL_BENCHMARK_RUST_LOG"] = "warn"
        with runtime.server(BINARY, options.output, "local", 2, 2, 128 * 2**20, cleanup, worker_task_slots=2, sail_pool_bytes=2**30) as (endpoint, pid):
            summary["server_pid"] = pid
            spark = SparkSession.builder.remote(endpoint).create()
            spark.client.set_retry_policies([DefaultPolicy(max_retries=1, initial_backoff=100, max_backoff=100, jitter=0)])
            try:
                graph = GraphAlgorithms(spark)
                for case in cases:
                    require(spark.sql("SELECT CAST(1 AS BIGINT) AS healthy").collect()[0][0] == 1, "server health")
                    result = run_case(spark, graph, options, case)
                    cells.append(result.model_dump())
                    summary["cells"] = cells
                    save(options.output / "receipt.json", summary)
                    require(not result.evidence["staging_remaining"], "uncertain staging cleanup; stop advancement")
            finally:
                spark.stop()
        summary["identities_after"] = guard(options, runtime)
        require(summary["identities_before"] == summary["identities_after"], "source/runtime/package identity changed")
        require(sha(manifest_path) == summary["input_manifest_sha256"], "input manifest changed")
        for entry in manifest.entries:
            for name, member in entry.members.items():
                require(sha(options.inputs / entry.name / name) == member.sha256, "input member changed " + name)
        require(not cleanup and not list((options.output / "staging").rglob("*")), "final cleanup")
        summary["outcome"] = "passed" if len(cells) == 16 and all(cell["outcome"] == "passed" for cell in cells) else "failed"
    except BaseException:
        summary["error"] = traceback.format_exc()
    finally:
        signal.alarm(0)
        completed = {str(cell["case"]) for cell in cells}
        for case in cases:
            name = case.name + "--" + case.algorithm
            path = options.output / name / "receipt.json"
            if name not in completed and path.is_file():
                cells.append(Receipt.model_validate_json(path.read_text()).model_dump())
                completed.add(name)
        summary["cells"] = cells
        summary["not_run"] = [case.name + "--" + case.algorithm for case in cases if case.name + "--" + case.algorithm not in completed]
        summary["cleanup_errors"] = cleanup
        summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save(options.output / "receipt.json", summary)
    print(json.dumps({"outcome": summary["outcome"], "completed_cells": len(cells), "receipt": str(options.output / "receipt.json")}))
    return 0 if summary["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
