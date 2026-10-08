"""Sail table projections; only admitted bounded selections enter Nutmeg CSR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyspark.sql import DataFrame
from pyspark.sql.connect import functions as F
from pyspark.sql.connect.session import SparkSession
from sail_nutmeg.client import Nutmeg  # type: ignore[import-untyped]


@dataclass(frozen=True, slots=True)
class Point:
    id: str
    kind: str
    x: float
    y: float
    represented_vertices: str


@dataclass(frozen=True, slots=True)
class Link:
    source: str
    target: str
    multiplicity: str


@dataclass(frozen=True, slots=True)
class View:
    points: tuple[Point, ...]
    links: tuple[Link, ...]
    expanded: frozenset[str]
    members: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class Catalog:
    graph: str
    snapshot: str
    projection: str
    hierarchy: str
    layout: str
    vertex_rows: int
    edge_rows: int
    source_bytes: int


class Refusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Provider:
    def __init__(
        self, spark: SparkSession, vertices: str, edges: str, catalog: Catalog
    ) -> None:
        self.spark = spark
        self.vertices: DataFrame = spark.read.parquet(vertices)
        self.edges: DataFrame = spark.read.parquet(edges)
        self.catalog = catalog
        self.nutmeg = Nutmeg(spark)
        expected = {"id": "string", "group_id": "string", "x": "double", "y": "double"}
        if dict(self.vertices.dtypes) != expected:
            raise ValueError(f"vertex schema must be {expected}")
        if dict(self.edges.dtypes) != {"src": "string", "dst": "string"}:
            raise ValueError("edge schema must be src/dst string")

    def follow(
        self, seeds: tuple[str, ...], direction: str, hops: int, cap: int
    ) -> tuple[str, ...]:
        """Set reachability includes seeds; union-distinct each bounded round."""
        reached = set(seeds)
        frontier = set(seeds)
        for _ in range(hops):
            if not frontier:
                break
            frames: list[DataFrame] = []
            if direction in {"out", "both"}:
                frames.append(
                    self.edges.filter(F.col("src").isin(sorted(frontier))).select(
                        F.col("dst").alias("id")
                    )
                )
            if direction in {"in", "both"}:
                frames.append(
                    self.edges.filter(F.col("dst").isin(sorted(frontier))).select(
                        F.col("src").alias("id")
                    )
                )
            next_frame = frames[0]
            for frame in frames[1:]:
                next_frame = next_frame.unionByName(frame)
            rows = next_frame.distinct().limit(cap + 1).collect()
            frontier = {str(row.id) for row in rows} - reached
            reached |= frontier
            if len(reached) > cap:
                raise Refusal(
                    "BUDGET_EXCEEDED", "complete follow exceeds the selection cap"
                )
        return tuple(sorted(reached))

    def view(
        self,
        expanded: frozenset[str],
        members: tuple[str, ...] | None,
        point_cap: int,
        link_cap: int,
    ) -> View:
        """Recompute all quotient edges, including affected incident edges."""
        nodes = self.vertices
        if members is not None:
            nodes = nodes.filter(F.col("id").isin(list(members)))
        mapping = nodes.select(
            "id",
            "x",
            "y",
            F.when(F.col("group_id").isin(sorted(expanded)), F.col("id"))
            .otherwise(F.concat(F.lit("h/"), F.col("group_id")))
            .alias("display"),
        )
        points = (
            mapping.groupBy("display")
            .agg(
                F.avg("x").alias("x"), F.avg("y").alias("y"), F.count("*").alias("size")
            )
            .orderBy("display")
            .limit(point_cap + 1)
            .collect()
        )
        if len(points) > point_cap:
            raise Refusal("BUDGET_EXCEEDED", "complete frontier exceeds the point cap")
        source = mapping.select(
            F.col("id").alias("src"), F.col("display").alias("source")
        )
        target = mapping.select(
            F.col("id").alias("dst"), F.col("display").alias("target")
        )
        links = (
            self.edges.join(source, "src")
            .join(target, "dst")
            .groupBy("source", "target")
            .count()
            .orderBy("source", "target")
            .limit(link_cap + 1)
            .collect()
        )
        if len(links) > link_cap:
            raise Refusal("BUDGET_EXCEEDED", "complete quotient exceeds the link cap")
        return View(
            tuple(
                Point(
                    str(r.display),
                    "aggregate" if str(r.display).startswith("h/") else "vertex",
                    float(r.x),
                    float(r.y),
                    str(r.size),
                )
                for r in points
            ),
            tuple(Link(str(r.source), str(r.target), str(r["count"])) for r in links),
            expanded,
            members,
        )

    def components(
        self, members: tuple[str, ...], name: str, method: str
    ) -> tuple[tuple[str, str], ...]:
        # A bounded projection map makes numeric-only kernels available without
        # turning opaque source IDs into JavaScript numbers or losing namespaces.
        lookup = self.spark.createDataFrame(
            [(value, str(index)) for index, value in enumerate(members)],
            "id string, node_id string",
        )
        nodes = self.vertices.select("id").join(lookup, "id").select("node_id")
        source = lookup.select(
            F.col("id").alias("src"), F.col("node_id").alias("source")
        )
        target = lookup.select(
            F.col("id").alias("dst"), F.col("node_id").alias("target")
        )
        edges = (
            self.edges.join(source, "src")
            .join(target, "dst")
            .select("source", "target")
        )
        self.nutmeg.stage(name, nodes, edges, order="asStaged")
        try:
            rows = self.nutmeg.run(name, method).collect()
            return tuple(
                sorted((members[int(row.nodeId)], str(row.componentId)) for row in rows)
            )
        finally:
            self.nutmeg.drop(name)

    def diagnostics(self) -> dict[str, Any]:
        return dict(self.nutmeg.status())
