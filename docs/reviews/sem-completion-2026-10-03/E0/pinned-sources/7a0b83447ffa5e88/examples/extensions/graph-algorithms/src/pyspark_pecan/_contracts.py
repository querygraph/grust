"""Shared typed helpers without controller or runtime imports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, Row


class ConvergenceError(RuntimeError):
    """The iteration limit was reached before the requested stopping rule."""

    __module__ = "pyspark_pecan.algorithms"


def first_row(frame: DataFrame) -> Row:
    """The first row of a scalar reduction, including an empty-input aggregate."""
    row = frame.first()
    assert row is not None
    return row
