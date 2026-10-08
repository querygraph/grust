"""Materialize typed graph frontiers on Sail; expose results only after success."""

from __future__ import annotations

import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from pyspark.sql.connect.session import SparkSession
from pyspark.sql.dataframe import DataFrame


class Cancelled(RuntimeError):
    """The operation was cancelled; no partial result is a successful query."""


class ResourceExceeded(RuntimeError):
    """An execution resource limit was reached, not a semantic path bound."""


@dataclass(frozen=True, slots=True)
class Limits:
    max_rounds: int = 10000
    max_rows: int = 1000000
    max_disk_bytes: int = 1 << 30

    def __post_init__(self) -> None:
        if min(self.max_rounds, self.max_rows, self.max_disk_bytes) <= 0:
            raise ValueError("execution limits must be positive")


@dataclass(frozen=True, slots=True)
class Traversal:
    view: str
    seed_sql: str
    adjacency_sql: str
    min_hops: int
    max_hops: int | None
    mode: str
    shortest_walk: bool

    def __post_init__(self) -> None:
        if self.mode not in {"Walk", "Trail", "Simple", "Acyclic"}:
            raise ValueError("unknown path mode")
        if self.min_hops < 0 or (
            self.max_hops is not None and self.max_hops < self.min_hops
        ):
            raise ValueError("invalid hop range")
        if self.shortest_walk and self.mode != "Walk":
            raise ValueError("pair pruning applies only to WALK")


@dataclass(frozen=True, slots=True)
class Materialization:
    view: str
    sql: str


ExecutionStep = Traversal | Materialization


@dataclass(frozen=True, slots=True)
class Program:
    sql: str
    traversals: tuple[Traversal, ...]
    steps: tuple[ExecutionStep, ...] = ()


@dataclass(frozen=True, slots=True)
class Progress:
    phase: str
    round: int
    rows: int


class Cancellation:
    """Can be called by a controlling thread; interrupts the query's Sail tag."""

    def __init__(self, spark: SparkSession, tag: str) -> None:
        self.spark = spark
        self.tag = tag
        self.event = threading.Event()

    def cancel(self) -> None:
        self.event.set()
        self.spark.interruptTag(self.tag)

    def check(self) -> None:
        if self.event.is_set():
            raise Cancelled("iterative graph execution cancelled")


