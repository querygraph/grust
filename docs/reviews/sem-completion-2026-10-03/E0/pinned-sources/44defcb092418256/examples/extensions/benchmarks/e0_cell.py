"""One native Pregel propagation cell; the outer owner manages Sail and its budget.

Reads LDBC Parquet, writes the complete answer and pre-write relation plans,
and never validates/collects graph rows. Run e0_oracle.py after the cell and
the owned engine have exited. Plan recording is an explicit diagnostic cost.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from pyspark.sql.connect import functions as F
from pyspark.sql.connect.client.retries import DefaultPolicy
from pyspark.sql.connect.session import SparkSession
from pyspark_pecan import GraphAlgorithms, IterationEvent

Program = Literal["pagerank", "sssp", "landmarks"]


@dataclass(frozen=True, slots=True)
class Arguments:
    endpoint: str
    vertices: Path
    edges: Path
    output: Path
    program: Program
    source: int
    landmarks: tuple[int, ...]
    partitions: int
    iterations: int
    tolerance: float
    reset: float
    normalized: bool
    vote_to_halt: bool
    reversed_edges: bool
    input_weights: bool
    record_plans: bool
    undirected: bool = False


@dataclass(slots=True)
class Receipt:
    observed_utc: str
    status: str
    arguments: Arguments
    output: str
    pipeline_seconds: float | None = None
    algorithm_and_export_seconds: float | None = None
    iterations: int | None = None
    converged: bool | None = None
    error: str | None = None
    session_stopped: bool = False


def write_receipt(path: Path, receipt: Receipt) -> None:
    path.write_text(json.dumps(asdict(receipt), default=str, indent=2) + "\n")


def execute(arguments: Arguments) -> None:
    arguments.output.mkdir(parents=True, exist_ok=False)
    receipt = Receipt(datetime.now(timezone.utc).isoformat(), "running", arguments, str(arguments.output / "result"))
    write_receipt(arguments.output / "receipt.json", receipt)
    events: list[IterationEvent] = []

    def observe(event: IterationEvent) -> None:
        if event.plan is not None:
            (arguments.output / f"pre-write-relation-step-{event.iteration:05d}.txt").write_text(event.plan)
        events.append(event.model_copy(update={"plan": None}))

    spark = SparkSession.builder.remote(arguments.endpoint).create()
    # Do not retry a benchmark action behind the owner's receipt.
    spark.client.set_retry_policies([DefaultPolicy(max_retries=0)])
    try:
        graph = GraphAlgorithms(
            spark,
            snapshot_inputs=False,
            repartition_checkpoints=False,
            record_plans=arguments.record_plans,
            observer=observe,
        )
        started = time.perf_counter()
        vertices = spark.read.parquet(str(arguments.vertices)).select("id")
        original_edges = spark.read.parquet(str(arguments.edges))
        edges = original_edges.select(F.col("source").alias("src"), F.col("target").alias("dst"))
        if arguments.program == "sssp":
            edges = original_edges.select(
                F.col("source").alias("src"),
                F.col("target").alias("dst"),
                (F.col("weight") if arguments.input_weights else F.lit(1.0)).alias("weight"),
            )
        elif arguments.undirected:
            edges = edges.unionByName(edges.select(F.col("dst").alias("src"), F.col("src").alias("dst")))
        algorithm_started = time.perf_counter()
        if arguments.program == "pagerank":
            result = graph.pagerank(
                vertices,
                edges,
                method="pregel_delta",
                partitions=arguments.partitions,
                max_iterations=arguments.iterations,
                tolerance=arguments.tolerance,
                reset_probability=arguments.reset,
                normalize=arguments.normalized,
                vote_to_halt=arguments.vote_to_halt,
            )
        elif arguments.program == "sssp":
            result = graph.sssp(
                vertices,
                edges,
                method="pregel",
                source=arguments.source,
                partitions=arguments.partitions,
                max_iterations=arguments.iterations,
                vote_to_halt=arguments.vote_to_halt,
                directed=not arguments.undirected,
            )
        else:
            result = graph.shortest_paths(
                vertices,
                edges,
                landmarks=arguments.landmarks,
                to_landmarks=arguments.reversed_edges,
                partitions=arguments.partitions,
                max_iterations=arguments.iterations,
                vote_to_halt=arguments.vote_to_halt,
            )
        with result:
            result.write_parquet(str(arguments.output / "result"))
            finished = time.perf_counter()
            receipt.pipeline_seconds = finished - started
            receipt.algorithm_and_export_seconds = finished - algorithm_started
            receipt.iterations = result.iterations
            receipt.converged = result.converged
        receipt.status = "completed_unvalidated"
    except BaseException as error:
        receipt.status = "error"
        receipt.error = f"{type(error).__name__}: {error}"
        raise
    finally:
        (arguments.output / "events.json").write_text(
            json.dumps([event.model_dump(mode="json", exclude_none=True) for event in events], indent=2) + "\n"
        )
        try:
            spark.stop()
            receipt.session_stopped = True
        finally:
            write_receipt(arguments.output / "receipt.json", receipt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--vertices", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--program", choices=("pagerank", "sssp", "landmarks"), required=True)
    parser.add_argument("--source", type=int, default=0)
    parser.add_argument("--landmarks", type=int, nargs="+", default=[0])
    parser.add_argument("--partitions", type=int, default=16)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--tolerance", type=float, default=0.01)
    parser.add_argument("--reset", type=float, default=0.15)
    parser.add_argument("--normalized", action="store_true")
    parser.add_argument("--vote-to-halt", action="store_true")
    parser.add_argument("--reversed-edges", action="store_true")
    parser.add_argument("--input-weights", action="store_true")
    parser.add_argument("--record-plans", action="store_true")
    parser.add_argument("--undirected", action="store_true")
    args = parser.parse_args()
    execute(
        Arguments(
            args.endpoint,
            args.vertices,
            args.edges,
            args.output,
            cast(Program, args.program),
            args.source,
            tuple(args.landmarks),
            args.partitions,
            args.iterations,
            args.tolerance,
            args.reset,
            args.normalized,
            args.vote_to_halt,
            args.reversed_edges,
            args.input_weights,
            args.record_plans,
            args.undirected,
        )
    )


if __name__ == "__main__":
    main()
