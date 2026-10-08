"""Deterministic refusal, cancellation and scratch-limit controls on live Sail."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path

from iterative import (
    Cancelled,
    Execution,
    Limits,
    Program,
    Progress,
    ResourceExceeded,
    replace_views,
)
from pyspark.sql.connect.session import SparkSession


@dataclass(frozen=True, slots=True)
class Control:
    name: str
    outcome: str
    error: str | None
    scratch_clean: bool


def run_controls(spark: SparkSession, parent: Path, program: Program) -> list[Control]:
    results: list[Control] = []
    for name, limits, phase in [
        ("row_limit", Limits(max_rows=1), None),
        ("disk_limit", Limits(max_disk_bytes=1), None),
        ("round_limit", Limits(max_rounds=1), None),
        ("cancel_before_run", Limits(), "before"),
        ("cancel_after_frontier", Limits(), "frontier"),
    ]:
        execution = Execution(spark, parent, limits)
        if phase == "frontier":
            execution.progress = partial(cancel_frontier, execution)
        error: str | None = None
        outcome = "unexpected_success"
        try:
            with execution:
                if phase == "before":
                    execution.cancellation.cancel()
                execution.run(program).collect()
        except (Cancelled, ResourceExceeded) as exc:
            expected = Cancelled if phase is not None else ResourceExceeded
            outcome = "passed" if isinstance(exc, expected) else "wrong_error"
            error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 — keep unexpected engine/control failures.
            outcome = "error"
            error = f"{type(exc).__name__}: {exc}"
        clean = not execution.root.exists()
        if not clean:
            outcome = "cleanup_failure"
        results.append(Control(name, outcome, error, clean))
    before = (
        "SELECT '__grust_traverse_0', `__grust_traverse_0`, * FROM __grust_traverse_0"
    )
    actual = replace_views(before, {"__grust_traverse_0": "`owned_view`"})
    expected_sql = (
        "SELECT '__grust_traverse_0', `__grust_traverse_0`, * FROM `owned_view`"
    )
    results.append(
        Control(
            "quoted_identifier_preserved",
            "passed" if actual == expected_sql else "mismatch",
            None,
            True,
        )
    )
    return results


def cancel_frontier(execution: Execution, progress: Progress) -> None:
    if progress.phase == "frontier":
        execution.cancellation.cancel()


def memory_probe(spark: SparkSession) -> Control:
    try:
        spark.sql("SELECT id, count(*) n FROM range(10000) GROUP BY id").collect()
    except Exception as exc:  # noqa: BLE001 — retain the exact engine limit error.
        message = str(exc)
        lowered = message.lower()
        passed = "memory" in lowered and (
            "resource" in lowered
            or "exhaust" in lowered
            or "failed to allocate" in lowered
        )
        return Control(
            "managed_memory_pool", "passed" if passed else "wrong_error", message, True
        )
    return Control("managed_memory_pool", "unexpected_success", None, True)
