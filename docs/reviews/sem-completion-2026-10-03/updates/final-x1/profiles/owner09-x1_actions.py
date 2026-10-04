"""Current stock Argentea reference BFS: full native13 export or retained error."""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from argentea_bfs_client import ArgenteaBfs
from grpc import RpcError, StatusCode
from pydantic import JsonValue
from pyspark.sql.connect import functions as sf
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession
from pyspark.sql.types import LongType

import x1_io as io
import x1_models as m

MAXIMUM_ERROR_CHAIN = 8
MAXIMUM_ERROR_TEXT = 4096

NATIVE_COLUMNS = [
    "id",
    "distance",
    "hops",
    "parent",
    "owner",
    "worker_id",
    "pid",
    "adjacency_id",
    "incoming_adjacency_id",
    "phase",
    "levels",
    "reached",
    "converged",
]


def exception_chain(error: BaseException) -> dict[str, JsonValue]:
    """Bounded local exception metadata; no RPC or retry is initiated."""
    entries: list[JsonValue] = []
    seen: set[int] = set()
    current: BaseException | None = error
    termination = "complete"
    while current is not None:
        if id(current) in seen:
            termination = "cycle"
            break
        if len(entries) == MAXIMUM_ERROR_CHAIN:
            termination = "depth_limit"
            break
        seen.add(id(current))
        try:
            message = str(current)
        except Exception:  # noqa: BLE001 - diagnostic rendering cannot replace the retained failure
            message = "<exception message unavailable>"
        entry: dict[str, JsonValue] = {
            "exception_type": (
                type(current).__module__ + "." + type(current).__qualname__
            )[:MAXIMUM_ERROR_TEXT],
            "message": message[:MAXIMUM_ERROR_TEXT],
            "message_truncated": len(message) > MAXIMUM_ERROR_TEXT,
            "grpc_rpc_error": isinstance(current, RpcError),
        }
        if isinstance(current, RpcError):
            for name in ("code", "details"):
                try:
                    accessor = getattr(current, name, None)
                    value = accessor() if callable(accessor) else None
                    valid = value is None or (
                        isinstance(value, StatusCode)
                        if name == "code"
                        else isinstance(value, str)
                    )
                    if not valid:
                        entry["grpc_" + name] = None
                        entry["grpc_" + name + "_invalid_type"] = True
                    elif value is None:
                        entry["grpc_" + name] = None
                    else:
                        text = value.name if name == "code" else value
                        entry["grpc_" + name] = text[:MAXIMUM_ERROR_TEXT]
                        entry["grpc_" + name + "_truncated"] = (
                            len(text) > MAXIMUM_ERROR_TEXT
                        )
                except Exception as detail_error:  # noqa: BLE001 - retain metadata accessor failure without hiding the query failure
                    entry["grpc_" + name + "_access_error_type"] = (
                        type(detail_error).__module__
                        + "."
                        + type(detail_error).__qualname__
                    )[:MAXIMUM_ERROR_TEXT]
        entries.append(entry)
        current = current.__cause__
    return {
        "entries": entries,
        "termination": termination,
        "maximum_depth": MAXIMUM_ERROR_CHAIN,
        "maximum_text_characters": MAXIMUM_ERROR_TEXT,
        "link": "__cause__",
    }