class Execution:
    """Owns scratch files/views until close; evaluate the returned frame inside it."""

    def __init__(
        self,
        spark: SparkSession,
        scratch_parent: Path,
        limits: Limits | None = None,
        progress: Callable[[Progress], None] | None = None,
    ) -> None:
        self.spark = spark
        self.limits = limits or Limits()
        self.progress = progress
        self.tag = f"grust-{uuid.uuid4().hex}"
        self.root = scratch_parent.resolve() / self.tag
        self.cancellation = Cancellation(spark, self.tag)
        self.views: list[str] = []
        self.serial = 0

    def __enter__(self) -> Self:
        self.spark.addTag(self.tag)
        try:
            self.root.mkdir(parents=True, exist_ok=False)
        except Exception:
            self.spark.removeTag(self.tag)
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        errors: list[str] = []
        for view in reversed(self.views):
            try:
                self.spark.catalog.dropTempView(view)
            except Exception as error:  # noqa: BLE001 — finish all cleanup, preserving failures.
                errors.append(str(error))
        try:
            self.spark.removeTag(self.tag)
        except Exception as error:  # noqa: BLE001
            errors.append(str(error))
        try:
            shutil.rmtree(self.root)
        except Exception as error:  # noqa: BLE001
            errors.append(str(error))
        if errors:
            message = "iterative cleanup: " + "; ".join(errors)
            if exc is not None:
                exc.add_note(message)
            else:
                raise RuntimeError(message)
        if exc is None:
            self.cancellation.check()
        if (
            exc is not None
            and self.cancellation.event.is_set()
            and not isinstance(exc, Cancelled)
        ):
            raise Cancelled("iterative graph execution cancelled") from exc

    def view(self, frame: DataFrame) -> str:
        self.cancellation.check()
        name = f"{self.tag.replace('-', '_')}_{self.serial}"
        self.serial += 1
        frame.createOrReplaceTempView(name)
        self.views.append(name)
        return f"`{name}`"

    def materialize(self, query: str, phase: str, round_: int) -> tuple[str, int]:
        self.cancellation.check()
        path = self.root / str(self.serial)
        self.serial += 1
        # The max_rows+1 sentinel distinguishes a complete state from an overflow.
        # Every step is a fresh unsorted write: no checkpoint-after-sort hazard.
        self.spark.sql(query).limit(self.limits.max_rows + 1).write.parquet(
            path.as_uri()
        )
        self.cancellation.check()
        frame = self.spark.read.parquet(path.as_uri())
        rows = frame.count()
        if rows > self.limits.max_rows:
            raise ResourceExceeded(f"{phase}: state row limit exceeded")
        disk = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        if disk > self.limits.max_disk_bytes:
            raise ResourceExceeded(f"{phase}: scratch byte limit exceeded")
        if self.progress is not None:
            self.progress(Progress(phase, round_, rows))
        self.cancellation.check()
        return self.view(frame), rows

    def run(self, program: Program) -> DataFrame:
        replacements: dict[str, str] = {}
        try:
            steps: tuple[ExecutionStep, ...] = program.steps or program.traversals
            for step in steps:
                if isinstance(step, Materialization):
                    query = replace_views(step.sql, replacements)
                    replacements[step.view], _ = self.materialize(
                        query, "materialize", 0
                    )
                else:
                    seed = replace_views(step.seed_sql, replacements)
                    adjacency = replace_views(step.adjacency_sql, replacements)
                    replacements[step.view] = self.traverse(step, seed, adjacency)
            self.cancellation.check()
            return self.spark.sql(replace_views(program.sql, replacements))
        except Exception as exc:
            if self.cancellation.event.is_set():
                raise Cancelled("iterative graph execution cancelled") from exc
            raise

    def traverse(self, step: Traversal, seed_sql: str, adjacency_sql: str) -> str:
        if step.mode == "Walk" and step.max_hops is None and not step.shortest_walk:
            raise ValueError("unbounded ALL WALK is not admitted")
        adjacency, _ = self.materialize(adjacency_sql, "adjacency", 0)
        seed, _ = self.materialize(seed_sql, "seed", 0)
        initial = f"""SELECT sg, si, sg dg, si di,
            CAST(array() AS ARRAY<STRUCT<group:BIGINT,identity:BIGINT>>) edges,
            array(named_struct('group',sg,'identity',si)) vertices,
            CAST(0 AS BIGINT) length FROM {seed}"""
        frontier, rows = self.materialize(initial, "frontier", 0)
        accepted: list[str] = []
        visited: str | None = None
        round_ = 0
        while rows:
            self.cancellation.check()
            if round_ >= step.min_hops:
                accepted.append(frontier)
                if step.shortest_walk:
                    pairs = f"SELECT DISTINCT sg,si,dg,di FROM {frontier}"
                    if visited is not None:
                        pairs += f" UNION SELECT sg,si,dg,di FROM {visited}"
                    visited, _ = self.materialize(pairs, "visited", round_)
            if step.max_hops is not None and round_ >= step.max_hops:
                break
            if round_ >= self.limits.max_rounds:
                raise ResourceExceeded("round limit exceeded with a nonempty frontier")
            next_query = expansion(frontier, adjacency, step.mode)
            if visited is not None:
                # Keep all tied paths in this round; eliminate only earlier-round pairs.
                next_query = f"SELECT n.* FROM ({next_query}) n LEFT ANTI JOIN {visited} v ON n.sg=v.sg AND n.si=v.si AND n.dg=v.dg AND n.di=v.di"
            round_ += 1
            frontier, rows = self.materialize(next_query, "frontier", round_)
        if accepted:
            result_query = " UNION ALL ".join(
                f"SELECT * FROM {view}" for view in accepted
            )
        else:
            result_query = f"SELECT * FROM {frontier} WHERE FALSE"
        result, _ = self.materialize(result_query, "result", round_)
        return result


def replace_views(query: str, replacements: dict[str, str]) -> str:
    # Substitute generated bare stage references, never quoted storage identifiers
    # or SQL string values, even if a caller's table name matches a stage name.
    output: list[str] = []
    index = 0
    while index < len(query):
        char = query[index]
        if char in {"`", "'", '"'}:
            start = index
            index += 1
            while index < len(query):
                if query[index] == char:
                    index += 1
                    if index < len(query) and query[index] == char:
                        index += 1
                        continue
                    break
                index += 1
            output.append(query[start:index])
        elif char.isalpha() or char == "_":
            start = index
            index += 1
            while index < len(query) and (
                query[index].isalnum() or query[index] == "_"
            ):
                index += 1
            token = query[start:index]
            output.append(replacements.get(token, token))
        else:
            output.append(char)
            index += 1
    return "".join(output)


def expansion(frontier: str, adjacency: str, mode: str) -> str:
    vertex = "named_struct('group',a.dg,'identity',a.di)"
    edge = "named_struct('group',a.eg,'identity',a.ei)"
    condition = "TRUE"
    if mode in {"Trail", "Simple"}:
        condition = f"NOT array_contains(f.edges,{edge})"
    if mode == "Acyclic":
        condition = f"NOT array_contains(f.vertices,{vertex})"
    if mode == "Simple":
        condition += f" AND (f.length=0 OR NOT (f.dg=f.sg AND f.di=f.si)) AND (NOT array_contains(f.vertices,{vertex}) OR (a.dg=f.sg AND a.di=f.si))"
    return f"""SELECT f.sg,f.si,a.dg,a.di,
        concat(f.edges,array({edge})) edges,
        concat(f.vertices,array({vertex})) vertices, f.length+1 length
        FROM {frontier} f INNER JOIN {adjacency} a ON f.dg=a.sg AND f.di=a.si
        WHERE {condition}"""
