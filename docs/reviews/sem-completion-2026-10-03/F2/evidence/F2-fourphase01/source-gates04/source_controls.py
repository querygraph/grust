"""Bounded handoff controls using extracted source and in-memory typed adapters.

No Spark, Nutmeg, Arrow or native libraries are imported or launched.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Self, cast

from f2a_models import ArrowHandoff


@dataclass(slots=True)
class Cached:
    _child: None = None


@dataclass(slots=True)
class Inline:
    _child: None = None


@dataclass(slots=True)
class Frame:
    values: tuple[int, ...]
    _plan: Cached | Inline
    depth: int = 0

    def unionByName(self, other: Frame) -> Frame:
        return Frame(
            self.values + other.values, Cached(), max(self.depth, other.depth) + 1
        )


@dataclass(slots=True)
class Table:
    values: tuple[int, ...]
    schema: str = "two-int64"

    @property
    def num_rows(self) -> int:
        return len(self.values)

    def slice(self, offset: int, length: int) -> Table:
        return Table(self.values[offset : offset + length])

    def to_batches(self) -> list[tuple[int, ...]]:
        return [self.values]


@dataclass(slots=True)
class Sink:
    size: int = 0

    def getvalue(self) -> Sink:
        return self


@dataclass(slots=True)
class Writer:
    sink: Sink
    bytes_per_row: int

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        return None

    def write_batch(self, values: tuple[int, ...]) -> None:
        self.sink.size += len(values) * self.bytes_per_row


@dataclass(slots=True)
class IPC:
    bytes_per_row: int

    def new_stream(self, sink: Sink, _schema: str) -> Writer:
        return Writer(sink, self.bytes_per_row)


@dataclass(slots=True)
class Arrow:
    ipc: IPC

    def BufferOutputStream(self) -> Sink:
        return Sink()


@dataclass(slots=True)
class Spark:
    cached: bool = True
    created: int = 0

    def createDataFrame(self, table: Table) -> Frame:
        self.created += 1
        return Frame(table.values, Cached() if self.cached else Inline())


@dataclass(slots=True)
class Configuration:
    chunk_rows: int = 2


@dataclass(slots=True)
class Receipt:
    configuration: Configuration = field(default_factory=Configuration)
    arrow_handoffs: list[ArrowHandoff] = field(default_factory=list)


def extracted(
    path: Path, bytes_per_row: int = 16
) -> Callable[[Spark, Table, Receipt, Literal["vertices", "edges"]], Frame]:
    module = ast.parse(path.read_text())
    nodes = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"cached_chunk", "bounded_handoff"}
    ]
    if len(nodes) != 2:
        raise ValueError("the exact production handoff bodies were not found")
    namespace: dict[str, object] = {
        "pa": Arrow(IPC(bytes_per_row)),
        "CachedLocalRelation": Cached,
        "LocalRelation": Inline,
        "ArrowHandoff": ArrowHandoff,
        "__builtins__": __builtins__,
    }
    future = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    )
    code = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(code, str(path), "exec"), namespace)  # noqa: S102 - exact whitelisted local function bodies only
    return cast(
        Callable[[Spark, Table, Receipt, Literal["vertices", "edges"]], Frame],
        namespace["bounded_handoff"],
    )


def main() -> None:
    root = Path(__file__).resolve().parent
    path = root / "f2a_worker.py"
    identity = hashlib.sha256(path.read_bytes()).hexdigest()
    values = (-(2**63), -8, 0, 5, 5, 2**63 - 1, 7)
    receipt = Receipt()
    frame = extracted(path)(Spark(), Table(values), receipt, "vertices")
    if (
        frame.values != values
        or frame.depth != 2
        or receipt.arrow_handoffs[0].chunks != 4
    ):
        raise ValueError("balanced handoff changed order/duplicates/domain or depth")
    denied = 0
    for spark, size in ((Spark(cached=False), 16), (Spark(), 32 * 1024 * 1024)):
        try:
            extracted(path, size)(spark, Table(values), Receipt(), "edges")
        except ValueError:
            denied += 1
        else:
            raise ValueError("unsafe inline or oversized IPC handoff was admitted")
    if denied != 2 or hashlib.sha256(path.read_bytes()).hexdigest() != identity:
        raise ValueError("control/source closure failed")
    print(
        json.dumps(
            {
                "observed_utc": datetime.now(timezone.utc).isoformat(),
                "outcome": "passed_source_controls",
                "controls": 3,
                "worker_sha256": identity,
                "scope": "Actual extracted cached_chunk/bounded_handoff bodies; typed in-memory adapters, no engine/native imports.",
            }
        )
    )


if __name__ == "__main__":
    main()