def run(value: str, root: Path) -> int:
    plan = m.Plan.model_validate_json(value)
    receipt = m.ActionReceipt(observed_utc=io.utc(), plan=plan, pid=os.getpid())
    spark: SparkSession | None = None
    try:
        io.require(
            io.pin(plan.dataset.admissions["capitola"].path)
            == plan.dataset.admissions["capitola"],
            "full external driver input admission changed",
        )
        spark = SparkSession.builder.remote(
            f"sc://{plan.driver.advertise}:{plan.connect_port}"
        ).create()
        spark.client.set_retry_policies([DefaultPolicy(max_retries=0)])
        # Metadata bootstrap starts the declared two workers; it is not graph input validation.
        _ = spark.version
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            rows = spark.sql(
                "SELECT CAST(worker_id AS BIGINT) AS worker_id, host, CAST(port AS INT) AS port, status FROM system.cluster.workers"
            ).collect()
            receipt.workers = [cast(dict[str, JsonValue], row.asDict()) for row in rows]
            running = {
                (row["worker_id"], row["host"], row["port"])
                for row in rows
                if row["status"] == "RUNNING"
            }
            if {
                (1, plan.worker1.advertise, plan.worker_ports[0]),
                (2, plan.worker2.advertise, plan.worker_ports[1]),
            } <= running:
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("actual two physical worker registrations absent")
        io.save(root / "action-receipt.json", receipt)
        if plan.kind == "host-pool-refusal":
            try:
                frame = (
                    spark.range(0, 1048576, 1, 32)
                    .repartition(32, "id")
                    .groupBy("id")
                    .agg(sf.count("*").alias("count"))
                )
                frame.write.mode("error").parquet(plan.output_uri)
            except Exception as error:  # noqa: BLE001 - this remains unqualified until task-cause proof
                receipt.client_error = repr(error)
                receipt.client_error_before_teardown = True
                receipt.outcome = "completed_expected_error_unqualified"
            else:
                raise ValueError("required host-pool refusal did not occur")
        else:
            vertices = spark.read.parquet(plan.dataset.vertices).select(
                sf.col(plan.dataset.vertex_column).alias("id")
            )
            edges = spark.read.parquet(plan.dataset.edges).select(
                sf.col(plan.dataset.source_column).alias("src"),
                sf.col(plan.dataset.target_column).alias("dst"),
            )

            def observe(event: Mapping[str, Any]) -> None:
                if event.get("kind") == "native_plan":
                    receipt.native_request = cast(
                        dict[str, JsonValue], event["request"]
                    )
                    io.require(
                        receipt.native_request["vertices"]
                        == plan.dataset.expected_vertices,
                        "actual native vertex cardinality differs from external input admission",
                    )
                    io.save(root / "action-receipt.json", receipt)

            try:
                with ArgenteaBfs(spark, observer=observe).bfs(
                    vertices,
                    edges,
                    source=plan.dataset.source_vertex,
                    method="reference",
                    directed=False,
                    max_levels=plan.max_levels,
                    partitions=32,
                    max_phase_budget=32,
                    batch_rows=4096,
                ) as result:
                    if plan.kind == "bfs-cap0":
                        raise ValueError("required BFS cap failure did not occur")
                    native = result.native_frame
                    io.require(
                        native.columns == NATIVE_COLUMNS
                        and all(
                            isinstance(field.dataType, LongType)
                            for field in native.schema.fields
                        ),
                        "actual stock native13 export schema differs",
                    )
                    receipt.levels, receipt.reached, receipt.converged = (
                        result.levels,
                        result.reached,
                        result.converged,
                    )
                    receipt.export_projection = list(NATIVE_COLUMNS)
                    receipt.output_uri = plan.output_uri
                    native.write.mode("error").parquet(plan.output_uri)
                    receipt.outcome = "completed_unqualified_bfs_export"
            except Exception as error:
                if (
                    plan.kind != "bfs-cap0"
                    or str(error) == "required BFS cap failure did not occur"
                ):
                    raise
                receipt.client_error = repr(error)
                receipt.client_error_before_teardown = True
                for name in (
                    "view_cleanup_deferred",
                    "view_cleanup_errors",
                    "uncertain_view_names",
                ):
                    detail = getattr(error, name, None)
                    if (
                        isinstance(detail, bool | str)
                        or isinstance(detail, list)
                        and all(isinstance(item, str) for item in detail)
                    ):
                        receipt.failure_details[name] = cast(JsonValue, detail)
                receipt.outcome = "completed_expected_error_unqualified"
    except BaseException as error:  # noqa: BLE001 - failed query/interrupt never qualifies current or historical cause
        receipt.outcome = "error"
        receipt.errors.append(repr(error))
        receipt.failure_details["initial_exception_chain"] = exception_chain(error)
    finally:
        if spark is not None:
            try:
                receipt.stages = [
                    cast(dict[str, JsonValue], row.asDict())
                    for row in spark.sql(
                        "SELECT session_id, CAST(job_id AS BIGINT) AS job_id, CAST(stage AS BIGINT) AS stage, "
                        "CAST(partitions AS BIGINT) AS partitions, placement, `group` AS slot_group, mode "
                        "FROM system.execution.stages"
                    ).collect()
                ]
            except Exception as error:  # noqa: BLE001 - retain metadata evidence failure, never hide query failure
                receipt.errors.append(f"stage inventory: {error!r}")
                receipt.failure_details["stage_inventory_exception_chain"] = (
                    exception_chain(error)
                )
            try:
                spark.stop()
                receipt.session_closed = True
            except Exception as error:  # noqa: BLE001 - preserve session closure failure
                receipt.errors.append(f"session closure: {error!r}")
        try:
            io.require(
                io.pin(plan.dataset.admissions["capitola"].path)
                == plan.dataset.admissions["capitola"],
                "final external driver input admission differs",
            )
        except (OSError, ValueError) as error:
            receipt.errors.append(f"input admission closure: {error!r}")
        if receipt.errors:
            receipt.outcome = "error"
        receipt.observed_utc = io.utc()
        io.save(root / "action-receipt.json", receipt)
    return 0 if receipt.outcome != "error" else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.plan_json, args.root))


if __name__ == "__main__":
    main()
