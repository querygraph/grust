"""Cancellation and ownership of materialized graph results."""

from __future__ import annotations

import threading
import uuid
from typing import TYPE_CHECKING

from typing_extensions import Self

if TYPE_CHECKING:
    from pyspark.sql import DataFrame
    from pyspark.sql.connect.session import SparkSession

    from .staging import StagingRun
    from .types import ContractionStep


class GraphCancelledError(RuntimeError):
    """The algorithm was cancelled before producing a retained result."""


class CancellationToken:
    """Request interruption and stop at the next cooperative action boundary.

    Call cancel() from another thread. A token belongs to at most one active
    algorithm. Spark Connect query tags scope interruption to that algorithm.
    InterruptTag covers registered operations; a race between a local check
    and server operation registration is best effort, not atomic cancellation.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._spark: SparkSession | None = None
        self._tag: str = "graph-" + uuid.uuid4().hex

    def check(self) -> None:
        if self._event.is_set():
            raise GraphCancelledError("graph algorithm cancelled")

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            spark = self._spark
        if spark is not None:
            spark.interruptTag(self._tag)

    def attach(self, spark: SparkSession) -> None:
        self.check()
        with self._lock:
            if self._spark is not None:
                raise ValueError("a cancellation token can control only one active algorithm")
            self._spark = spark
        try:
            spark.addTag(self._tag)
            self.check()
        except BaseException:
            with self._lock:
                self._spark = None
            spark.removeTag(self._tag)
            raise

    def detach(self) -> None:
        with self._lock:
            spark, self._spark = self._spark, None
        if spark is not None:
            spark.removeTag(self._tag)


class GraphResult:
    """A DataFrame plus its server-owned storage lease.

    Use as a context manager. close() removes the run and invalidates the frame.
    touch() keeps its session active. write_parquet() produces an independently owned
    export; cleanup of that caller-selected path is the caller's responsibility.
    The optional attributes are set by the algorithm that produced the result.
    """

    def __init__(self, run: StagingRun, frame: DataFrame, *, algorithm: str, iterations: int,
                 converged: bool | None) -> None:
        self._run = run
        self._frame = frame
        self.algorithm: str = algorithm
        self.iterations: int = iterations
        self.converged: bool | None = converged
        self.method: str | None = None
        self.seed: int | None = None
        self.contractions: list[ContractionStep] | None = None
        self.residual: float | None = None
        self.error_bound: float | None = None

    @property
    def frame(self) -> DataFrame:
        if self._run.closed:
            raise RuntimeError("graph result is closed")
        return self._frame

    @property
    def path(self) -> str | None:
        return self._run.result_path

    def touch(self) -> None:
        self._run.touch()

    def close(self) -> None:
        self._run.close()

    def write_parquet(self, path: str, *, mode: str = "error") -> None:
        self.touch()
        self.frame.write.mode(mode).parquet(path)

    def __enter__(self) -> Self:
        self.touch()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
