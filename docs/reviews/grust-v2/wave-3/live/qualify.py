"""Execute generated plans and their costed alternatives on native Sail/Parquet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from controls import Control, memory_probe, run_controls
from iterative import Execution, Program, Traversal
from oracle import SPECS
from oracle import rows as oracle_rows
from pyspark.sql.connect.session import SparkSession
from pyspark.sql.types import Row


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    sql: str
    optimized_sql: str
    expected: list[list[Any]]
    ordered: bool
    trace: list[str]
    output_types: list[str]
    traversals: tuple[Traversal, ...]
    optimized_traversals: tuple[Traversal, ...]


@dataclass(frozen=True, slots=True)
class Result:
    name: str
    variant: str
    outcome: str
    expected: list[list[Any]]
    actual: list[list[Any]] | None
    error: str | None


TABLES: dict[str, str] = {
    "chain_nodes": "SELECT CAST(id AS BIGINT) id FROM VALUES (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12) AS t(id)",
    "chain_edges": "SELECT CAST(id AS BIGINT) id, CAST(src AS BIGINT) src, CAST(dst AS BIGINT) dst FROM VALUES (301,1,2),(302,2,3),(303,3,4),(304,4,5),(305,5,6),(306,6,7),(307,7,8),(308,8,9),(309,9,10),(310,10,11),(311,11,12) AS t(id,src,dst)",
    "people": "SELECT CAST(id AS BIGINT) id, name, CAST(age AS BIGINT) age FROM VALUES (1,'Alice',30),(2,'Bob',20),(3,'Cara',NULL),(4,'Dave',40) AS t(id,name,age)",
    "employees": "SELECT CAST(id AS BIGINT) id, name, CAST(age AS BIGINT) age, CAST(salary AS BIGINT) salary FROM VALUES (5,'Eve',35,100) AS t(id,name,age,salary)",
    "companies": "SELECT CAST(id AS BIGINT) id, name FROM VALUES (7,'Acme') AS t(id,name)",
    "knows": "SELECT CAST(id AS BIGINT) id, CAST(src AS BIGINT) src, CAST(dst AS BIGINT) dst FROM VALUES (100,1,2),(101,1,2),(102,2,3),(103,3,3),(104,3,1) AS t(id,src,dst)",
    "works": "SELECT CAST(id AS BIGINT) id, CAST(src AS BIGINT) src, CAST(dst AS BIGINT) dst FROM VALUES (200,1,7),(201,2,7) AS t(id,src,dst)",
}


def normalize(value: Any) -> Any:
    if isinstance(value, Row):
        return value.asDict(recursive=True)
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def equal(actual: list[list[Any]], expected: list[list[Any]], ordered: bool) -> bool:
    if ordered:
        return actual == expected
    # Sorting serialized rows preserves bag multiplicity and handles mixed null types.
    return sorted(
        json.dumps(r, ensure_ascii=False, sort_keys=True) for r in actual
    ) == sorted(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in expected)


def run(sail: Path, manifest: Path, output: Path, probe: bool = False) -> int:
    output.mkdir(parents=True, exist_ok=True)
    raw: list[dict[str, Any]] = json.loads(manifest.read_text())
    if probe and raw:
        raise ValueError("memory probe requires an empty query manifest")
    for record in raw:
        if record["name"] in SPECS:
            expected = oracle_rows(SPECS[record["name"]])
            if not equal(record["expected"], expected, False):
                raise RuntimeError(
                    f"fixture disagrees with independent DFS: {record['name']}"
                )
    cases = [
        Case(
            name=c["name"],
            sql=c["sql"],
            optimized_sql=c["optimized_sql"],
            expected=c["expected"],
            ordered=c["ordered"],
            trace=c["trace"],
            output_types=c["output_types"],
            traversals=tuple(Traversal(**step) for step in c.get("traversals", [])),
            optimized_traversals=tuple(
                Traversal(**step) for step in c.get("optimized_traversals", [])
            ),
        )
        for c in raw
    ]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = dict(
        os.environ,
        SAIL_MODE="local",
        SAIL_EXECUTION__DEFAULT_PARALLELISM="2",
        TOKIO_WORKER_THREADS="2",
        RUST_LOG="warn",
        SAIL_RUNTIME__MEMORY_POOL__TYPE="fair",
        SAIL_RUNTIME__MEMORY_POOL__FAIR__MAX_SIZE=str(1 if probe else 256 << 20),
    )
    results: list[Result] = []
    controls: list[Control] = []
    spark: SparkSession | None = None
    observed = datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha256(sail.read_bytes()).hexdigest()
    command = [str(sail), "spark", "server", "--ip", "127.0.0.1", "--port", str(port)]
    with (output / "server.log").open("w") as log:
        server = subprocess.Popen(command, env=environment, stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 30
        while True:
            with socket.socket() as connection:
                if connection.connect_ex(("127.0.0.1", port)) == 0:
                    break
            if server.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Sail did not start; see server.log")
            time.sleep(0.05)
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
        if probe:
            controls = [memory_probe(spark)]
            print(f"control managed_memory_pool {controls[0].outcome}", flush=True)
        for name, query in [] if probe else TABLES.items():
            parquet = output / "inputs" / name
            spark.sql(query).write.mode("overwrite").parquet(parquet.as_uri())
            spark.read.parquet(parquet.as_uri()).createOrReplaceTempView(name)
        for case in cases:
            for variant, query in [
                ("resolved", case.sql),
                ("optimized", case.optimized_sql),
            ]:
                actual: list[list[Any]] | None = None
                error: str | None = None
                try:
                    steps = (
                        case.traversals
                        if variant == "resolved"
                        else case.optimized_traversals
                    )
                    with Execution(spark, output / "scratch") as execution:
                        frame = execution.run(Program(query, steps))
                        types = [
                            field.dataType.simpleString()
                            for field in frame.schema.fields
                        ]
                        if types != case.output_types:
                            raise RuntimeError(
                                f"output type mismatch: {types} != {case.output_types}"
                            )
                        actual = [
                            [normalize(value) for value in row]
                            for row in frame.collect()
                        ]
                    outcome = (
                        "passed"
                        if equal(actual, case.expected, case.ordered)
                        else "mismatch"
                    )
                except Exception as exc:  # noqa: BLE001 — preserve errors from every engine cell.
                    outcome = "error"
                    error = str(exc)
                results.append(
                    Result(case.name, variant, outcome, case.expected, actual, error)
                )
                print(f"{case.name} {variant} {outcome}", flush=True)
        iterative_cases = [case for case in cases if case.traversals]
        if iterative_cases:
            first = iterative_cases[0]
            controls = run_controls(
                spark, output / "controls", Program(first.sql, first.traversals)
            )
            for control in controls:
                print(f"control {control.name} {control.outcome}", flush=True)
    finally:
        shutdown_error: str | None = None
        try:
            if spark is not None:
                spark.stop()
        except Exception as exc:  # noqa: BLE001 — still close the owned native server.
            shutdown_error = str(exc)
        finally:
            server.terminate()
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        receipt = {
            "observed_utc": observed,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "sail_binary": str(sail),
            "sail_sha256": digest,
            "command": command,
            "settings": {
                k: environment[k]
                for k in (
                    "SAIL_MODE",
                    "SAIL_EXECUTION__DEFAULT_PARALLELISM",
                    "TOKIO_WORKER_THREADS",
                    "SAIL_RUNTIME__MEMORY_POOL__TYPE",
                    "SAIL_RUNTIME__MEMORY_POOL__FAIR__MAX_SIZE",
                )
            },
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "cases": len(cases),
            "controls": [asdict(control) for control in controls],
            "results": [asdict(result) for result in results],
            "rewrites": {c.name: c.trace for c in cases},
            "server_exit_code": server.returncode,
            "shutdown_error": shutdown_error,
            "sail_sha256_after": hashlib.sha256(sail.read_bytes()).hexdigest(),
        }
        (output / "receipt.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
        )
    return (
        0
        if len(results) == 2 * len(cases)
        and all(r.outcome == "passed" for r in results)
        and all(c.outcome == "passed" for c in controls)
        and shutdown_error is None
        and receipt["sail_sha256_after"] == digest
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sail", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--memory-probe", action="store_true")
    args = parser.parse_args()
    return run(
        args.sail.resolve(),
        args.manifest.resolve(),
        args.output.resolve(),
        args.memory_probe,
    )


if __name__ == "__main__":
    raise SystemExit(main())
