"""The single-source seed does not require reading the vertex relation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.connect import functions as F

if TYPE_CHECKING:
    from pyspark.sql import DataFrame
    from pyspark.sql.connect.session import SparkSession


def initial_state(spark: SparkSession, source: int) -> DataFrame:
    # Source membership is part of the valid graph contract. Explicit types
    # preserve BIGINT IDs at both signed extremes. A range avoids local Arrow
    # conversion and configuration discovery.
    return spark.range(1).select(
        F.lit(source).cast("long").alias("id"),
        F.lit(0.0).alias("distance"),
        F.lit(0).cast("long").alias("hops"),
        F.lit(source).cast("long").alias("parent"),
    )
