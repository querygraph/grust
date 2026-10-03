"""Parquet generations with explicit capability-based cleanup."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .lifecycle import GraphResult

if TYPE_CHECKING:
    from pyspark.sql import DataFrame
    from pyspark.sql.connect.session import SparkSession

    from .lifecycle import CancellationToken
    from .utils import GraphUtils


class StagingRun:
    """One owned staging directory holding the Parquet generations of a run."""

    def __init__(self, spark: SparkSession, utils: GraphUtils, cancellation: CancellationToken,
                 partitions: int, *, repartition_checkpoints: bool = True) -> None:
        self.spark = spark
        self.utils = utils
        self.cancellation = cancellation
        self.partitions: int = partitions
        self.repartition_checkpoints: bool = repartition_checkpoints
        self.path, self.token = utils.allocate()
        self.closed: bool = False
        self.write_uncertain: bool = False
        self.result_path: str | None = None
        self._stages: dict[str, DataFrame | None] = {}
        self._serial: int = 0

    def touch(self) -> None:
        if self.closed:
            raise RuntimeError("graph staging run is closed")
        if not self.utils.exists(self.path, self.token):
            raise RuntimeError("graph staging session expired or its files were removed")

    def materialize(self, frame: DataFrame) -> tuple[str, DataFrame]:
        """Write `frame` as the next generation and return its path and stored relation.

        The stored relation is read back from the written files; its schema is
        compared by names and types (Parquet readers may widen nullability).
        Row counts are not verified: the graph is assumed valid and the engine's
        write is trusted to be complete once it has returned.
        """
        self.cancellation.check()
        self.touch()
        self.cancellation.check()
        path = self.path.rstrip("/") + f"/stage-{self._serial:05d}"
        self._serial += 1
        # Record before writing, so a partially failed stage is still owned.
        self._stages[path] = None
        # A failed/interrupted write RPC is not a distributed writer-drain
        # barrier. Keep ownership for session teardown if its outcome is unknown.
        self.write_uncertain = True
        writing = frame.repartition(self.partitions) if self.repartition_checkpoints else frame
        writing.write.mode("error").parquet(path)
        self.write_uncertain = False
        self.cancellation.check()
        stored = self.spark.read.parquet(path)
        if not stored.schema.fields:
            # Some engines create no data files for an empty write. Preserve
            # the known schema when there is no Parquet footer to infer it from.
            stored = self.spark.read.schema(frame.schema).parquet(path)
        if stored.schema != frame.schema:
            actual = [(field.name, field.dataType) for field in stored.schema]
            expected = [(field.name, field.dataType) for field in frame.schema]
            if actual != expected:
                raise RuntimeError("materialized graph stage changed its schema")
        self.cancellation.check()
        self._stages[path] = stored
        return path, stored

    def remove(self, path: str) -> None:
        self.utils.remove(path, self.token)
        self._stages.pop(path, None)

    def finish(self, path: str, frame: DataFrame, *, algorithm: str, iterations: int,
               converged: bool | None) -> GraphResult:
        self.cancellation.check()
        for obsolete in list(self._stages):
            if obsolete != path:
                self.remove(obsolete)
        self.cancellation.check()
        self.result_path = path
        return GraphResult(self, frame, algorithm=algorithm, iterations=iterations, converged=converged)

    def close(self) -> None:
        if not self.closed:
            self.utils.remove(self.path, self.token)
            self.closed = True
            self._stages.clear()
