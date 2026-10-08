"""Disjoint fixture replicas: a disclosed synthetic scale control, not an LDBC SF."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from snb_dataset import Dataset, Table


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplicatedTable(Table):
    exact_metadata: dict[str, Any]

    def metadata(self) -> dict[str, Any]:
        return self.exact_metadata


def replicate(dataset: Dataset, replicas: int) -> Dataset:
    if not 1 <= replicas <= 100:
        raise ValueError("synthetic replica count must be in 1..100")
    if replicas == 1:
        return dataset
    maximum = max(
        int(row["_identity"]) for table in dataset.tables for row in table.records
    )
    stride = 1 << maximum.bit_length()
    if maximum + stride * (replicas - 1) > (1 << 63) - 1:
        raise ValueError("replicated identifiers would overflow signed Int64")
    tables = []
    for table in dataset.tables:
        shifted = (
            {"_identity", "src", "dst"}
            if table.source is not None
            else {"_identity", "id"}
        )
        metadata = table.metadata()
        metadata["rows"] *= replicas
        metadata["distinct"] = {
            key: value * replicas if key in shifted else value
            for key, value in metadata["distinct"].items()
        }
        for key in ("source_ndv", "target_ndv"):
            if metadata[key] is not None:
                metadata[key] *= replicas
        records = [
            {
                key: value + stride * replica if key in shifted else value
                for key, value in row.items()
            }
            for replica in range(replicas)
            for row in table.records
        ]
        tables.append(
            ReplicatedTable(
                table.group,
                table.name,
                records,
                table.types,
                table.source,
                table.target,
                exact_metadata=metadata,
            )
        )
    digest = hashlib.sha256(
        json.dumps(
            {
                "base": dataset.sha256,
                "replicas": replicas,
                "stride": stride,
                "version": "disjoint-int64-v1",
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return Dataset(tuple(tables), dataset.schema, dataset.files, digest)
