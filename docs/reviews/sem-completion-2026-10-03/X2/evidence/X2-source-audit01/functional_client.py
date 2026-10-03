"""Producer only: root owns a fresh native server, resources and actual waits.

The functional control exercises the current reference BFS relation shape.
The tiny-pool control retains any induced error for separate causal/log review;
its zero exit never certifies the historical stream-loss cause or this control.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql.connect import functions as F
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession
from pyspark_pecan import GraphAlgorithms, IterationEvent

from probe_models import Arguments, Receipt


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute(args: Arguments) -> None:
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = Receipt(utc(), args)
    events: list[IterationEvent] = []

    def observe(event: IterationEvent) -> None:
        if event.plan is not None:
            (args.output / f"pre-write-step-{event.iteration:05}.txt").write_text(event.plan)
        events.append(event.model_copy(update={"plan": None}))

    spark = SparkSession.builder.remote(args.endpoint).create()
    spark.client.set_retry_policies([DefaultPolicy(max_retries=0)])
    try:
        receipt.query_start_utc = utc()
        start = time.perf_counter()
        if args.case == "functional":
            graph = GraphAlgorithms(
                spark, snapshot_inputs=True, repartition_checkpoints=True, record_plans=True, observer=observe
            )
            vertices = spark.read.parquet(str(args.fixture / "vertices.parquet"))
            edges = spark.read.parquet(str(args.fixture / "edges"))
            with graph.bfs(
                vertices,
                edges,
                source=0,
                method="reference",
                directed=False,
                partitions=args.partitions,
                max_iterations=32,
            ) as result:
                result.write_parquet(str(args.output / "result"))
                receipt.pipeline_seconds = time.perf_counter() - start
                receipt.iterations = result.iterations
                receipt.converged = result.converged
            receipt.status = "completed_unvalidated"
        else:
            query = (
                spark.range(0, 1_048_576, 1, args.partitions)
                .repartition(args.partitions, "id")
                .groupBy("id")
                .agg(F.count("*").alias("count"))
            )
            (args.output / "fault-query.txt").write_text(
                "range(1048576).repartition(P,id).groupBy(id).count().write.parquet; "
                "fresh explicit greedy pool of 1048576 bytes per process required\n"
            )
            try:
                query.write.mode("error").parquet(str(args.output / "partial-fault-output"))
            except Exception as error:  # noqa: BLE001 - separate post-exit log oracle classifies the induced fault
                receipt.error = f"{type(error).__name__}: {error}"
                receipt.status = "expected_error_pending_log_qualification"
            else:
                raise ValueError("explicit tiny-pool control did not produce an error")
            receipt.pipeline_seconds = time.perf_counter() - start
    except BaseException as error:
        receipt.status = "error"
        receipt.error = f"{type(error).__name__}: {error}"
        raise
    finally:
        receipt.query_end_utc = utc()
        (args.output / "events.json").write_text(
            json.dumps([event.model_dump(mode="json", exclude_none=True) for event in events], indent=2) + "\n"
        )
        try:
            spark.stop()
            receipt.session_stopped = True
        finally:
            (args.output / "receipt.json").write_text(json.dumps(asdict(receipt), default=str, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--case", required=True, choices=("functional", "pool-refusal"))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partitions", type=int, default=8)
    args = parser.parse_args()
    execute(Arguments(args.endpoint, args.case, args.fixture, args.output, args.partitions))


if __name__ == "__main__":
    main()
